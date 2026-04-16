import json
import logging
from typing import Any, Optional
import valkey.asyncio as valkey
from app.config import settings

logger = logging.getLogger(__name__)

valkey_client: Optional[valkey.Valkey] = None

def _valkey_url() -> str:
    url = settings.valkey_url
    if url.startswith("valkey://"):
        url = "redis://" + url[len("valkey://"):]
    return url

async def init_cache() -> None:
    global valkey_client
    if valkey_client is None:
        valkey_client = valkey.from_url(_valkey_url(), decode_responses=True)
        logger.info("Valkey cache connection pool initialized.")

async def close_cache() -> None:
    global valkey_client
    if valkey_client is not None:
        await valkey_client.aclose()
        valkey_client = None
        logger.info("Valkey cache connection pool closed.")

async def cache_get(key: str) -> Optional[Any]:
    if not valkey_client:
        return None
    try:
        val = await valkey_client.get(key)
        if val:
            return json.loads(val)
        return None
    except Exception as e:
        logger.error(f"Valkey cache get failed: {e}")
        return None

async def cache_set(key: str, value: Any, expire_seconds: int = 60) -> None:
    if not valkey_client:
        return
    try:
        await valkey_client.setex(key, expire_seconds, json.dumps(value))
    except Exception as e:
        logger.error(f"Valkey cache set failed: {e}")

async def invalidate_vehicle_cache(vehicle_id: str) -> None:
    if not valkey_client:
        return
    try:
        pattern = f"ivdrive:api:cache:*/vehicles/{vehicle_id}*"
        cursor = '0'
        while cursor != '0':
            cursor, keys = await valkey_client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await valkey_client.delete(*keys)
    except Exception as e:
        logger.error(f"Valkey cache invalidation failed: {e}")
