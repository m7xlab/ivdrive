"""Brute-force guard for iVDrive's own login, 2FA, recovery-code, password and reset endpoints.

Every attempt is counted *before* the password or code is checked, with an atomic increment, so a
burst of parallel requests cannot all slip past a check that runs first and a count that runs after.
Counters live in Valkey (process memory when Valkey is down, like login_guard).

Three counters per scope, each over a fixed 15-minute window that the first attempt opens:

  * account + address: 5.   One person mistyping, or one attacker at one address, hits this first.
                            Because the address is part of the key, an attacker elsewhere cannot lock
                            a victim out by failing against the victim's account from their own address.
  * account, any address: 20. Bounds a distributed guess at one account (TOTP has about 3 valid codes
                            per 30 s, so 20 guesses per window is a negligible chance).
  * address: 100.           Bounds one address across accounts; generous because several people can
                            share one (home or office network).

A success clears the account counters. Blocked attempts keep the window they were counted in, so
hammering a locked endpoint cannot extend the lock, and an attempt stops counting at the first counter it exceeds (so one attacker cannot fill the account-wide counter). The refusal is a 429 with the same wording for
every cause, so it does not say whether an account exists.
"""
from __future__ import annotations

import ipaddress
import logging
import time

from fastapi import HTTPException, Request, status

from app.services.login_guard import _kv

logger = logging.getLogger(__name__)

WINDOW_S = 15 * 60
ACCOUNT_ADDRESS_LIMIT = 5
ACCOUNT_LIMIT = 20
ADDRESS_LIMIT = 100

_mem: dict[str, tuple[int, float]] = {}


def client_address(request: Request) -> str:
    """The caller's address. The web app proxies /api through Next.js, so the socket peer is the web
    container for every browser; the real address arrives in X-Forwarded-For. Entries are read from
    the right, skipping private and loopback hops (our own containers and proxies), and the first
    public one is used. Anything a client puts at the left of the header is never reached, so it
    cannot be spoofed to dodge or to pile onto someone else's counter."""
    for hop in reversed([h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]):
        try:
            ip = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if not (ip.is_private or ip.is_loopback or ip.is_link_local):
            return str(ip)
    return request.client.host if request.client else "unknown"


def _keys(scope: str, account: str | None, address: str) -> list[tuple[str, int]]:
    keys = [(f"auth:guard:{scope}:addr:{address}", ADDRESS_LIMIT)]
    if account:
        who = account.strip().lower()
        keys.insert(0, (f"auth:guard:{scope}:acct:{who}", ACCOUNT_LIMIT))
        keys.insert(0, (f"auth:guard:{scope}:pair:{who}:{address}", ACCOUNT_ADDRESS_LIMIT))
    return keys


async def _incr(key: str) -> int:
    """Atomic increment inside a fixed window; returns the new count."""
    kv = _kv()
    if kv is not None:
        try:
            await kv.set(key, 0, ex=WINDOW_S, nx=True)   # opens the window; no-op while one is open
            return int(await kv.incr(key))
        except Exception:  # noqa: BLE001
            logger.warning("auth guard: Valkey unavailable, using process memory")
    now = time.time()
    count, expires = _mem.get(key, (0, 0.0))
    if expires <= now:
        count, expires = 0, now + WINDOW_S
    _mem[key] = (count + 1, expires)
    return count + 1


async def _drop(key: str) -> None:
    kv = _kv()
    if kv is not None:
        try:
            await kv.delete(key)
        except Exception:  # noqa: BLE001
            pass
    _mem.pop(key, None)


async def begin(scope: str, account: str | None, request: Request) -> None:
    """Count this attempt; raise 429 as soon as a counter is over its limit.

    The counters are tried narrowest first (account + address, then account, then address) and an
    attempt stops counting at the first one it exceeds. That is what keeps one attacker's endless
    attempts from filling the account-wide counter and locking the real owner out."""
    for key, limit in _keys(scope, account, client_address(request)):
        if await _incr(key) > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Try again in a few minutes.",
                headers={"Retry-After": str(WINDOW_S)},
            )


async def succeeded(scope: str, account: str | None, request: Request) -> None:
    """A correct password or code clears this account's counters (the address counter keeps counting)."""
    if not account:
        return
    who = account.strip().lower()
    await _drop(f"auth:guard:{scope}:acct:{who}")
    await _drop(f"auth:guard:{scope}:pair:{who}:{client_address(request)}")
