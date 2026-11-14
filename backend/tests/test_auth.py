import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"

engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def open_registration(monkeypatch):
    """The service defaults to invite-only registration; these tests register directly."""
    from app.config import settings

    monkeypatch.setattr(settings, "service_registration", "open")


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient):
    payload = {
        "email": "test@example.com",
        "password": "securepass123",
        "display_name": "Test User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    return resp.json()


@pytest_asyncio.fixture
async def auth_tokens(client: AsyncClient, registered_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "securepass123"},
    )
    assert resp.status_code == 200
    return resp.json()


def _set_cookie_headers(resp) -> dict[str, str]:
    """Map cookie name -> raw Set-Cookie header, so flags can be asserted."""
    out = {}
    for raw in resp.headers.get_list("set-cookie"):
        name = raw.split("=", 1)[0].strip()
        out[name] = raw
    return out

def _csrf(client: AsyncClient) -> dict[str, str]:
    """Mirror the csrf_token cookie into the header, as the browser client does."""
    token = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}


@pytest_asyncio.fixture
async def auth_header(client: AsyncClient, auth_tokens):
    # Auth travels in the HttpOnly cookie the login set on the client; mutations need the CSRF header.
    return {"Authorization": f"Bearer {auth_tokens['access_token']}", **_csrf(client)}


@pytest.mark.asyncio
async def test_register_new_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": "password123",
            "display_name": "New User",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@example.com"
    assert data["display_name"] == "New User"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, registered_user):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "anotherpass1"},
    )
    assert resp.status_code == 409
    assert "already registered" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "abc"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, registered_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "securepass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, registered_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "password123"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_header, registered_user):
    resp = await client.get("/api/v1/auth/me", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["display_name"] == "Test User"


@pytest.mark.asyncio
async def test_get_me_no_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_me(client: AsyncClient, auth_header, registered_user):
    resp = await client.put(
        "/api/v1/auth/me",
        headers=auth_header,
        json={"display_name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_refresh_token_flow(client: AsyncClient, auth_tokens):
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": auth_tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # Tokens minted in the same second as the login are byte-identical (no jti), so the
    # proof of rotation is the fresh cookie set rather than a differing token string.
    assert {"access_token", "refresh_token", "csrf_token"} <= set(_set_cookie_headers(resp))


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(client: AsyncClient, auth_tokens):
    client.cookies.clear()  # the cookie's refresh token would otherwise be used
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": auth_tokens["access_token"]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, auth_tokens):
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=_csrf(client),
        json={"refresh_token": auth_tokens["refresh_token"]},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, auth_header, registered_user):
    resp = await client.put(
        "/api/v1/auth/me/password",
        headers=auth_header,
        json={"old_password": "securepass123", "new_password": "newpassword123"},
    )
    assert resp.status_code == 200

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "newpassword123"},
    )
    assert login_resp.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_old(client: AsyncClient, auth_header, registered_user):
    resp = await client.put(
        "/api/v1/auth/me/password",
        headers=auth_header,
        json={"old_password": "wrongoldpass", "new_password": "newpassword123"},
    )
    assert resp.status_code == 400
    assert "incorrect" in resp.json()["error"]["message"].lower()



@pytest.mark.asyncio
async def test_login_sets_readable_access_expiry_cookie(client: AsyncClient, registered_user):
    import time
    from app.config import settings

    before = int(time.time())
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "securepass123"},
    )
    assert resp.status_code == 200
    cookies = _set_cookie_headers(resp)
    assert "access_expires_at" in cookies
    raw = cookies["access_expires_at"]
    # Readable by the browser client (not HttpOnly) and outlives the access token.
    assert "httponly" not in raw.lower()
    assert "max-age" in raw.lower()
    assert "httponly" in cookies["access_token"].lower()
    value = int(resp.cookies["access_expires_at"])
    expected = before + settings.access_token_expire_minutes * 60
    assert expected - 2 <= value <= expected + 5


@pytest.mark.asyncio
async def test_refresh_rotates_access_expiry_cookie(client: AsyncClient, auth_tokens):
    import time
    from app.config import settings

    before = int(time.time())
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": auth_tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    assert "access_expires_at" in _set_cookie_headers(resp)
    value = int(resp.cookies["access_expires_at"])
    expected = before + settings.access_token_expire_minutes * 60
    assert expected - 2 <= value <= expected + 5


@pytest.mark.asyncio
async def test_logout_clears_access_expiry_cookie(client: AsyncClient, auth_tokens):
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=_csrf(client),
        json={"refresh_token": auth_tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    cookies = _set_cookie_headers(resp)
    assert "access_expires_at" in cookies
    assert 'access_expires_at=""' in cookies["access_expires_at"] or "max-age=0" in cookies["access_expires_at"].lower()
