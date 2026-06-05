"""Phase 3 handlers: trip annotations, charging reminders, data quality."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase3 import TripAnnotation, ChargingReminder, AlertHistory
from app.services.valkey_client import get_valkey

logger = logging.getLogger(__name__)

# ── Intent patterns (compiled once) ───────────────────────────────────────────

import re

ANNOTATION_PATTERNS = [
    re.compile(r'annotate', re.I),
    re.compile(r'\btag\b.*\btrip\b', re.I),
    re.compile(r'note[:\s]', re.I),
    re.compile(r'add.*note', re.I),
    re.compile(r'\bflag\b.*\btrip\b', re.I),
    re.compile(r'comment.*trip', re.I),
]

REMINDER_PATTERNS = [
    re.compile(r'\bremind\s+(me\s+)?(to\s+)?charge', re.I),
    re.compile(r'set\s+.*reminder.*charge', re.I),
    re.compile(r'charging\s+reminder', re.I),
    re.compile(r'alert.*charge', re.I),
    re.compile(r'notify.*charge', re.I),
    re.compile(r'\bcharge\b.*\bat\s+\d', re.I),  # "charge at 8pm"
    re.compile(r'tomorrow.*charge', re.I),
]

CANCEL_REMINDER_PATTERNS = [
    re.compile(r'cancel\s+.*reminder', re.I),
    re.compile(r'delete\s+.*reminder', re.I),
    re.compile(r'remove\s+.*reminder', re.I),
    re.compile(r'stop\s+.*reminder', re.I),
]

LIST_REMINDERS_PATTERNS = [
    re.compile(r'list\s+.*reminder', re.I),
    re.compile(r'show\s+.*reminder', re.I),
    re.compile(r'what\s+.*reminder', re.I),
    re.compile(r'my\s+reminder', re.I),
]

DATA_QUALITY_PATTERNS = [
    re.compile(r'any\s+(data\s+)?issue', re.I),
    re.compile(r'any\s+problem', re.I),
    re.compile(r'check\s+.*quality', re.I),
    re.compile(r'health\s+check', re.I),
    re.compile(r'phantom\s+trip', re.I),
    re.compile(r'data\s+gap', re.I),
]

SUMMARY_PATTERNS = [
    re.compile(r'(weekly|daily|monthly)\s+summary', re.I),
    re.compile(r'summarize\s+.*week', re.I),
    re.compile(r'how\s+was\s+.*week', re.I),
    re.compile(r'week\s+.*review', re.I),
]


def detect_phase3_intent(query: str) -> Optional[str]:
    """Returns the intent key or None."""
    q = query.lower()
    if any(p.search(q) for p in CANCEL_REMINDER_PATTERNS):
        return 'cancel_reminder'
    if any(p.search(q) for p in LIST_REMINDERS_PATTERNS):
        return 'list_reminders'
    if any(p.search(q) for p in REMINDER_PATTERNS):
        return 'set_reminder'
    if any(p.search(q) for p in ANNOTATION_PATTERNS):
        return 'annotate_trip'
    if any(p.search(q) for p in DATA_QUALITY_PATTERNS):
        return 'data_quality'
    if any(p.search(q) for p in SUMMARY_PATTERNS):
        return 'weekly_summary'
    return None


# ── Trip Annotations ──────────────────────────────────────────────────────────

async def add_trip_annotation(
    db: AsyncSession,
    user_id: str,
    vehicle_id: str,
    annotation: str,
    tags: list[str] | None = None,
) -> TripAnnotation:
    """Store a note/tag on a trip."""
    ann = TripAnnotation(
        user_id=uuid.UUID(str(user_id)),
        user_vehicle_id=uuid.UUID(str(vehicle_id)) if vehicle_id else None,
        annotation=annotation,
        tags=tags or [],
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return ann


async def get_trip_annotations(
    db: AsyncSession,
    vehicle_id: str,
    limit: int = 20,
) -> list[TripAnnotation]:
    """Get annotations for a vehicle."""
    stmt = (
        select(TripAnnotation)
        .where(TripAnnotation.user_vehicle_id == uuid.UUID(str(vehicle_id)))
        .order_by(TripAnnotation.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ── Charging Reminders ────────────────────────────────────────────────────────

async def set_charging_reminder(
    db: AsyncSession,
    user_id: str,
    remind_at: datetime,
    vehicle_id: str | None = None,
    message: str | None = None,
) -> ChargingReminder:
    """Create a charging reminder in DB and Valkey."""
    import logging
    logger2 = logging.getLogger(__name__)
    logger2.info(f"[DEBUG set_charging_reminder] user_id={user_id} ({type(user_id)}), vehicle_id={vehicle_id} ({type(vehicle_id) if vehicle_id else None})")
    try:
        # Safely convert user_id to UUID (asyncpg UUID has no .replace)
        try:
            uid_uuid = uuid.UUID(str(user_id))
        except Exception:
            uid_uuid = user_id  # Already a proper UUID
        
        # Safely convert vehicle_id to UUID if provided
        vid_uuid = None
        if vehicle_id:
            try:
                vid_uuid = uuid.UUID(str(vehicle_id))
            except Exception:
                vid_uuid = vehicle_id
        
        reminder = ChargingReminder(
            user_id=uid_uuid,
            user_vehicle_id=vid_uuid,
            remind_at=remind_at,
            message=message,
        )
        db.add(reminder)
        await db.commit()
        await db.refresh(reminder)
    except Exception as e:
        logger2.error(f"Failed to create reminder: {e}", exc_info=True)
        raise

    # Also store in Valkey for fast due-check (non-critical, wrap in try/except)
    try:
        vk = get_valkey()
        vk.add_charging_reminder(
            user_id=user_id,
            vehicle_id=vehicle_id,
            remind_at=remind_at,
            message=message or f"Charging reminder for {vehicle_id or 'your vehicle'}",
        )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Valkey reminder store failed: {e}")

    return reminder


async def list_charging_reminders(
    db: AsyncSession,
    user_id: str,
    include_cancelled: bool = False,
) -> list[ChargingReminder]:
    """List user's reminders."""
    stmt = (
        select(ChargingReminder)
        .where(ChargingReminder.user_id == uuid.UUID(str(user_id)))
    )
    if not include_cancelled:
        stmt = stmt.where(ChargingReminder.cancelled_at.is_(None))
    stmt = stmt.order_by(ChargingReminder.remind_at.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def cancel_charging_reminder(
    db: AsyncSession,
    reminder_id: str,
    user_id: str,
) -> bool:
    """Cancel a reminder (soft delete)."""
    stmt = (
        select(ChargingReminder)
        .where(
            ChargingReminder.id == uuid.UUID(str(reminder_id)),
            ChargingReminder.user_id == uuid.UUID(str(user_id)),
            ChargingReminder.cancelled_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    reminder = result.scalar_one_or_none()
    if not reminder:
        return False
    reminder.cancelled_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def get_due_reminders(db: AsyncSession, user_id: str) -> list[ChargingReminder]:
    """Get reminders that are due (from DB)."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(ChargingReminder)
        .where(
            ChargingReminder.user_id == uuid.UUID(str(user_id)),
            ChargingReminder.remind_at <= now,
            ChargingReminder.fired_at.is_(None),
            ChargingReminder.cancelled_at.is_(None),
        )
        .order_by(ChargingReminder.remind_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def fire_reminder(db: AsyncSession, reminder_id: str) -> None:
    """Mark a reminder as fired."""
    stmt = select(ChargingReminder).where(ChargingReminder.id == uuid.UUID(str(reminder_id)))
    result = await db.execute(stmt)
    reminder = result.scalar_one_or_none()
    if reminder:
        reminder.fired_at = datetime.now(timezone.utc)
        await db.commit()


# ── Data Quality Checks ──────────────────────────────────────────────────────

async def check_phantom_trips(db: AsyncSession, user_id: str) -> list[dict]:
    """Find trips with distance=0 or duration anomalous (likely phantom)."""
    query = text("""
        SELECT t.id, t.user_vehicle_id, t.start_date::text, t.distance_km,
               EXTRACT(EPOCH FROM (t.end_date - t.start_date)) AS duration_sec,
               v.display_name
        FROM trips t
        JOIN user_vehicles v ON v.id = t.user_vehicle_id
        WHERE t.user_id = :uid
          AND t.end_date IS NOT NULL
          AND (t.distance_km = 0 OR t.distance_km < 0.1)
          AND t.start_date > NOW() - INTERVAL '30 days'
        ORDER BY t.start_date DESC
        LIMIT 10
    """)
    result = await db.execute(query, {"uid": uuid.UUID(str(user_id))})
    rows = result.fetchall()
    return [
        {
            "trip_id": str(r[0]),
            "vehicle_id": str(r[1]),
            "start_date": r[2],
            "distance_km": r[3],
            "duration_sec": r[4],
            "vehicle_name": r[5],
        }
        for r in rows
    ]


async def check_data_gaps(db: AsyncSession, user_id: str) -> list[dict]:
    """Find vehicles with no data in the last 7+ days."""
    query = text("""
        SELECT v.id, v.display_name,
               MAX(t.start_date)::text AS last_trip,
               MAX(c.session_start)::text AS last_charge
        FROM user_vehicles v
        LEFT JOIN trips t ON t.user_vehicle_id = v.id AND t.end_date IS NOT NULL
        LEFT JOIN charging_sessions c ON c.user_vehicle_id = v.id AND c.session_end IS NOT NULL
        WHERE v.user_id = :uid
        GROUP BY v.id, v.display_name
        HAVING
            (MAX(t.start_date) IS NULL OR MAX(t.start_date) < NOW() - INTERVAL '7 days')
            AND (MAX(c.session_start) IS NULL OR MAX(c.session_start) < NOW() - INTERVAL '7 days')
        LIMIT 10
    """)
    result = await db.execute(query, {"uid": uuid.UUID(str(user_id))})
    rows = result.fetchall()
    return [
        {
            "vehicle_id": str(r[0]),
            "vehicle_name": r[1],
            "last_trip": r[2],
            "last_charge": r[3],
        }
        for r in rows
    ]


async def run_data_quality_check(db: AsyncSession, user_id: str) -> dict:
    """Run all data quality checks and return a summary."""
    phantom = await check_phantom_trips(db, user_id)
    gaps = await check_data_gaps(db, user_id)

    issues = []
    if phantom:
        issues.append(f"⚠️ *{len(phantom)} phantom trips* detected (0km trips in last 30 days)")
    if gaps:
        vehicle_names = ", ".join(g["vehicle_name"] for g in gaps)
        issues.append(f"⚠️ *Data gaps* for: {vehicle_names} (no data in 7+ days)")

    return {
        "status": "issues_found" if issues else "ok",
        "issues": issues,
        "details": {
            "phantom_trips": phantom[:3],  # top 3
            "data_gaps": gaps,
        },
    }


# ── Weekly Summary ─────────────────────────────────────────────────────────────

async def get_weekly_summary(db: AsyncSession, user_id: str) -> dict:
    """Generate a weekly summary for the user."""
    query = text("""
        SELECT
            v.display_name,
            COUNT(DISTINCT t.id) AS trips,
            COALESCE(SUM(t.distance_km), 0) AS total_km,
            COALESCE(SUM(t.kwh_consumed), 0) AS total_kwh,
            COUNT(DISTINCT c.id) AS charge_sessions,
            COALESCE(SUM(c.energy_kwh), 0) AS total_charged
        FROM user_vehicles v
        LEFT JOIN trips t ON t.user_vehicle_id = v.id
            AND t.end_date IS NOT NULL
            AND t.start_date > NOW() - INTERVAL '7 days'
        LEFT JOIN charging_sessions c ON c.user_vehicle_id = v.id
            AND c.session_end IS NOT NULL
            AND c.session_start > NOW() - INTERVAL '7 days'
        WHERE v.user_id = :uid
        GROUP BY v.id, v.display_name
        ORDER BY total_km DESC
    """)
    result = await db.execute(query, {"uid": uuid.UUID(str(user_id))})
    rows = result.fetchall()

    vehicle_summaries = []
    for r in rows:
        total_km = float(r[2])
        total_kwh = float(r[3]) if r[3] else 0
        efficiency = (total_kwh / total_km * 100) if total_km > 0 else 0
        vehicle_summaries.append({
            "vehicle": r[0],
            "trips": r[1],
            "total_km": round(total_km, 1),
            "total_kwh": round(total_kwh, 1),
            "efficiency": round(efficiency, 1),
            "charge_sessions": r[4],
            "total_charged_kwh": round(float(r[5]) if r[5] else 0, 1),
        })

    return {"vehicles": vehicle_summaries}