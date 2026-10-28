"""Fill trips iVDrive's polling missed using MyŠkoda's server-side trip history.

`GET /api/v1/trip-statistics/{vin}/single-trips` returns journeys; each journey has
waypoints (stops) with exact arrival/departure times, SoC, coordinates and the
distance of the leg to the next waypoint. One leg == one iVDrive trip. Legs are
inserted only where no existing trip overlaps them in time; measured trips are never
overwritten or deleted (a 0 km trip overlapping a leg gets that leg's distance).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Trip

logger = logging.getLogger(__name__)

DEFAULT_CAPACITY_KWH = 77.0


@dataclass
class Leg:
    start: datetime
    end: datetime
    start_odometer: float
    end_odometer: float
    start_soc: int | None
    end_soc: int | None
    start_lat: float | None
    start_lon: float | None
    end_lat: float | None
    end_lon: float | None

    @property
    def km(self) -> float:
        return self.end_odometer - self.start_odometer


def _ts(v: str | None) -> datetime | None:
    if not v:
        return None
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_legs(payload: dict) -> list[Leg]:
    """Turn a single-trips response into legs. Malformed journeys are skipped, never guessed."""
    legs: list[Leg] = []
    for day in payload.get("dailyTrips") or []:
        for trip in day.get("trips") or []:
            wps = trip.get("waypoints") or []
            start_odo = trip.get("startMileageInKm")
            end_odo = trip.get("endMileageInKm")
            if len(wps) < 2 or start_odo is None or end_odo is None:
                continue
            odo = float(start_odo)
            built: list[Leg] = []
            ok = True
            for a, b in zip(wps, wps[1:]):
                dep, arr = _ts(a.get("departureTime")), _ts(b.get("arrivalTime"))
                if dep is None or arr is None or arr < dep:
                    ok = False
                    break
                dist = float(a.get("distanceToNextWaypointInKm") or 0)
                ca, cb = a.get("coordinates") or {}, b.get("coordinates") or {}
                built.append(Leg(
                    dep, arr, odo, odo + dist,
                    a.get("departureStateOfChargeInPercent"), b.get("arrivalStateOfChargeInPercent"),
                    ca.get("latitude"), ca.get("longitude"), cb.get("latitude"), cb.get("longitude"),
                ))
                odo += dist
            if not ok or not built:
                continue
            built[-1].end_odometer = float(end_odo)  # absorb per-leg km rounding
            if built[-1].end_odometer < built[-1].start_odometer:
                continue
            legs.extend(built)
    return legs


def _covers(trip: Trip, leg: Leg, now: datetime) -> bool:
    """A recorded trip covers a leg when they share at least half of the shorter span.

    Adjacent legs of one journey (stops of a few minutes) touch but must not count as covered.
    """
    t_start = trip.start_date.astimezone(timezone.utc)
    t_end = (trip.end_date or now).astimezone(timezone.utc)
    overlap = (min(t_end, leg.end) - max(t_start, leg.start)).total_seconds()
    shorter = max(min((t_end - t_start).total_seconds(), (leg.end - leg.start).total_seconds()), 60.0)
    return overlap >= 0.5 * shorter


@dataclass
class SyncResult:
    inserted: int = 0
    distance_filled: int = 0
    skipped_covered: int = 0
    km_added: float = 0.0


async def sync_legs(
    session: AsyncSession,
    vehicle_id: UUID,
    legs: list[Leg],
    *,
    capacity_kwh: float | None = None,
    apply: bool = True,
) -> SyncResult:
    res = SyncResult()
    capacity = capacity_kwh or DEFAULT_CAPACITY_KWH
    for leg in sorted(legs, key=lambda x: x.start):
        now = datetime.now(timezone.utc)
        cands = list((await session.execute(
            select(Trip).where(
                Trip.user_vehicle_id == vehicle_id,
                Trip.start_date < leg.end,
                (Trip.end_date.is_(None)) | (Trip.end_date > leg.start),
            )
        )).scalars())
        overlapping = [t for t in cands if _covers(t, leg, now)]
        if overlapping:
            # A recorded trip covers this leg. Only repair a trip that lost its distance.
            for t in overlapping:
                if (t.distance_km in (None, 0)) and t.start_odometer is not None and leg.km > 0 and len(overlapping) == 1:
                    res.distance_filled += 1
                    res.km_added += leg.km
                    if apply:
                        t.end_odometer = float(t.start_odometer) + leg.km
                        t.distance_km = leg.km
                        t.data_quality = t.data_quality or "skoda_history"
                    break
            else:
                res.skipped_covered += 1
            continue
        if leg.km <= 0:
            continue
        res.inserted += 1
        res.km_added += leg.km
        if apply:
            used = (leg.start_soc - leg.end_soc) if leg.start_soc is not None and leg.end_soc is not None else None
            session.add(Trip(
                user_vehicle_id=vehicle_id, start_date=leg.start, end_date=leg.end,
                start_lat=leg.start_lat, start_lon=leg.start_lon, end_lat=leg.end_lat, end_lon=leg.end_lon,
                start_odometer=leg.start_odometer, end_odometer=leg.end_odometer, distance_km=leg.km,
                start_soc=leg.start_soc, end_soc=leg.end_soc,
                kwh_consumed=(used / 100.0 * capacity) if used and used > 0 else None,
                data_quality="skoda_history",
            ))
    if apply and (res.inserted or res.distance_filled):
        await session.flush()
    return res


async def run_trip_sync(only_vehicle: UUID | None = None, *, apply: bool = True, pause_s: float = 3.0) -> dict[str, SyncResult]:
    """One pass over every MyŠkoda-Login vehicle. Never raises; one vehicle failing is logged and skipped.

    Independent of the smart poller: its own schedule, one GET per vehicle per run.
    """
    import asyncio
    import json

    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.vehicle import UserVehicle
    from app.services.crypto import decrypt_field
    from app.services.skoda_api import SkodaAPIClient
    from app.services.skoda_lifecycle import AuthRequiredError, SkodaTokenLifecycle

    out: dict[str, SyncResult] = {}
    async with async_session() as s:
        q = select(UserVehicle.id).where(UserVehicle.collection_enabled.is_(True))
        if only_vehicle:
            q = q.where(UserVehicle.id == only_vehicle)
        ids = list((await s.execute(q)).scalars())

    for vid in ids:
        try:
            async with async_session() as s:
                v = (await s.execute(
                    select(UserVehicle).where(UserVehicle.id == vid).options(selectinload(UserVehicle.connector_session))
                )).scalar_one_or_none()
                cs = v.connector_session if v else None
                if v is None or cs is None or cs.status in ("token_error", "auth_failed"):
                    continue  # no MyŠkoda Login for this vehicle (Public API has no trip history)
                username = password = None
                if v.connector_config_encrypted:
                    try:
                        cfg = json.loads(decrypt_field(v.connector_config_encrypted))
                        username, password = cfg.get("username"), cfg.get("password")
                    except Exception:
                        pass
                try:
                    token = await SkodaTokenLifecycle(s).ensure_valid_token(cs, username, password)
                except AuthRequiredError:
                    continue
                api = SkodaAPIClient(token)
                try:
                    payload = await api.get_single_trips(decrypt_field(v.vin_encrypted))
                finally:
                    await api.close()
                res = await sync_legs(s, vid, parse_legs(payload), capacity_kwh=v.battery_capacity_kwh, apply=apply)
                if apply:
                    await s.commit()
                out[str(vid)] = res
                if res.inserted or res.distance_filled:
                    logger.info("trip sync %s: +%d trips, %d distances filled, +%.0f km (apply=%s)",
                                vid, res.inserted, res.distance_filled, res.km_added, apply)
        except Exception as e:  # one vehicle must never stop the rest
            logger.warning("trip sync failed for %s: %s", vid, str(e)[:200])
        await asyncio.sleep(pause_s)
    return out
