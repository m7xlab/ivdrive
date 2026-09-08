"""Charging-plan period math, GPS match, and suggested session cost.

Cost rules:
- Included-kWh subscription (allotment set): in-allotment sessions cost 0;
  overage is (session_kwh - remaining) * overage rate (fallback monthly_fee / allotment).
- Discounted-rate subscription (no allotment) and home/public: energy * price_per_kwh.
- Monthly fee is a period line item in economics, not stuffed onto the first session.
"""

from __future__ import annotations

import math
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.charging_plan import UserChargingPlan
from app.models.geofence import Geofence
from app.models.telemetry import ChargingSession
from app.models.vehicle import UserVehicle
from app.services.cache import invalidate_vehicle_cache


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def add_period(d: date, periodicity: str | None) -> date:
    if periodicity == "yearly":
        return add_months(d, 12)
    return add_months(d, 1)


def period_containing(
    start: date, periodicity: str | None, when: date
) -> tuple[date, date] | None:
    if when < start:
        return None
    cursor = start
    for _ in range(600):
        nxt = add_period(cursor, periodicity or "monthly")
        if cursor <= when < nxt:
            return cursor, nxt
        cursor = nxt
    return None


def count_overlapping_periods(
    start: date,
    periodicity: str | None,
    window_start: date,
    window_end: date,
    today: date | None = None,
) -> int:
    """Count billing periods that overlap [window_start, window_end) and have started by today."""
    if window_end <= window_start:
        return 0
    today = today or date.today()
    count = 0
    cursor = start
    for _ in range(600):
        if cursor > today:
            break
        nxt = add_period(cursor, periodicity or "monthly")
        if cursor < window_end and nxt > window_start:
            count += 1
        cursor = nxt
        if cursor >= window_end and cursor > today:
            break
    return count


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(min(1.0, a)))


def overage_rate_eur(plan: UserChargingPlan) -> float | None:
    overage = _as_float(plan.overage_price_per_kwh_eur)
    if overage is not None:
        return overage
    allotment = _as_float(plan.kwh_allotment)
    fee = _as_float(plan.monthly_fee_eur)
    if allotment and allotment > 0 and fee is not None:
        return fee / allotment
    return _as_float(plan.price_per_kwh_eur)


def session_cost_from_remaining(
    session_kwh: float,
    remaining_kwh: float | None,
    rate: float | None,
) -> tuple[float, str]:
    """Return (cost, reason) for an included-kWh bucket."""
    if remaining_kwh is None:
        if rate is None:
            return 0.0, "per_kwh"
        return round(session_kwh * rate, 2), "per_kwh"
    if remaining_kwh >= session_kwh:
        return 0.0, "within_allotment"
    if rate is None:
        return 0.0, "overage"
    billed = max(0.0, session_kwh - max(0.0, remaining_kwh))
    return round(billed * rate, 2), "overage"


def validate_plan_fields(
    plan_type: str,
    *,
    monthly_fee_eur: float | None,
    kwh_allotment: float | None,
    price_per_kwh_eur: float | None,
    subscription_start_date: date | None,
    periodicity: str | None,
) -> str | None:
    if plan_type == "subscription":
        if monthly_fee_eur is None:
            return "monthly_fee_eur is required for subscription plans"
        if subscription_start_date is None:
            return "subscription_start_date is required for subscription plans"
        if periodicity not in ("monthly", "yearly"):
            return "periodicity must be monthly or yearly"
        if kwh_allotment is None and price_per_kwh_eur is None:
            return "subscription plans need kwh_allotment (included kWh) or price_per_kwh_eur (discounted rate)"
        return None
    if plan_type in ("home", "public"):
        if price_per_kwh_eur is None:
            return "price_per_kwh_eur is required for home and public plans"
        return None
    return "plan_type must be subscription, home, or public"


async def invalidate_user_vehicle_caches(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(select(UserVehicle.id).where(UserVehicle.user_id == user_id))
    for vehicle_id in result.scalars().all():
        await invalidate_vehicle_cache(str(vehicle_id))


async def load_user_plans(db: AsyncSession, user_id: uuid.UUID) -> list[UserChargingPlan]:
    result = await db.execute(
        select(UserChargingPlan)
        .options(selectinload(UserChargingPlan.geofence))
        .where(UserChargingPlan.user_id == user_id)
        .order_by(UserChargingPlan.created_at)
    )
    return list(result.scalars().all())


def match_plan_by_geofence(
    plans: list[UserChargingPlan],
    latitude: float | None,
    longitude: float | None,
) -> UserChargingPlan | None:
    if latitude is None or longitude is None:
        return None
    best: UserChargingPlan | None = None
    best_distance: float | None = None
    for plan in plans:
        geofence: Geofence | None = plan.geofence
        if geofence is None:
            continue
        distance = haversine_m(latitude, longitude, geofence.latitude, geofence.longitude)
        if distance <= geofence.radius_meters:
            if best_distance is None or distance < best_distance:
                best = plan
                best_distance = distance
    return best


async def kwh_used_in_period(
    db: AsyncSession,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    period_start: date,
    period_end: date,
    exclude_session_id: int | None = None,
) -> float:
    start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)
    stmt = (
        select(ChargingSession.energy_kwh)
        .join(UserVehicle, UserVehicle.id == ChargingSession.user_vehicle_id)
        .where(
            UserVehicle.user_id == user_id,
            ChargingSession.charging_plan_id == plan_id,
            ChargingSession.session_start >= start_dt,
            ChargingSession.session_start < end_dt,
            ChargingSession.energy_kwh.is_not(None),
        )
    )
    if exclude_session_id is not None:
        stmt = stmt.where(ChargingSession.id != exclude_session_id)
    result = await db.execute(stmt)
    return sum(float(row[0] or 0.0) for row in result.all())


async def compute_suggested_cost(
    db: AsyncSession,
    user_id: uuid.UUID,
    plan: UserChargingPlan,
    session: ChargingSession,
    energy_kwh: float | None = None,
) -> dict[str, Any]:
    energy = float(energy_kwh) if energy_kwh is not None else float(session.energy_kwh or 0.0)
    session_day: date | None = None
    if session.session_start is not None:
        session_day = session.session_start.date()

    allotment = _as_float(plan.kwh_allotment)
    price = _as_float(plan.price_per_kwh_eur)

    if plan.plan_type == "subscription" and allotment is not None:
        start = plan.subscription_start_date
        if start is None or session_day is None or session_day < start:
            return {
                "suggested_cost_eur": None,
                "reason": "before_start",
                "remaining_kwh": None,
                "allotment_kwh": allotment,
            }
        period = period_containing(start, plan.periodicity, session_day)
        if period is None:
            return {
                "suggested_cost_eur": None,
                "reason": "before_start",
                "remaining_kwh": None,
                "allotment_kwh": allotment,
            }
        used = await kwh_used_in_period(
            db, user_id, plan.id, period[0], period[1], exclude_session_id=session.id
        )
        remaining = max(0.0, allotment - used)
        cost, reason = session_cost_from_remaining(energy, remaining, overage_rate_eur(plan))
        return {
            "suggested_cost_eur": cost,
            "reason": reason,
            "remaining_kwh": round(remaining, 2),
            "allotment_kwh": allotment,
        }

    if price is None:
        return {
            "suggested_cost_eur": None,
            "reason": "no_rate",
            "remaining_kwh": None,
            "allotment_kwh": allotment,
        }
    return {
        "suggested_cost_eur": round(energy * price, 2),
        "reason": "per_kwh",
        "remaining_kwh": None,
        "allotment_kwh": allotment,
    }


async def suggest_cost_for_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    session: ChargingSession,
    plan_id: uuid.UUID | None = None,
    energy_kwh: float | None = None,
) -> dict[str, Any]:
    plans = await load_user_plans(db, user_id)
    matched_by: str | None = None
    chosen: UserChargingPlan | None = None

    if plan_id is not None:
        chosen = next((p for p in plans if p.id == plan_id), None)
        if chosen is None:
            return {
                "plan_id": None,
                "plan_name": None,
                "plan_type": None,
                "suggested_provider_name": None,
                "suggested_cost_eur": None,
                "reason": "plan_not_found",
                "remaining_kwh": None,
                "allotment_kwh": None,
                "matched_by": None,
            }
        matched_by = "plan_id"
    else:
        chosen = match_plan_by_geofence(plans, session.latitude, session.longitude)
        if chosen is not None:
            matched_by = "geofence"

    if chosen is None:
        return {
            "plan_id": None,
            "plan_name": None,
            "plan_type": None,
            "suggested_provider_name": None,
            "suggested_cost_eur": None,
            "reason": "no_match",
            "remaining_kwh": None,
            "allotment_kwh": None,
            "matched_by": None,
        }

    computed = await compute_suggested_cost(db, user_id, chosen, session, energy_kwh=energy_kwh)
    return {
        "plan_id": chosen.id,
        "plan_name": chosen.name,
        "plan_type": chosen.plan_type,
        "suggested_provider_name": chosen.name,
        "suggested_cost_eur": computed["suggested_cost_eur"],
        "reason": computed["reason"],
        "remaining_kwh": computed["remaining_kwh"],
        "allotment_kwh": computed["allotment_kwh"],
        "matched_by": matched_by,
    }


def window_for_fees(from_date: date | None, to_date: date | None, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = from_date or date(today.year - 20, 1, 1)
    end = (to_date + timedelta(days=1)) if to_date else (today + timedelta(days=1))
    return start, end
