"""Shared safeguard for MyŠkoda logins (#213).

Every user's login leaves from the same IP, so one misbehaving account can get all of them limited.
Škoda answers a limit with ``login.error.throttled`` and keeps extending it while we keep trying.

Rules, enforced in one place (SkodaAuthClient.login), for the collector, trip sync and the UI alike:
  * Škoda says "throttled": freeze **all** logins for 30 min, doubling on each repeat up to 6 h.
    Polling with a valid token needs no login and goes on.
  * Wrong password: counts one strike; 5 strikes in 30 min (any users) freeze all logins the same way.
  * Logins leave at most one per ``MIN_GAP_S`` seconds, so a restart cannot send a burst.
  * A person pressing Save/Retry gets one attempt per minute per vehicle.
State lives in Valkey (the API and the collector are separate containers); if Valkey is down it is
kept in this process instead, so the guard never becomes the reason a login is impossible.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from uuid import UUID

logger = logging.getLogger(__name__)

FIRST_FREEZE_S = 30 * 60
MAX_FREEZE_S = 6 * 3600
LEVEL_TTL_S = 12 * 3600           # repeats within this window lengthen the freeze
STRIKE_WINDOW_S = 30 * 60
STRIKES_TO_FREEZE = 5             # wrong-password strikes, across all users
MIN_GAP_S = 10.0
MAX_WAIT_FOR_SLOT_S = 30.0
MANUAL_GAP_S = 60

_K_FREEZE, _K_LEVEL, _K_STRIKES, _K_SLOT = (f"skoda:login:{n}" for n in ("freeze_until", "level", "strikes", "slot"))


class LoginError(RuntimeError):
    """A MyŠkoda login that did not work. Subclasses keep ``except RuntimeError`` callers working."""


class LoginThrottledError(LoginError):
    """Škoda is limiting logins, or we are holding them back. ``retry_after_s`` says for how long."""

    def __init__(self, retry_after_s: int, message: str | None = None):
        self.retry_after_s = max(1, int(retry_after_s))
        super().__init__(message or (
            f"Škoda is limiting logins right now. Try again in about {max(1, round(self.retry_after_s / 60))} min; "
            "repeated attempts make the limit longer."))


class LoginInvalidCredentialsError(LoginError):
    """Škoda rejected the email or password."""


# ── storage: Valkey, or this process when Valkey is unreachable ────────────────────────────
_mem: dict[str, tuple[str, float | None]] = {}


def _now() -> float:
    return time.time()


def _kv():
    try:
        from app.services.valkey_client import get_valkey
        return get_valkey()
    except Exception:  # noqa: BLE001
        return None


async def _get(key: str) -> str | None:
    kv = _kv()
    if kv is not None:
        try:
            return await kv.get(key)
        except Exception:  # noqa: BLE001
            logger.warning("login guard: Valkey unavailable, using process memory")
    item = _mem.get(key)
    if item and (item[1] is None or item[1] > _now()):
        return item[0]
    _mem.pop(key, None)
    return None


async def _set(key: str, value: str, ex: float | None = None, nx: bool = False) -> bool:
    kv = _kv()
    if kv is not None:
        try:
            return bool(await kv.set(key, value, px=int(ex * 1000) if ex else None, nx=nx))
        except Exception:  # noqa: BLE001
            logger.warning("login guard: Valkey unavailable, using process memory")
    if nx and await _get(key) is not None:
        return False
    _mem[key] = (value, _now() + ex if ex else None)
    return True


async def _del(key: str) -> None:
    kv = _kv()
    if kv is not None:
        try:
            await kv.delete(key)
        except Exception:  # noqa: BLE001
            pass
    _mem.pop(key, None)


# ── the rules ──────────────────────────────────────────────────────────────────────────────
async def frozen_for() -> int:
    """Seconds until logins are allowed again; 0 when they are."""
    raw = await _get(_K_FREEZE)
    return max(0, int(float(raw) - _now())) if raw else 0


async def _freeze(reason: str) -> int:
    level = int(await _get(_K_LEVEL) or 0)
    seconds = min(MAX_FREEZE_S, FIRST_FREEZE_S * 2 ** level)
    await _set(_K_FREEZE, str(_now() + seconds), ex=seconds)
    await _set(_K_LEVEL, str(level + 1), ex=LEVEL_TTL_S)
    await _del(_K_STRIKES)
    logger.error("MyŠkoda logins FROZEN for %d min (%s). Polling with valid tokens continues; no login is attempted.",
                 seconds // 60, reason)
    return seconds


async def before_login() -> None:
    """Call right before talking to Škoda's login. Raises LoginThrottledError while frozen; otherwise
    waits for this process's turn (one login per MIN_GAP_S across the app)."""
    left = await frozen_for()
    if left:
        raise LoginThrottledError(left)
    waited = 0.0
    while not await _set(_K_SLOT, "1", ex=MIN_GAP_S, nx=True):
        if waited >= MAX_WAIT_FOR_SLOT_S:
            raise LoginThrottledError(int(MIN_GAP_S), "MyŠkoda logins are busy right now; try again in a moment.")
        await asyncio.sleep(1.0)
        waited += 1.0
        left = await frozen_for()
        if left:
            raise LoginThrottledError(left)


async def record_throttled() -> int:
    """Škoda itself said 'throttled'. Returns the freeze length in seconds."""
    return await _freeze("Škoda reported login.error.throttled")


async def record_invalid_credentials() -> None:
    raw = await _get(_K_STRIKES)
    stamps = [t for t in (json.loads(raw) if raw else []) if t > _now() - STRIKE_WINDOW_S] + [_now()]
    if len(stamps) >= STRIKES_TO_FREEZE:
        await _freeze(f"{len(stamps)} rejected passwords in {STRIKE_WINDOW_S // 60} min")
    else:
        await _set(_K_STRIKES, json.dumps(stamps), ex=STRIKE_WINDOW_S)


async def record_success() -> None:
    await _del(_K_STRIKES)
    await _del(_K_LEVEL)


async def allow_manual_attempt(vehicle_id: UUID | str) -> int:
    """One person-triggered login per vehicle per minute. Returns 0 if allowed, else seconds to wait."""
    if await _set(f"skoda:login:manual:{vehicle_id}", "1", ex=MANUAL_GAP_S, nx=True):
        return 0
    return MANUAL_GAP_S
