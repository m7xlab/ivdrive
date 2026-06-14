"""
Valkey client wrapper — session-scoped flags for KV cache management.
"""
import logging
from typing import Optional
import valkey.asyncio as valkey

from app.config import settings

logger = logging.getLogger(__name__)

_valkey_client: Optional[valkey.Valkey] = None


def _valkey_url() -> str:
    url = settings.valkey_url
    if url.startswith("valkey://"):
        url = "redis://" + url[len("valkey://"):]
    return url


def get_valkey() -> valkey.Valkey:
    """Get or create the shared Valkey client (async)."""
    global _valkey_client
    if _valkey_client is None:
        _valkey_client = valkey.from_url(_valkey_url(), decode_responses=True)
    return _valkey_client


async def get_session_flag(session_id: str, key: str) -> Optional[str]:
    """
    Get a session-scoped flag from Valkey.
    Returns None if not set or expired.
    """
    try:
        client = get_valkey()
        full_key = f"chat_session:{session_id}:{key}"
        return await client.get(full_key)
    except Exception as e:
        logger.warning(f"Valkey get_session_flag error: {e}")
        return None


async def set_session_flag(session_id: str, key: str, value: str, ttl_seconds: int = 86400) -> None:
    """Set a session-scoped flag in Valkey with a TTL."""
    try:
        client = get_valkey()
        full_key = f"chat_session:{session_id}:{key}"
        await client.setex(full_key, ttl_seconds, value)
    except Exception as e:
        logger.warning(f"Valkey set_session_flag error: {e}")