"""Brute-force guard for iVDrive's own login, 2FA, recovery-code and password-reset endpoints.

There is no proxy in front of the API that limits requests, so this is the only limit. Counters
live in Valkey (process memory when Valkey is down, same fallback as login_guard) and are keyed
by what the attacker has to vary: the account (email or user id) and the caller's address.

  * account: 5 failures in 15 minutes lock that account's endpoint for 15 minutes
  * address: 30 failures in 15 minutes lock that address for 15 minutes
  * a success clears the account counter (the address counter keeps counting)

A locked attempt answers 429 with Retry-After and the same wording for every cause, so the
response does not say whether the account exists.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from app.services.login_guard import _del, _get, _set

logger = logging.getLogger(__name__)

WINDOW_S = 15 * 60
LOCK_S = 15 * 60
ACCOUNT_LIMIT = 5
ADDRESS_LIMIT = 30


def client_address(request: Request) -> str:
    """The caller's address as the API sees it. With no trusted proxy in front, the socket peer
    is the truth; a forwarded header from the client would be attacker-controlled."""
    return request.client.host if request.client else "unknown"


def _keys(scope: str, account: str | None, address: str) -> list[tuple[str, int]]:
    keys = [(f"auth:guard:{scope}:addr:{address}", ADDRESS_LIMIT)]
    if account:
        keys.insert(0, (f"auth:guard:{scope}:acct:{account.strip().lower()}", ACCOUNT_LIMIT))
    return keys


async def check(scope: str, account: str | None, request: Request) -> None:
    """Raise 429 when the account or the address is locked for this scope."""
    for key, _limit in _keys(scope, account, client_address(request)):
        if await _get(key + ":lock"):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Try again in a few minutes.",
                headers={"Retry-After": str(LOCK_S)},
            )


async def failed(scope: str, account: str | None, request: Request) -> None:
    """Count one failure; lock the key when it reaches its limit inside the window."""
    for key, limit in _keys(scope, account, client_address(request)):
        raw = await _get(key)
        count = int(raw) + 1 if raw else 1
        await _set(key, str(count), ex=WINDOW_S)
        if count >= limit:
            await _set(key + ":lock", "1", ex=LOCK_S)
            await _del(key)
            logger.warning("auth guard: %s locked for %d min after %d failures (%s)",
                           scope, LOCK_S // 60, count, "account" if ":acct:" in key else "address")


async def succeeded(scope: str, account: str | None) -> None:
    """A correct password or code clears the account counter."""
    if account:
        key = f"auth:guard:{scope}:acct:{account.strip().lower()}"
        await _del(key)
        await _del(key + ":lock")
