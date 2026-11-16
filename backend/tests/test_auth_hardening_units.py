"""v1.4.0 auth hardening, unit level: the brute-force guard, token versioning, keyed recovery
codes, placeholder secrets and the bcrypt input limit."""

import pytest

from app import security
from app.config import _is_placeholder_secret, settings
from app.services import auth_guard, login_guard


class _Req:
    def __init__(self, host="203.0.113.7"):
        self.client = type("C", (), {"host": host})()


@pytest.fixture(autouse=True)
def memory_store(monkeypatch):
    """No Valkey: the guard keeps its counters in process memory, which each test starts empty."""
    monkeypatch.setattr(login_guard, "_kv", lambda: None)
    login_guard._mem.clear()
    yield
    login_guard._mem.clear()


@pytest.mark.asyncio
async def test_account_locks_after_five_failures_and_a_success_clears_it():
    req = _Req()
    for _ in range(auth_guard.ACCOUNT_LIMIT - 1):
        await auth_guard.failed("login", "Person@Example.com", req)
        await auth_guard.check("login", "person@example.com", req)  # still allowed
    await auth_guard.failed("login", "person@example.com", req)
    with pytest.raises(Exception) as exc_info:
        await auth_guard.check("login", "person@example.com", req)
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == str(auth_guard.LOCK_S)
    # another account from the same address is still fine below the address limit
    await auth_guard.check("login", "other@example.com", req)
    await auth_guard.succeeded("login", "person@example.com")
    await auth_guard.check("login", "person@example.com", req)


@pytest.mark.asyncio
async def test_address_locks_after_thirty_failures_across_accounts():
    req = _Req("198.51.100.9")
    for i in range(auth_guard.ADDRESS_LIMIT):
        await auth_guard.failed("login", f"u{i}@example.com", req)
    with pytest.raises(Exception) as exc_info:
        await auth_guard.check("login", "fresh@example.com", req)
    assert exc_info.value.status_code == 429
    await auth_guard.check("login", "fresh@example.com", _Req("198.51.100.10"))  # other address


@pytest.mark.asyncio
async def test_scopes_are_independent():
    req = _Req()
    for _ in range(auth_guard.ACCOUNT_LIMIT):
        await auth_guard.failed("2fa", "user-id-1", req)
    with pytest.raises(Exception):
        await auth_guard.check("2fa", "user-id-1", req)
    await auth_guard.check("login", "user-id-1", req)


def test_tokens_carry_the_version_and_old_tokens_are_refused(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "unit-test-secret-not-used-anywhere-else-0123456789")
    tok = security.create_access_token("u1", token_version=3)
    payload = security.decode_token(tok)
    assert payload["tv"] == 3
    assert security.token_matches_user(payload, 3)
    assert not security.token_matches_user(payload, 4)   # password changed since
    assert not security.token_matches_user({"sub": "u1", "type": "access"}, 1)  # pre-v1.4.0 token


def test_recovery_codes_are_keyed_and_legacy_hashes_still_match(monkeypatch):
    from app.api.v1 import auth
    from app.services.crypto import hash_field
    monkeypatch.setattr(settings, "encryption_key", "unit-test-encryption-key-0123456789abcdef")
    new = auth._hash_recovery_code("abcd1234")
    assert new.startswith("v2:") and new != hash_field("ABCD1234")
    assert auth._recovery_code_matches(" abcd1234 ", new)
    assert not auth._recovery_code_matches("abcd1235", new)
    legacy = hash_field("ABCD1234")
    assert auth._recovery_code_matches("abcd1234", legacy)
    # a different server key gives a different hash: a dump without the key is useless
    monkeypatch.setattr(settings, "encryption_key", "another-key-0123456789abcdef0123456789")
    assert auth._hash_recovery_code("abcd1234") != new


@pytest.mark.parametrize("value, placeholder", [
    ("CHANGE_ME_TO_RANDOM_64_CHAR_STRING", True),
    ("change_me", True),
    ("secret", True),
    ("x" * 31, True),
    ("k7Qn2vP9sL4mZ8wR1tY6uA3bC5dE0fG2hJ4kL6mN8pQ0", False),
])
def test_placeholder_secrets_are_recognised(value, placeholder):
    assert _is_placeholder_secret(value) is placeholder


def test_password_byte_limit_matches_bcrypt():
    assert security.password_fits("a" * 72)
    assert not security.password_fits("a" * 73)
    assert not security.password_fits("ä" * 40)   # 80 bytes
