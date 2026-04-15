import json
import logging
from typing import Any, Optional
import valkey.asyncio as valkey
from app.config import settings

logger = logging.getLogger(__name__)

def _valkey_url() -> str:
    url = settings.valkey_url
    if url.startswith("valkey://"):
        url = "redis://" + url[len("valkey://"):]
    return url

async def get_valkey_client(**kwargs) -> valkey.Valkey:
    return valkey.from_url(_valkey_url(), decode_responses=True, **kwargs)

async def cache_get(key: str) -> Optional[Any]:
    try:
        client = await get_valkey_client()
        val = await client.get(key)
        await client.aclose()
        if val:
            return json.loads(val)
        return None
    except Exception as e:
        logger.error(f"Valkey cache get failed: {e}")
        return None

async def cache_set(key: str, value: Any, expire_seconds: int = 60) -> None:
    try:
        client = await get_valkey_client()
        await client.setex(key, expire_seconds, json.dumps(value))
        await client.aclose()
    except Exception as e:
        logger.error(f"Valkey cache set failed: {e}")

async def invalidate_vehicle_cache(vehicle_id: str) -> None:
    """Invalidate all cached API responses for a specific vehicle."""
    try:
        client = await get_valkey_client()
        # Scan for keys matching the vehicle prefix
        pattern = f"ivdrive:api:cache:vehicles:{vehicle_id}:*"
        cursor = '0'
        while cursor != 0:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await client.delete(*keys)
        await client.aclose()
    except Exception as e:
        logger.error(f"Valkey cache invalidation failed: {e}")
