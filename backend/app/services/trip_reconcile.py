"""Repair trip distances from the odometer series.

Skoda's odometer value often lags the moving state, so a trip can close with
start_odometer == end_odometer (distance 0) while a later reading shows the km.
`reconcile_zero_distance_trips` attributes that distance to the trip it belongs
to; `find_uncovered_gaps` reports odometer increments no trip accounts for.
Original telemetry rows are never modified; only trips are.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import OdometerReading, Trip

# How long after a trip closes a late odometer update may still belong to it.
ODOMETER_LAG_GRACE = timedelta(minutes=90)
MAX_TRIP_KM = 300.0   # larger jumps are not one drive; leave for manual review
MIN_GAP_KM = 1.0


@dataclass
class TripFix:
    trip_id: int
    start_date: datetime
    old_distance: float | None
    new_end_odometer: float
    new_distance: float


@dataclass
class Gap:
    start: datetime
    end: datetime
    start_odometer: float
    end_odometer: float

    @property
    def km(self) -> float:
        return self.end_odometer - self.start_odometer


async def reconcile_zero_distance_trips(
    session: AsyncSession,
    vehicle_id: UUID,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    apply: bool = False,
) -> list[TripFix]:
    q = select(Trip).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.end_date.is_not(None),
        (Trip.distance_km.is_(None)) | (Trip.distance_km == 0),
        Trip.start_odometer.is_not(None),
    ).order_by(Trip.start_date)
    if since:
        q = q.where(Trip.start_date >= since)
    if until:
        q = q.where(Trip.start_date <= until)
    candidates = list((await session.execute(q)).scalars())

    fixes: list[TripFix] = []
    for trip in candidates:
        nxt = (await session.execute(
            select(Trip).where(Trip.user_vehicle_id == vehicle_id, Trip.start_date > trip.start_date)
            .order_by(Trip.start_date).limit(1)
        )).scalar_one_or_none()
        bound = trip.end_date + ODOMETER_LAG_GRACE
        if nxt is not None and nxt.start_date < bound:
            bound = nxt.start_date
        last = (await session.execute(
            select(OdometerReading.mileage_in_km)
            .where(
                OdometerReading.user_vehicle_id == vehicle_id,
                OdometerReading.captured_at >= trip.start_date,
                OdometerReading.captured_at < bound,
            )
            .order_by(OdometerReading.captured_at.desc()).limit(1)
        )).scalar_one_or_none()
        if last is None:
            continue
        dist = float(last) - float(trip.start_odometer)
        if not (0 < dist <= MAX_TRIP_KM):
            continue
        fixes.append(TripFix(trip.id, trip.start_date, trip.distance_km, float(last), dist))
        if apply:
            trip.end_odometer = float(last)
            trip.distance_km = dist
            trip.data_quality = trip.data_quality or "estimated_end"
            # A following trip that started from the same stale odometer would
            # double-count this distance: start it where this one ended.
            if (
                nxt is not None and nxt.start_odometer is not None
                and nxt.start_odometer < last
                and (nxt.end_odometer is None or nxt.end_odometer >= last)
            ):
                nxt.start_odometer = float(last)
                if nxt.end_odometer is not None:
                    nxt.distance_km = float(nxt.end_odometer) - float(last)
                nxt.data_quality = nxt.data_quality or "estimated_start"
    if apply and fixes:
        await session.flush()
    return fixes


async def find_uncovered_gaps(
    session: AsyncSession,
    vehicle_id: UUID,
    *,
    since: datetime | None = None,
) -> list[Gap]:
    """Odometer increases between consecutive readings that no trip's odometer range covers."""
    rq = select(OdometerReading.captured_at, OdometerReading.mileage_in_km).where(
        OdometerReading.user_vehicle_id == vehicle_id
    ).order_by(OdometerReading.captured_at)
    tq = select(Trip.start_odometer, Trip.end_odometer).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.start_odometer.is_not(None), Trip.end_odometer.is_not(None),
    )
    if since:
        rq = rq.where(OdometerReading.captured_at >= since)
        tq = tq.where(Trip.start_date >= since - timedelta(days=1))
    readings = (await session.execute(rq)).all()
    ranges = sorted((float(a), float(b)) for a, b in (await session.execute(tq)).all())

    def covered(a: float, b: float) -> bool:
        # any trip whose odometer span overlaps (a, b)
        return any(lo < b and hi > a for lo, hi in ranges)

    gaps: list[Gap] = []
    for (t0, o0), (t1, o1) in zip(readings, readings[1:]):
        o0, o1 = float(o0), float(o1)
        if o1 - o0 >= MIN_GAP_KM and not covered(o0, o1):
            gaps.append(Gap(t0, t1, o0, o1))
    return gaps


async def create_reconstructed_trips(session: AsyncSession, vehicle_id: UUID, gaps: list[Gap]) -> int:
    """Insert one clearly-labelled trip per gap (no GPS, times = surrounding readings)."""
    n = 0
    for g in gaps:
        if g.km > MAX_TRIP_KM:
            continue
        exists = (await session.execute(
            select(Trip.id).where(Trip.user_vehicle_id == vehicle_id, Trip.start_date == g.start).limit(1)
        )).first()
        if exists:
            continue
        session.add(Trip(
            user_vehicle_id=vehicle_id, start_date=g.start, end_date=g.end,
            start_odometer=g.start_odometer, end_odometer=g.end_odometer,
            distance_km=g.km, data_quality="reconstructed",
        ))
        n += 1
    if n:
        await session.flush()
    return n


PHANTOM_MAX_MINUTES = 15


async def find_phantom_trips(
    session: AsyncSession, vehicle_id: UUID, *, since: datetime | None = None
) -> list[Trip]:
    """Closed trips with 0 km, <= 15 min and no odometer rise in their window.

    Call `reconcile_zero_distance_trips(apply=True)` first: it rescues trips whose
    distance only showed up in a later odometer reading. What remains is a single-poll
    "moving" flicker or a sub-1 km move (odometer is whole km) with no distance to report.
    """
    q = select(Trip).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.end_date.is_not(None),
        Trip.distance_km == 0,
        Trip.start_odometer.is_not(None),
        Trip.end_odometer == Trip.start_odometer,
    ).order_by(Trip.start_date)
    if since:
        q = q.where(Trip.start_date >= since)
    out: list[Trip] = []
    for trip in (await session.execute(q)).scalars():
        if trip.end_date - trip.start_date > timedelta(minutes=PHANTOM_MAX_MINUTES):
            continue
        rose = (await session.execute(
            select(OdometerReading.id).where(
                OdometerReading.user_vehicle_id == vehicle_id,
                OdometerReading.captured_at >= trip.start_date,
                OdometerReading.captured_at <= trip.end_date + ODOMETER_LAG_GRACE,
                OdometerReading.mileage_in_km > trip.start_odometer,
            ).limit(1)
        )).first()
        if rose is None:
            out.append(trip)
    return out
