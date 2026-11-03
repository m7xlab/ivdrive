"""#213: one account's login trouble must not get every user limited (shared IP)."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.services import login_guard as g
from app.services import skoda_lifecycle as lc
from app.services.skoda_auth import SkodaAuthClient


@pytest.fixture(autouse=True)
def _memory_state(monkeypatch):
    """Process memory instead of Valkey, a controllable clock, and no real waiting."""
    g._mem.clear()
    clock = SimpleNamespace(t=1_000_000.0)
    monkeypatch.setattr(g, "_kv", lambda: None)
    monkeypatch.setattr(g, "_now", lambda: clock.t)

    async def fake_sleep(s):
        clock.t += s
    monkeypatch.setattr(g.asyncio, "sleep", fake_sleep)
    return clock


@pytest.fixture
def clock(_memory_state):
    return _memory_state


def _client_whose_login_says(monkeypatch, outcome):
    """SkodaAuthClient._login stand-in: returns tokens or raises `outcome`; counts requests to Škoda."""
    calls = []

    async def fake(self, username, password):
        calls.append(1)
        if isinstance(outcome, Exception):
            raise outcome
        return {"accessToken": "a", "refreshToken": "r"}
    monkeypatch.setattr(SkodaAuthClient, "_login", fake)
    return calls


@pytest.mark.asyncio
async def test_throttle_freezes_all_logins_and_sends_nothing_while_frozen(monkeypatch, clock):
    calls = _client_whose_login_says(monkeypatch, g.LoginThrottledError(1800))
    with pytest.raises(g.LoginThrottledError):
        await SkodaAuthClient().login("a@x", "pw")
    assert len(calls) == 1 and await g.frozen_for() > 0
    for _ in range(5):                                   # other users / the collector / trip sync
        clock.t += 60
        with pytest.raises(g.LoginThrottledError) as e:
            await SkodaAuthClient().login("b@x", "pw")
        assert e.value.retry_after_s > 0
    assert len(calls) == 1                               # not one more request reached Škoda


@pytest.mark.asyncio
async def test_freeze_grows_on_repeat_and_ends(monkeypatch, clock):
    first = await g.record_throttled()
    clock.t += first + 1
    assert await g.frozen_for() == 0
    second = await g.record_throttled()
    assert (first, second) == (1800, 3600)
    for _ in range(6):
        await g.record_throttled()
    assert await g.record_throttled() == g.MAX_FREEZE_S


@pytest.mark.asyncio
async def test_success_clears_the_penalty(monkeypatch, clock):
    await g.record_throttled()
    clock.t += 1801
    _client_whose_login_says(monkeypatch, None)
    await SkodaAuthClient().login("a@x", "pw")
    assert await g.record_throttled() == g.FIRST_FREEZE_S    # back to the first step, not doubled


@pytest.mark.asyncio
async def test_wrong_passwords_freeze_everyone_only_after_five(monkeypatch, clock):
    calls = _client_whose_login_says(monkeypatch, g.LoginInvalidCredentialsError("Password is invalid"))
    for _ in range(g.STRIKES_TO_FREEZE - 1):
        clock.t += 15
        with pytest.raises(g.LoginInvalidCredentialsError):
            await SkodaAuthClient().login("a@x", "bad")
    assert await g.frozen_for() == 0
    clock.t += 15
    with pytest.raises(g.LoginInvalidCredentialsError):
        await SkodaAuthClient().login("a@x", "bad")
    assert await g.frozen_for() > 0 and len(calls) == g.STRIKES_TO_FREEZE


@pytest.mark.asyncio
async def test_logins_leave_at_most_one_per_gap(monkeypatch, clock):
    _client_whose_login_says(monkeypatch, None)
    await SkodaAuthClient().login("a@x", "pw")
    t0 = clock.t
    await SkodaAuthClient().login("b@x", "pw")           # has to wait for its turn
    assert clock.t - t0 >= g.MIN_GAP_S - 1


@pytest.mark.asyncio
async def test_a_person_gets_one_attempt_per_minute_per_car(clock):
    assert await g.allow_manual_attempt("car-1") == 0
    assert await g.allow_manual_attempt("car-1") == g.MANUAL_GAP_S
    assert await g.allow_manual_attempt("car-2") == 0
    clock.t += g.MANUAL_GAP_S + 1
    assert await g.allow_manual_attempt("car-1") == 0


# ── per-vehicle behaviour in the token lifecycle ──────────────────────────────────────────
class _Session:
    def __init__(self): self.added = []
    def add(self, o): self.added.append(o)


def _cs(**kw):
    base = dict(id="cs-1", status="active", secure_mode=True, backoff_until=None, consecutive_auth_failures=0,
                access_token_encrypted="x", refresh_token_encrypted="y",
                token_expires_at=datetime.now(UTC) - timedelta(hours=1), needs_user_reauth_reason=None,
                last_auth_error=None, last_auth_at=None, last_auth_method=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _expired_refresh_then(monkeypatch, login_outcome):
    """Refresh answers 400 (as in the production log), then the silent login does `login_outcome`."""
    monkeypatch.setattr(lc, "decrypt_field", lambda v: v)

    class Fake:
        async def refresh(self, token):
            req = httpx.Request("POST", "https://x")
            raise httpx.HTTPStatusError("400", request=req, response=httpx.Response(400, request=req))

        async def login(self, u, p):
            raise login_outcome

        async def close(self): pass
    monkeypatch.setattr(lc, "SkodaAuthClient", Fake)


@pytest.mark.asyncio
async def test_throttled_vehicle_is_deferred_not_marked_for_reauth(monkeypatch):
    _expired_refresh_then(monkeypatch, g.LoginThrottledError(1800))
    cs = _cs()
    with pytest.raises(lc.LoginDeferred) as e:
        await lc.SkodaTokenLifecycle(_Session()).ensure_valid_token(cs, "u", "p")
    assert cs.status == "active" and cs.needs_user_reauth_reason is None      # the user is not blamed
    assert cs.backoff_until and e.value.retry_after_s >= 1800
    with pytest.raises(lc.LoginDeferred):                                       # cooling down: no request at all
        await lc.SkodaTokenLifecycle(_Session()).ensure_valid_token(cs, "u", "p")


@pytest.mark.asyncio
async def test_wrong_password_suspends_the_vehicle_on_the_first_strike(monkeypatch):
    _expired_refresh_then(monkeypatch, g.LoginInvalidCredentialsError("Password is invalid"))
    cs = _cs()
    with pytest.raises(lc.AuthRequiredError):
        await lc.SkodaTokenLifecycle(_Session()).ensure_valid_token(cs, "u", "p")
    assert cs.status == "auth_failed" and "Settings" in cs.needs_user_reauth_reason


@pytest.mark.asyncio
async def test_other_login_failures_suspend_on_the_third_strike(monkeypatch):
    _expired_refresh_then(monkeypatch, g.LoginError("Skoda requires accepting Terms & Conditions."))
    cs = _cs()
    for n in (1, 2):
        with pytest.raises(lc.LoginDeferred):
            await lc.SkodaTokenLifecycle(_Session()).ensure_valid_token(cs, "u", "p")
        assert cs.status == "active" and cs.consecutive_auth_failures == n
    with pytest.raises(lc.AuthRequiredError):
        await lc.SkodaTokenLifecycle(_Session()).ensure_valid_token(cs, "u", "p")
    assert cs.status == "auth_failed"


@pytest.mark.asyncio
async def test_trip_sync_style_caller_never_logs_in(monkeypatch):
    _expired_refresh_then(monkeypatch, AssertionError("a login was attempted"))
    cs = _cs()
    with pytest.raises(lc.LoginDeferred):
        await lc.SkodaTokenLifecycle(_Session()).ensure_valid_token(cs, "u", "p", allow_login=False)
