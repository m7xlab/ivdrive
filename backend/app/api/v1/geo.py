import asyncio
import logging
import math
import time
from decimal import ROUND_HALF_UP, Decimal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.cache import cache_get, cache_set

router = APIRouter()
logger = logging.getLogger(__name__)

# ~1.1 m precision; frontend coordKey uses toFixed(5) (half-up).
GEO_QUANTIZE = Decimal("0.00001")
GEO_CACHE_PREFIX = "ivdrive:geo:reverse:"
GEO_CACHE_TTL_SECONDS = 90 * 24 * 3600
# ~110 m: reuse a street name for nearby GPS jitter from the same driveway.
GEO_NEARBY_DELTA = Decimal("0.001")
COOLDOWN_KEY = "ivdrive:geo:nominatim:cooldown"

NOMINATIM_MIN_INTERVAL = 1.1
NOMINATIM_MAX_COOLDOWN = 300.0
PHOTON_MIN_INTERVAL = 1.1

_nominatim_lock = asyncio.Lock()
_photon_lock = asyncio.Lock()
_inflight: dict[str, asyncio.Future[tuple[str, int | None]]] = {}
_next_allowed = 0.0
_photon_next_allowed = 0.0
_failures = 0


class GeoRequest(BaseModel):
    latitude: float
    longitude: float


class GeoResponse(BaseModel):
    display_name: str
    retry_after_seconds: int | None = None


def _rounded_coord(value: float) -> Decimal:
    return Decimal(str(value)).quantize(GEO_QUANTIZE, rounding=ROUND_HALF_UP)


def _valkey_key(lat: Decimal, lon: Decimal) -> str:
    return f"{GEO_CACHE_PREFIX}{lat},{lon}"


def _is_useful_name(name: str | None) -> bool:
    return bool(name) and name not in ("Location", "Unknown Location")


def _short_name(data: dict) -> str:
    address = data.get("address") or {}
    road = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
        or address.get("path")
        or address.get("cycleway")
    )
    house_number = address.get("house_number")
    if road:
        return f"{road} {house_number}".strip() if house_number else road
    for key in (
        "neighbourhood",
        "suburb",
        "hamlet",
        "village",
        "town",
        "city",
        "municipality",
        "county",
    ):
        if address.get(key):
            return str(address[key])
    display = data.get("display_name")
    if isinstance(display, str) and display.strip():
        return display.split(",")[0].strip()
    return "Unknown Location"


def _short_name_photon(data: dict) -> str:
    features = data.get("features") or []
    if not features:
        return "Unknown Location"
    props = features[0].get("properties") or {}
    street = props.get("street") or props.get("name")
    house = props.get("housenumber")
    if street:
        return f"{street} {house}".strip() if house else str(street)
    for key in ("district", "city", "locality", "county", "state"):
        if props.get(key):
            return str(props[key])
    return "Unknown Location"


async def _remember(lat: Decimal, lon: Decimal, name: str, db: AsyncSession) -> None:
    if not _is_useful_name(name):
        return
    await cache_set(_valkey_key(lat, lon), name, expire_seconds=GEO_CACHE_TTL_SECONDS)
    await db.execute(
        text(
            "INSERT INTO geocoded_locations (latitude, longitude, display_name) "
            "VALUES (:lat, :lon, :name) "
            "ON CONFLICT (latitude, longitude) DO UPDATE "
            "SET display_name = EXCLUDED.display_name "
            "WHERE geocoded_locations.display_name IN ('Location', 'Unknown Location') "
            "OR geocoded_locations.display_name IS DISTINCT FROM EXCLUDED.display_name"
        ),
        {"lat": lat, "lon": lon, "name": name},
    )


async def _lookup_postgres(lat: Decimal, lon: Decimal, db: AsyncSession) -> str | None:
    row = (
        await db.execute(
            text(
                "SELECT display_name FROM geocoded_locations "
                "WHERE latitude = :lat AND longitude = :lon "
                "AND display_name NOT IN ('Location', 'Unknown Location')"
            ),
            {"lat": lat, "lon": lon},
        )
    ).fetchone()
    if row and _is_useful_name(row[0]):
        return row[0]

    nearby = (
        await db.execute(
            text(
                "SELECT display_name FROM geocoded_locations "
                "WHERE latitude BETWEEN :lat_min AND :lat_max "
                "AND longitude BETWEEN :lon_min AND :lon_max "
                "AND display_name NOT IN ('Location', 'Unknown Location') "
                "ORDER BY (ABS(latitude - :lat) + ABS(longitude - :lon)) ASC "
                "LIMIT 1"
            ),
            {
                "lat": lat,
                "lon": lon,
                "lat_min": lat - GEO_NEARBY_DELTA,
                "lat_max": lat + GEO_NEARBY_DELTA,
                "lon_min": lon - GEO_NEARBY_DELTA,
                "lon_max": lon + GEO_NEARBY_DELTA,
            },
        )
    ).fetchone()
    if nearby and _is_useful_name(nearby[0]):
        return nearby[0]
    return None


async def _cooldown_until() -> float:
    raw = await cache_get(COOLDOWN_KEY)
    if isinstance(raw, dict) and raw.get("until") is not None:
        try:
            return float(raw["until"])
        except (TypeError, ValueError):
            return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    return 0.0


async def _remaining_cooldown() -> float:
    return max(0.0, max(_next_allowed, await _cooldown_until()) - time.time())


async def _set_cooldown(until_ts: float, failures: int) -> None:
    ttl = max(1, int(until_ts - time.time()) + 1)
    await cache_set(
        COOLDOWN_KEY,
        {"until": until_ts, "failures": failures},
        expire_seconds=ttl,
    )


def _expand_delay(failures: int) -> float:
    return min(NOMINATIM_MAX_COOLDOWN, NOMINATIM_MIN_INTERVAL * (2 ** failures))


async def _note_nominatim_429() -> None:
    global _failures, _next_allowed
    _failures += 1
    delay = _expand_delay(_failures)
    _next_allowed = time.time() + delay
    await _set_cooldown(_next_allowed, _failures)
    logger.warning("Nominatim 429 — cooldown %.1fs (failures=%s)", delay, _failures)


async def _note_nominatim_success() -> None:
    global _failures, _next_allowed
    _failures = 0
    _next_allowed = time.time() + NOMINATIM_MIN_INTERVAL
    await _set_cooldown(_next_allowed, 0)


async def _fetch_nominatim(lat: Decimal, lon: Decimal) -> str | None:
    """One Nominatim call. Returns None if cooling down or the provider refused."""
    global _next_allowed
    async with _nominatim_lock:
        wait = await _remaining_cooldown()
        if wait > 0:
            logger.info("Nominatim cooldown %.1fs — skip", wait)
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={
                        "format": "jsonv2",
                        "lat": float(lat),
                        "lon": float(lon),
                    },
                    headers={"User-Agent": "iVDrive-Backend-Cache (info@ivdrive.eu)"},
                )
        except Exception:
            logger.exception("Nominatim request failed")
            _next_allowed = time.time() + _expand_delay(max(_failures, 1))
            return None

        if response.status_code == 429:
            await _note_nominatim_429()
            return None

        if response.status_code != 200:
            logger.warning("Nominatim HTTP %s", response.status_code)
            _next_allowed = time.time() + NOMINATIM_MIN_INTERVAL
            return None

        try:
            name = _short_name(response.json())
        except Exception:
            logger.exception("Nominatim parse failed")
            await _note_nominatim_success()
            return None

        await _note_nominatim_success()
        return name


async def _fetch_photon(lat: Decimal, lon: Decimal) -> str | None:
    """Komoot Photon fallback while Nominatim is cooling down."""
    global _photon_next_allowed
    async with _photon_lock:
        wait = _photon_next_allowed - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://photon.komoot.io/reverse",
                    params={"lat": float(lat), "lon": float(lon)},
                    headers={"User-Agent": "iVDrive-Backend-Cache (info@ivdrive.eu)"},
                )
        except Exception:
            logger.exception("Photon request failed")
            _photon_next_allowed = time.time() + PHOTON_MIN_INTERVAL
            return None

        _photon_next_allowed = time.time() + PHOTON_MIN_INTERVAL
        if response.status_code != 200:
            logger.warning("Photon HTTP %s", response.status_code)
            return None
        try:
            return _short_name_photon(response.json())
        except Exception:
            logger.exception("Photon parse failed")
            return None


async def _resolve(lat: Decimal, lon: Decimal, db: AsyncSession) -> tuple[str, int | None]:
    cached = await cache_get(_valkey_key(lat, lon))
    if isinstance(cached, str) and _is_useful_name(cached):
        return cached, None

    stored = await _lookup_postgres(lat, lon, db)
    if stored:
        await _remember(lat, lon, stored, db)
        return stored, None

    fetched = await _fetch_nominatim(lat, lon)
    if fetched and _is_useful_name(fetched):
        await _remember(lat, lon, fetched, db)
        return fetched, None

    fallback = await _fetch_photon(lat, lon)
    if fallback and _is_useful_name(fallback):
        await _remember(lat, lon, fallback, db)
        return fallback, None

    retry = max(8, math.ceil(await _remaining_cooldown()) or 8)
    return "Location", retry


@router.post("/reverse", response_model=GeoResponse)
async def reverse_geocode(
    req: GeoRequest,
    db: AsyncSession = Depends(get_db),
):
    """Valkey → Postgres → Nominatim → Photon. Location is a miss, not a final name."""
    lat = _rounded_coord(req.latitude)
    lon = _rounded_coord(req.longitude)
    key = f"{lat},{lon}"

    loop = asyncio.get_running_loop()
    existing = _inflight.get(key)
    if existing is not None:
        name, retry = await existing
        return {"display_name": name, "retry_after_seconds": retry}

    fut: asyncio.Future[tuple[str, int | None]] = loop.create_future()
    _inflight[key] = fut
    try:
        name, retry = await _resolve(lat, lon, db)
        if not fut.done():
            fut.set_result((name, retry))
        return {"display_name": name, "retry_after_seconds": retry}
    except Exception:
        logger.exception("reverse geocode failed")
        if not fut.done():
            fut.set_result(("Location", 8))
        return {"display_name": "Location", "retry_after_seconds": 8}
    finally:
        # CancelledError is BaseException, not Exception. If the leader
        # request is cancelled, waiters on this Future hang unless we resolve.
        if not fut.done():
            fut.set_result(("Location", 8))
        if _inflight.get(key) is fut:
            _inflight.pop(key, None)
