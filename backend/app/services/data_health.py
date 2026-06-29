"""Per-vehicle data-freshness snapshot.

Powers both the dashboard "data health" widget and the AI Support Coach tool.
Single source of truth — both UIs consume the same function so the chat agent
can never disagree with what the user sees on the dashboard.

Health roll-up:
  - live   — most recent telemetry within the last hour
  - stale  — last telemetry 1-24h ago, user may notice missing recent data
  - down   — no telemetry in >24h, vehicle essentially invisible to the app
  - unknown — no telemetry ever recorded for this vehicle (never polled)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import (
    ChargingSession,
    ChargingState,
    OdometerReading,
    Trip,
    VehiclePosition,
    VehicleState,
)
from app.models.vehicle import UserVehicle
from app.schemas.vehicle import DataHealthTimeline, VehicleDataHealthResponse

logger = logging.getLogger(__name__)

# Thresholds (minutes) — exposed here so the AI prompt and tests can reference them.
LIVE_MAX_MINUTES = 60
STALE_MAX_MINUTES = 24 * 60


def _age_minutes(ts: datetime | None, now: datetime) -> int | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0, int((now - ts).total_seconds() // 60))


def _classify(minutes: int | None) -> str:
    if minutes is None:
        return "unknown"
    if minutes <= LIVE_MAX_MINUTES:
        return "live"
    if minutes <= STALE_MAX_MINUTES:
        return "stale"
    return "down"


async def _last_seen(db: AsyncSession, vid, model, ts_col: str) -> datetime | None:
    ts_attr = getattr(model, ts_col)
    stmt = select(func.max(ts_attr)).where(model.user_vehicle_id == vid)
    row = (await db.execute(stmt)).scalar_one()
    return row


async def _has_ongoing_trip(db: AsyncSession, vid) -> bool:
    """A trip is 'ongoing' if it has a start_date but no end_date."""
    stmt = select(func.count(Trip.id)).where(
        Trip.user_vehicle_id == vid, Trip.end_date.is_(None)
    )
    return (await db.execute(stmt)).scalar_one() > 0


async def _is_currently_charging(db: AsyncSession, vid) -> bool:
    """Charging is 'current' if the latest charging_state.state indicates active charging."""
    stmt = (
        select(ChargingState.state)
        .where(ChargingState.user_vehicle_id == vid)
        .order_by(ChargingState.last_date.desc())
        .limit(1)
    )
    state = (await db.execute(stmt)).scalar_one_or_none()
    if not state:
        return False
    return state.upper() in {"CHARGING", "READY_TO_CHARGE"}


def _decide_refresh(status: str, last_telemetry_age: int | None) -> tuple[bool, str | None]:
    """Decide whether the AI should recommend a manual refresh."""
    if status == "down":
        return True, "No telemetry received in over 24 hours — a manual refresh may restore the connection."
    if status == "stale":
        return True, "Telemetry is more than an hour behind — a manual refresh usually catches the missing data."
    return False, None


async def compute_vehicle_data_health(
    db: AsyncSession, vehicle: UserVehicle
) -> VehicleDataHealthResponse:
    """Build the data-health snapshot for one vehicle."""
    from app.services.crypto import decrypt_field

    now = datetime.now(timezone.utc)
    vid = vehicle.id

    # Pull last-seen for each telemetry stream. Done in parallel for speed.
    (
        pos_ts,
        state_ts,
        cs_ts,
        chg_ts,
        trip_ts,
        odo_ts,
    ) = await _gather_last_seen(db, vid)

    timeline = {
        "position": _timeline(pos_ts, now),
        "vehicle_state": _timeline(state_ts, now),
        "charging_state": _timeline(cs_ts, now),
        "charging_session": _timeline(chg_ts, now),
        "trip": _timeline(trip_ts, now),
        "odometer": _timeline(odo_ts, now),
    }

    # Most recent telemetry across all streams
    last_telemetry_at = max(
        (ts for ts in (pos_ts, state_ts, cs_ts, chg_ts, trip_ts, odo_ts) if ts is not None),
        default=None,
    )
    minutes_since = _age_minutes(last_telemetry_at, now)
    status = _classify(minutes_since)

    ongoing_trip = await _has_ongoing_trip(db, vid)
    charging_now = await _is_currently_charging(db, vid)

    refresh_recommended, refresh_reason = _decide_refresh(status, minutes_since)

    try:
        vin_plain = decrypt_field(vehicle.vin_encrypted)
        vin_last4 = vin_plain[-4:] if vin_plain else "????"
    except Exception:
        vin_last4 = "????"

    return VehicleDataHealthResponse(
        vehicle_id=vehicle.id,
        vin_last4=vin_last4,
        display_name=vehicle.display_name,
        status=status,
        last_telemetry_at=last_telemetry_at,
        minutes_since_last_telemetry=minutes_since,
        timeline=timeline,
        has_ongoing_trip=ongoing_trip,
        is_currently_charging=charging_now,
        collection_enabled=vehicle.collection_enabled,
        last_fetch_at=getattr(vehicle.connector_session, "last_fetch_at", None) if vehicle.connector_session else None,
        refresh_recommended=refresh_recommended,
        refresh_reason=refresh_reason,
        generated_at=now,
    )


async def _gather_last_seen(db: AsyncSession, vid):
    """Gather last-seen timestamps for each stream in a single helper.

    Sequential is fine — these are all indexed MAX() lookups and add <50ms total.
    Kept sequential (not gather) to avoid surprises with the shared session.
    """
    pos_ts = await _last_seen(db, vid, VehiclePosition, "captured_at")
    state_ts = await _last_seen(db, vid, VehicleState, "last_date")
    cs_ts = await _last_seen(db, vid, ChargingState, "last_date")
    chg_ts = await _last_seen(db, vid, ChargingSession, "session_start")
    trip_ts = await _last_seen(db, vid, Trip, "end_date")  # most-recent *completed* trip
    odo_ts = await _last_seen(db, vid, OdometerReading, "captured_at")
    return pos_ts, state_ts, cs_ts, chg_ts, trip_ts, odo_ts


def _timeline(ts: datetime | None, now: datetime) -> DataHealthTimeline:
    return DataHealthTimeline(last_at=ts, age_minutes=_age_minutes(ts, now))


def format_data_health_for_llm(health: VehicleDataHealthResponse) -> str:
    """Render the data-health snapshot as plain text for the AI coach tool.

    Concise and structured so the LLM can quote it directly in its answer.
    """
    lines = [
        f"Vehicle: {health.display_name or health.vin_last4} (…{health.vin_last4})",
        f"Data health: {health.status.upper()}",
        f"Last telemetry: {health.last_telemetry_at.isoformat() if health.last_telemetry_at else 'NEVER'} "
        f"({health.minutes_since_last_telemetry if health.minutes_since_last_telemetry is not None else 'unknown'} min ago)",
    ]
    lines.append("Per-stream last seen:")
    for name, t in health.timeline.items():
        age = "never" if t.age_minutes is None else f"{t.age_minutes} min ago"
        lines.append(f"  - {name}: {age}")

    if health.has_ongoing_trip:
        lines.append("Ongoing trip: yes (start recorded, no end yet)")
    if health.is_currently_charging:
        lines.append("Currently charging: yes")
    if not health.collection_enabled:
        lines.append("Collection: DISABLED — vehicle won't receive new telemetry until re-enabled.")

    if health.refresh_recommended:
        lines.append(f"Recommendation: trigger a manual refresh. Reason: {health.refresh_reason}")
    return "\n".join(lines)