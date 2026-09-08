"""Vampire drain (parked standby) from trip gaps.

Skoda only exposes integer SoC, and the collector does not persist charging
payloads while parked. The reliable signal is therefore:

    trip[i].end_soc  →  trip[i+1].start_soc

while the car stayed still and did not charge. Hour-weighted, including
nights where integer SoC did not tick (0% displayed drop).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


VAMPIRE_DRAIN_DEFAULTS = {
    "min_parked_hours": 1.0,
    "max_parked_hours": 72.0,
    "max_dsoc_pct": 15.0,
    "min_dsoc_pct": -1.0,  # allow 1% BMS rounding gain
    "max_odo_delta_km": 1.0,
}


@dataclass(frozen=True)
class TripEndpoint:
    start: datetime
    end: datetime
    start_soc: float
    end_soc: float
    start_odometer: float | None
    end_odometer: float | None


@dataclass(frozen=True)
class ChargeWindow:
    start: datetime
    end: datetime | None


@dataclass(frozen=True)
class VampireDrainStats:
    has_data: bool
    sample_count: int
    zero_drop_count: int
    parked_hours: float
    total_soc_lost: float
    avg_drain_pct_per_hour: float
    avg_drain_pct_per_day: float


def _charge_overlaps(
    park_start: datetime,
    park_end: datetime,
    charge: ChargeWindow,
    max_open_hours: float,
) -> bool:
    if charge.end is None:
        if charge.start >= park_end:
            return False
        age_h = (park_start - charge.start).total_seconds() / 3600.0
        return age_h < max_open_hours
    return charge.start < park_end and charge.end > park_start


def compute_vampire_drain(
    trips: Sequence[TripEndpoint],
    charges: Sequence[ChargeWindow] = (),
    cfg: dict | None = None,
) -> VampireDrainStats:
    """Hour-weighted parked SoC loss between consecutive trips."""
    rules = {**VAMPIRE_DRAIN_DEFAULTS, **(cfg or {})}
    ordered = sorted(trips, key=lambda t: t.start)

    total_dsoc = 0.0
    total_hours = 0.0
    sample_count = 0
    zero_drop_count = 0

    for prev, nxt in zip(ordered, ordered[1:]):
        parked_h = (nxt.start - prev.end).total_seconds() / 3600.0
        if not (rules["min_parked_hours"] < parked_h < rules["max_parked_hours"]):
            continue
        if prev.end_odometer is None or nxt.start_odometer is None:
            continue
        if abs(nxt.start_odometer - prev.end_odometer) > rules["max_odo_delta_km"]:
            continue
        if any(
            _charge_overlaps(prev.end, nxt.start, ch, rules["max_parked_hours"])
            for ch in charges
        ):
            continue

        dsoc = float(prev.end_soc) - float(nxt.start_soc)
        if not (rules["min_dsoc_pct"] <= dsoc < rules["max_dsoc_pct"]):
            continue

        total_dsoc += dsoc
        total_hours += parked_h
        sample_count += 1
        if dsoc == 0:
            zero_drop_count += 1

    if sample_count == 0 or total_hours <= 0:
        return VampireDrainStats(
            has_data=False,
            sample_count=0,
            zero_drop_count=0,
            parked_hours=0.0,
            total_soc_lost=0.0,
            avg_drain_pct_per_hour=0.0,
            avg_drain_pct_per_day=0.0,
        )

    pct_per_hour = max(0.0, total_dsoc / total_hours)
    return VampireDrainStats(
        has_data=True,
        sample_count=sample_count,
        zero_drop_count=zero_drop_count,
        parked_hours=round(total_hours, 1),
        total_soc_lost=round(total_dsoc, 1),
        avg_drain_pct_per_hour=pct_per_hour,
        avg_drain_pct_per_day=pct_per_hour * 24.0,
    )


async def vampire_drain_for_vehicle(db: AsyncSession, vehicle_id: UUID) -> VampireDrainStats:
    """Load trips + charging sessions and compute parked drain for one vehicle."""
    from app.models.telemetry import ChargingSession, Trip

    trip_res = await db.execute(
        select(Trip)
        .where(Trip.user_vehicle_id == vehicle_id)
        .where(Trip.start_soc.is_not(None))
        .where(Trip.end_soc.is_not(None))
        .where(Trip.end_date.is_not(None))
        .order_by(Trip.start_date)
    )
    trips: list[TripEndpoint] = []
    for t in trip_res.scalars().all():
        if t.start_date is None or t.end_date is None or t.start_soc is None or t.end_soc is None:
            continue
        trips.append(
            TripEndpoint(
                start=t.start_date,
                end=t.end_date,
                start_soc=float(t.start_soc),
                end_soc=float(t.end_soc),
                start_odometer=float(t.start_odometer) if t.start_odometer is not None else None,
                end_odometer=float(t.end_odometer) if t.end_odometer is not None else None,
            )
        )

    charge_res = await db.execute(
        select(ChargingSession)
        .where(ChargingSession.user_vehicle_id == vehicle_id)
        .where(ChargingSession.session_start.is_not(None))
    )
    charges = [
        ChargeWindow(start=c.session_start, end=c.session_end)
        for c in charge_res.scalars().all()
        if c.session_start is not None
    ]
    return compute_vampire_drain(trips, charges)
