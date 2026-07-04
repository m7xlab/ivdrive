"""Per-user chat sessions list cache (Valkey read-through).

The chat widget calls GET /api/v1/chat/sessions on widget open and after
every chat completion. With many sessions per user, the query joins
chat_sessions + chat_messages with a GROUP BY — fast individually (~10ms)
but unnecessary on every refresh when the data rarely changes second-by-second.

This module wraps the read with a Valkey read-through cache (TTL 60s) and
exposes an invalidate(key) helper for write paths.

Cache key:   chat:sessions:<user_id>
Value:       JSON-encoded list of session dicts
TTL:         60 seconds (short — sessions feel "live" but the DB is shielded
             from widget-open + post-chat refetches)
Invalidate:  after chat() / chat_stream() writes new messages, after
             delete_session() / delete_all_sessions()
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.events import get_valkey_client

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60
KEY_PREFIX = "chat:sessions:"


def _key(user_id: str) -> str:
    return f"{KEY_PREFIX}{user_id}"


async def get(user_id: str) -> list[dict[str, Any]] | None:
    """Return cached sessions list for user_id, or None on miss/error.

    Note: timestamps come back as ISO strings (JSON has no datetime type).
    The chat list_sessions endpoint pre-converts timestamps to .isoformat()
    before calling set(), so the cached shape matches what the API always
    returned. PR Agent #166 — also defensively reject non-list shapes
    (e.g. stale foreign values) by treating them as a cache miss.
    """
    try:
        client = await get_valkey_client()
        raw = await client.get(_key(user_id))
        if raw is None:
            return None
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            logger.debug("sessions cache get: unexpected shape for %s, treating as miss", user_id)
            return None
        return parsed
    except Exception as exc:  # never let cache outage break the API
        logger.debug("sessions cache get failed for %s: %s", user_id, exc)
        return None


async def set(user_id: str, value: list[dict[str, Any]]) -> None:
    """Store sessions list for user_id with TTL. Best-effort.

    `value` should already be JSON-safe (datetimes as .isoformat()). The
    `default=str` fallback here is defense in depth in case a future caller
    passes a datetime.
    """
    try:
        client = await get_valkey_client()
        payload = json.dumps(value, default=str)
        await client.set(_key(user_id), payload, ex=CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.debug("sessions cache set failed for %s: %s", user_id, exc)


async def invalidate(user_id: str) -> None:
    """Drop the cached list for user_id. Call from every write path."""
    try:
        client = await get_valkey_client()
        await client.delete(_key(user_id))
    except Exception as exc:
        logger.debug("sessions cache invalidate failed for %s: %s", user_id, exc)
