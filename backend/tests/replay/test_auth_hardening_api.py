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
from app.services import login_guard

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
    login_guard._mem.clear()
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
