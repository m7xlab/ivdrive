"""Feed recorded polls through the production analytics code path.

Each `Poll` is written the way the collector writes it (one ConnectionState and
OdometerReading row per poll, ChargingState merged into duration rows keyed on
`state`), then `process_completed_trips_and_charges` runs with `now=poll.ts`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.telemetry import (
    ChargingSession, ChargingState, ConnectionState, OdometerReading, Trip, VehiclePosition,
)
from app.services import analytics

UTC = timezone.utc


@dataclass
class Poll:
    ts: datetime
    moving: bool = False
    odometer: float | None = None
    charge_state: str | None = None
    power_kw: float | None = None
    soc: int | None = None
    ignition: bool | None = None  # defaults to `moving`, like the Public API path
    lat: float = 47.5
    lon: float = 19.0


def t(hhmm: str, day: str = "2026-10-28") -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=UTC)


async def feed(sm, vid, p: Poll) -> None:
    async with sm() as s:
        s.add(ConnectionState(
            user_vehicle_id=vid, captured_at=p.ts, is_online=True,
            in_motion=p.moving, ignition_on=p.moving if p.ignition is None else p.ignition,
        ))
        if p.odometer is not None:
            s.add(OdometerReading(user_vehicle_id=vid, captured_at=p.ts, mileage_in_km=p.odometer))
        s.add(VehiclePosition(user_vehicle_id=vid, captured_at=p.ts, latitude=p.lat, longitude=p.lon))
        if p.charge_state:
            last = (await s.execute(
                select(ChargingState).where(ChargingState.user_vehicle_id == vid)
                .order_by(ChargingState.first_date.desc()).limit(1)
            )).scalar_one_or_none()
            if last and last.state == p.charge_state:  # collector merges same-state rows
                last.last_date = p.ts
                last.charge_power_kw = p.power_kw
                last.battery_pct = p.soc
            else:
                s.add(ChargingState(
                    user_vehicle_id=vid, first_date=p.ts, last_date=p.ts, state=p.charge_state,
                    charge_power_kw=p.power_kw, battery_pct=p.soc,
                ))
        await s.commit()
    await analytics.process_completed_trips_and_charges(vid, now=p.ts)


async def replay(sm, vid, polls: list[Poll]) -> None:
    for p in polls:
        await feed(sm, vid, p)


async def trips(sm, vid) -> list[Trip]:
    async with sm() as s:
        return list((await s.execute(
            select(Trip).where(Trip.user_vehicle_id == vid).order_by(Trip.start_date)
        )).scalars())


async def sessions(sm, vid) -> list[ChargingSession]:
    async with sm() as s:
        return list((await s.execute(
            select(ChargingSession).where(ChargingSession.user_vehicle_id == vid)
            .order_by(ChargingSession.session_start)
        )).scalars())


def every(start: str, end: str, minutes: int, day: str = "2026-10-28", **kw) -> list[Poll]:
    out, cur, stop = [], t(start, day), t(end, day)
    while cur <= stop:
        out.append(Poll(ts=cur, **kw))
        cur += timedelta(minutes=minutes)
    return out
