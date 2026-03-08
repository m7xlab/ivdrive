"""Valkey pub/sub event bus for inter-service communication.

API pods publish vehicle lifecycle events; collector pods subscribe and
react by registering/unregistering APScheduler jobs in real time.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import valkey.asyncio as valkey

from app.config import settings

logger = logging.getLogger(__name__)

CHANNEL_VEHICLE_EVENTS = "ivdrive:vehicle_events"


def _valkey_url() -> str:
    url = settings.valkey_url
    if url.startswith("valkey://"):
        url = "redis://" + url[len("valkey://"):]
    return url


async def get_valkey_client(**kwargs) -> valkey.Valkey:
    return valkey.from_url(_valkey_url(), decode_responses=True, **kwargs)


async def get_valkey_pubsub_client() -> valkey.Valkey:
    """Client with no socket timeout, suitable for blocking pub/sub listeners."""
    return valkey.from_url(
        _valkey_url(), decode_responses=True, socket_timeout=None
    )


async def publish_event(event_type: str, payload: dict[str, Any]) -> None:
    message = json.dumps({"type": event_type, **payload})
    client = await get_valkey_client()
    try:
        await client.publish(CHANNEL_VEHICLE_EVENTS, message)
        logger.info("Published event %s: %s", event_type, payload.get("vehicle_id", ""))
    finally:
        await client.aclose()


async def publish_vehicle_linked(vehicle_id: str, interval: int) -> None:
    await publish_event("vehicle_linked", {
        "vehicle_id": vehicle_id,
        "interval": interval,
    })


async def publish_vehicle_updated(vehicle_id: str, interval: int, enabled: bool) -> None:
    await publish_event("vehicle_updated", {
        "vehicle_id": vehicle_id,
        "interval": interval,
        "enabled": enabled,
    })


async def publish_vehicle_deleted(vehicle_id: str) -> None:
    await publish_event("vehicle_deleted", {"vehicle_id": vehicle_id})


async def publish_vehicle_refresh(vehicle_id: str) -> None:
    """Queue a manual refresh request via a persistent Valkey List.

    Uses RPUSH instead of pub/sub so the request survives listener crashes
    and is processed within ~5 seconds by the collector's queue-drain job.
    """
    client = await get_valkey_client()
    try:
        await client.rpush("ivdrive:manual_refresh", vehicle_id)
        logger.info("Queued manual refresh for vehicle %s", vehicle_id)
    finally:
        await client.aclose()
