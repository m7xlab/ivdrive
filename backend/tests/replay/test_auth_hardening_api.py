"""v1.4.0 auth hardening through the real API on the scratch Postgres: the login limiter, cookie-only
tokens, session revocation on password change, docs off, reverse geocoding behind login."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
from app.security import get_password_hash
from app.services import auth_guard, login_guard

pytestmark = pytest.mark.asyncio

PASSWORD = "correct-horse-battery-staple"


@pytest_asyncio.fixture
async def api(replay_sessionmaker, monkeypatch):
    from app.models.user import User

    async def _db():
        # Mirrors app.database.get_db: commit after the request, roll back on error.
        async with replay_sessionmaker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(login_guard, "_kv", lambda: None)
    monkeypatch.setattr(auth_guard, "_kv", lambda: None)
    login_guard._mem.clear()
    auth_guard._mem.clear()
    async with replay_sessionmaker() as s:
        user = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex[:8]}@example.com", password_hash=get_password_hash(PASSWORD))
        s.add(user)
        await s.commit()
        email = user.email
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, email
    finally:
        app.dependency_overrides.pop(get_db, None)
        login_guard._mem.clear()
        auth_guard._mem.clear()


async def test_login_sets_cookies_and_keeps_tokens_out_of_the_body(api):
    c, email = api
    r = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"] == "" and r.json()["refresh_token"] == ""
    assert {"access_token", "refresh_token", "csrf_token"} <= set(r.cookies.keys())
    me = await c.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["email"] == email


async def test_five_wrong_passwords_lock_the_account_for_fifteen_minutes(api):
    c, email = api
    for _ in range(5):
        r = await c.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401
    r = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 429 and r.headers["retry-after"] == "900"
    assert "Too many attempts" in r.json()["error"]["message"]


async def test_a_wrong_password_does_not_say_whether_the_account_exists(api):
    c, email = api
    known = await c.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
    unknown = await c.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert known.status_code == unknown.status_code == 401
    assert known.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_changing_the_password_ends_other_sessions(api):
    c, email = api
    first = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    old_cookies = dict(first.cookies)
    # a second browser
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        r = await other.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200
        r = await other.put("/api/v1/auth/me/password",
                            json={"old_password": PASSWORD, "new_password": "a-new-password-123"},
                            headers={"X-CSRF-Token": other.cookies["csrf_token"]})
        assert r.status_code == 200, r.text
        me = await other.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text   # the changing browser stays in
    stale = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=old_cookies)
    async with stale:
        assert (await stale.get("/api/v1/auth/me")).status_code == 401
        assert (await stale.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_everywhere_bumps_the_version(api):
    c, email = api
    await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    keep = dict(c.cookies)
    r = await c.post("/api/v1/auth/logout-all", headers={"X-CSRF-Token": c.cookies["csrf_token"]})
    assert r.status_code == 200
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=keep) as stale:
        assert (await stale.get("/api/v1/auth/me")).status_code == 401


async def test_long_passwords_are_a_422_not_a_500(api):
    c, email = api
    r = await c.post("/api/v1/auth/login", json={"email": email, "password": "x" * 100})
    assert r.status_code == 401   # not a crash, and not a hint
    await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    r = await c.put("/api/v1/auth/me/password", json={"old_password": PASSWORD, "new_password": "x" * 100},
                    headers={"X-CSRF-Token": c.cookies["csrf_token"]})
    assert r.status_code == 422


async def test_docs_are_off_and_reverse_geocoding_needs_a_login(api):
    c, _ = api
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await c.get(path)).status_code == 404, path
    r = await c.post("/api/v1/geo/reverse", json={"latitude": 54.68, "longitude": 25.28})
    assert r.status_code in (401, 403)


async def test_users_behind_the_same_web_container_have_separate_limits(api):
    """The web app proxies /api, so every browser arrives from the web container; the real address is
    the right-hand X-Forwarded-For entry. One address failing five times must not lock another."""
    c, email = api
    one = {"X-Forwarded-For": "8.8.4.4"}
    two = {"X-Forwarded-For": "8.8.8.8"}
    for _ in range(5):
        assert (await c.post("/api/v1/auth/login", json={"email": email, "password": "wrong"}, headers=one)).status_code == 401
    assert (await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=one)).status_code == 429
    ok = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=two)
    assert ok.status_code == 200, ok.text


async def test_the_response_cache_does_not_serve_revoked_or_unversioned_tokens(api, monkeypatch):
    import jwt as _jwt
    from app.config import settings
    from app.services import cache as cache_mod

    class FakeValkey:
        def __init__(self): self.d = {}
        async def get(self, k): return self.d.get(k)
        async def setex(self, k, ttl, v): self.d[k] = v
        async def scan(self, cursor="0", match="*", count=100):
            import fnmatch
            return "0", [k for k in self.d if fnmatch.fnmatch(k, match)]
        async def delete(self, *keys):
            for k in keys: self.d.pop(k, None)

    fake = FakeValkey()
    monkeypatch.setattr(cache_mod, "valkey_client", fake)
    c, email = api
    await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    me = (await c.get("/api/v1/auth/me")).json()
    uid = me["id"]
    tv = _jwt.decode(c.cookies["access_token"], options={"verify_signature": False})["tv"]
    path = "/api/v1/vehicles/00000000-0000-0000-0000-000000000001/trips-analytics"
    key = f"ivdrive:api:cache:{uid}:v{tv}:{path}:*/*"
    import json as _json
    fake.d[key] = _json.dumps({"body": "[]", "status": 200, "media_type": "application/json"})
    assert (await c.get(path)).headers.get("x-cache") == "HIT"          # mechanism works for a valid session

    old_cookies = dict(c.cookies)
    r = await c.post("/api/v1/auth/logout-all", headers={"X-CSRF-Token": c.cookies["csrf_token"]})
    assert r.status_code == 200
    assert not [k for k in fake.d if k.startswith(f"ivdrive:api:cache:{uid}:")]   # purged on revocation
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=old_cookies) as stale:
        got = await stale.get(path)                       # entries were purged: a miss, then refused
        assert got.headers.get("x-cache") != "HIT" and got.status_code == 401, "a revoked token must not read the cache"
    # a session started after the bump never reads an entry cached under the old version
    fake.d[key] = _json.dumps({"body": "[]", "status": 200, "media_type": "application/json"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh:
        r = await fresh.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200
        assert (await fresh.get(path)).headers.get("x-cache") != "HIT"
    # a token without a version claim is never served from the cache either
    unversioned = _jwt.encode({"sub": uid, "type": "access", "exp": 4102444800}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={"access_token": unversioned}) as old:
        got = await old.get(path)
        assert got.headers.get("x-cache") != "HIT" and got.status_code == 401
