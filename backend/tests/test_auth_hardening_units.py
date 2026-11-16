"""v1.4.0 auth hardening, unit level: the brute-force guard, token versioning, keyed recovery
codes, placeholder secrets and the bcrypt input limit."""

import pytest

from app import security
from app.config import _is_placeholder_secret, _is_short_secret, settings
from app.services import auth_guard


class _Req:
    def __init__(self, host="93.184.216.34", xff=None):
        self.client = type("C", (), {"host": host})()
        self.headers = {"x-forwarded-for": xff} if xff else {}


@pytest.fixture(autouse=True)
def memory_store(monkeypatch):
    """No Valkey: the guard keeps its counters in process memory, which each test starts empty."""
    monkeypatch.setattr(auth_guard, "_kv", lambda: None)
    auth_guard._mem.clear()
    yield
    auth_guard._mem.clear()


async def _tries(scope, account, req, n):
    ok = 0
    for _ in range(n):
        try:
            await auth_guard.begin(scope, account, req)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            assert exc.status_code == 429
    return ok


@pytest.mark.asyncio
async def test_five_attempts_per_account_and_address_then_429_with_retry_after():
    req = _Req()
    assert await _tries("login", "Person@Example.com", req, 5) == 5
    with pytest.raises(Exception) as exc_info:
        await auth_guard.begin("login", "person@example.com", req)    # case-insensitive account
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == str(auth_guard.WINDOW_S)
    await auth_guard.begin("login", "other@example.com", req)         # another account is untouched


@pytest.mark.asyncio
async def test_an_attacker_elsewhere_cannot_lock_the_victim_out_from_the_victims_address():
    victim_home = _Req("5.9.12.200")
    attacker = _Req("45.33.32.156")
    assert await _tries("login", "victim@example.com", attacker, 50) == 5   # attacker is stopped at 5
    await auth_guard.begin("login", "victim@example.com", victim_home)     # the victim still gets in


@pytest.mark.asyncio
async def test_a_distributed_guess_at_one_account_is_bounded_across_addresses():
    ok = 0
    for i in range(auth_guard.ACCOUNT_LIMIT + 10):
        ok += await _tries("2fa", "user-id-1", _Req(f"5.9.13.{i + 1}"), 1)
    assert ok == auth_guard.ACCOUNT_LIMIT


@pytest.mark.asyncio
async def test_parallel_requests_cannot_slip_past_the_limit():
    """200 simultaneous attempts: the count is taken before the slow password check, atomically,
    so exactly the first five are let through."""
    import asyncio
    req = _Req()
    results = await asyncio.gather(*[_tries("login", "burst@example.com", req, 1) for _ in range(200)])
    assert sum(results) == auth_guard.ACCOUNT_ADDRESS_LIMIT


@pytest.mark.asyncio
async def test_a_success_clears_the_account_counters_but_the_address_keeps_counting():
    req = _Req()
    assert await _tries("login", "me@example.com", req, 4) == 4
    await auth_guard.succeeded("login", "me@example.com", req)
    assert await _tries("login", "me@example.com", req, 5) == 5
    assert auth_guard._mem[f"auth:guard:login:addr:{auth_guard.client_address(req)}"][0] == 9


@pytest.mark.asyncio
async def test_scopes_are_independent():
    req = _Req()
    assert await _tries("2fa", "user-id-1", req, 10) == 5
    await auth_guard.begin("login", "user-id-1", req)


def test_client_address_comes_from_the_right_of_x_forwarded_for_skipping_our_own_hops():
    # the web container (172.18.0.7) is the socket peer; Next appends the address it saw
    assert auth_guard.client_address(_Req("172.18.0.7", "8.8.4.4")) == "8.8.4.4"
    # a spoofed left-hand entry is never reached
    assert auth_guard.client_address(_Req("172.18.0.7", "1.2.3.4, 8.8.4.4")) == "8.8.4.4"
    # a reverse proxy in front adds its own private hop to the right
    assert auth_guard.client_address(_Req("172.18.0.7", "8.8.4.4, 10.0.0.2")) == "8.8.4.4"
    # no header: the peer
    assert auth_guard.client_address(_Req("172.18.0.7")) == "172.18.0.7"
    assert auth_guard.client_address(_Req("172.18.0.7", "garbage, not-an-ip")) == "172.18.0.7"


@pytest.mark.asyncio
async def test_users_behind_the_same_web_container_do_not_share_a_counter():
    a = _Req("172.18.0.7", "8.8.4.4")
    b = _Req("172.18.0.7", "8.8.8.8")
    assert await _tries("login", "x@example.com", a, 10) == 5
    await auth_guard.begin("login", "y@example.com", b)


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
    ("x" * 31, False),     # short but not a placeholder: warned about, not refused
    ("k7Qn2vP9sL4mZ8wR1tY6uA3bC5dE0fG2hJ4kL6mN8pQ0", False),
])
def test_placeholder_secrets_are_recognised(value, placeholder):
    assert _is_placeholder_secret(value) is placeholder


def test_short_keys_are_flagged_for_a_warning_not_refused():
    assert _is_short_secret("x" * 31) and not _is_short_secret("x" * 32)
    assert not _is_placeholder_secret("openssl-rand-base64-16-ab")   # 24 chars from an old install


def test_password_byte_limit_matches_bcrypt():
    assert security.password_fits("a" * 72)
    assert not security.password_fits("a" * 73)
    assert not security.password_fits("ä" * 40)   # 80 bytes


def test_a_public_peer_means_no_proxy_of_ours_so_the_header_is_ignored():
    assert auth_guard.client_address(_Req("93.184.216.34", "8.8.4.4")) == "93.184.216.34"


def test_only_globally_routable_addresses_count_as_a_client():
    assert auth_guard.client_address(_Req("172.18.0.7", "224.0.0.1")) == "172.18.0.7"      # multicast
    assert auth_guard.client_address(_Req("172.18.0.7", "0.0.0.0")) == "172.18.0.7"        # unspecified
    assert auth_guard.client_address(_Req("172.18.0.7", "8.8.4.4, 224.0.0.1")) == "8.8.4.4"


@pytest.mark.asyncio
async def test_the_valkey_counter_opens_its_window_and_counts_in_one_transaction(monkeypatch):
    calls = []

    class Pipe:
        def __init__(self): self.ops = []
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def set(self, key, value, ex=None, nx=False): self.ops.append(("set", key, ex, nx))
        def incr(self, key): self.ops.append(("incr", key))
        async def execute(self):
            calls.append(list(self.ops))
            return [True, 7]

    class KV:
        def pipeline(self, transaction=True):
            assert transaction is True
            return Pipe()

    monkeypatch.setattr(auth_guard, "_kv", lambda: KV())
    assert await auth_guard._incr("k") == 7
    assert calls == [[("set", "k", auth_guard.WINDOW_S, True), ("incr", "k")]]
