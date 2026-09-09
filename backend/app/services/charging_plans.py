"""Charging-plan period math, GPS match, and suggested session cost.

Cost rules:
- Included-kWh subscription: period fee is a prepaid bucket. Each tagged session
  consumes fee/allotment per kWh (e.g. 100 EUR / 300 kWh). After the allotment,
  extra kWh is billed at the public walk-up (overage) rate.
- Discounted-rate subscription (no allotment) and home/public: energy * price_per_kwh.
- Do not add the full period fee on top of included-kWh allocations (that double-counts).
  Discounted-rate subscriptions still treat the fee as a separate economics line item.
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


def included_allotment_kwh(plan: UserChargingPlan) -> float | None:
    allotment = _as_float(plan.kwh_allotment)
    if allotment is None or allotment <= 0:
        return None
    return allotment


def included_rate_eur(plan: UserChargingPlan) -> float | None:
    """Period fee divided by included kWh. Unrounded; callers round display values."""
    fee = _as_float(plan.monthly_fee_eur)
    allotment = included_allotment_kwh(plan)
    if fee is None or allotment is None:
        return None
    return fee / allotment


def overage_rate_eur(plan: UserChargingPlan) -> float | None:
    overage = _as_float(plan.overage_price_per_kwh_eur)
    if overage is not None:
        return overage
    return _as_float(plan.price_per_kwh_eur)


def session_cost_from_remaining(
    session_kwh: float,
    remaining_kwh: float | None,
    overage_rate: float | None = None,
    included_rate: float | None = None,
) -> tuple[float, str]:
    """Return (allocated cost, reason) for a session against an included-kWh bucket."""
    if remaining_kwh is None:
        rate = included_rate if included_rate is not None else overage_rate
        if rate is None:
            return 0.0, "per_kwh"
        return round(session_kwh * rate, 2), "per_kwh"
    remaining = max(0.0, remaining_kwh)
    included_kwh = min(session_kwh, remaining)
    extra_kwh = max(0.0, session_kwh - remaining)
    cost = 0.0
    if included_rate is not None:
        cost += included_kwh * included_rate
    extra_rate = overage_rate if overage_rate is not None else included_rate
    if extra_kwh > 0 and extra_rate is not None:
        cost += extra_kwh * extra_rate
    if extra_kwh <= 0:
        reason = "within_allotment"
    elif included_kwh <= 0:
        reason = "overage"
    else:
        reason = "mixed"
    return round(cost, 2), reason


def charger_payable_eur(
    session_kwh: float,
    remaining_kwh: float | None,
    overage_rate: float | None,
) -> float | None:
    """Amount typically paid at the charger (0 inside the allotment, overage after)."""
    if remaining_kwh is None:
        return None
    extra = max(0.0, session_kwh - max(0.0, remaining_kwh))
    if extra <= 0 or overage_rate is None:
        return 0.0
    return round(extra * overage_rate, 2)


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


def _period_bounds_utc(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)
    return start_dt, end_dt


async def sessions_for_plan_period(
    db: AsyncSession,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[ChargingSession]:
    start_dt, end_dt = _period_bounds_utc(period_start, period_end)
    stmt = (
        select(ChargingSession)
        .join(UserVehicle, UserVehicle.id == ChargingSession.user_vehicle_id)
        .where(
            UserVehicle.user_id == user_id,
            ChargingSession.charging_plan_id == plan_id,
            ChargingSession.session_start >= start_dt,
            ChargingSession.session_start < end_dt,
            ChargingSession.energy_kwh.is_not(None),
        )
        .order_by(ChargingSession.session_start.asc(), ChargingSession.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _session_sort_key(session: ChargingSession) -> tuple[datetime, int]:
    start = session.session_start
    if start is None:
        start = datetime.min.replace(tzinfo=timezone.utc)
    elif start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start, session.id


def kwh_before_session(sessions: list[ChargingSession], current: ChargingSession) -> float:
    """Energy already tagged on this plan before `current` in chronological order."""
    current_key = _session_sort_key(current)
    return sum(
        float(session.energy_kwh or 0.0)
        for session in sessions
        if session.id != current.id and _session_sort_key(session) < current_key
    )


def allocate_period_sessions(
    sessions: list[ChargingSession],
    plan: UserChargingPlan,
) -> dict[int, dict[str, Any]]:
    """Walk tagged sessions in order and assign allocated plan cost."""
    allotment = included_allotment_kwh(plan)
    inc_rate = included_rate_eur(plan)
    ov_rate = overage_rate_eur(plan)
    price = _as_float(plan.price_per_kwh_eur)
    by_session: dict[int, dict[str, Any]] = {}
    remaining = allotment
    for session in sorted(sessions, key=_session_sort_key):
        energy = float(session.energy_kwh or 0.0)
        if allotment is not None and remaining is not None:
            before = remaining
            cost, reason = session_cost_from_remaining(energy, before, ov_rate, inc_rate)
            included_kwh = min(energy, max(0.0, before))
            extra_kwh = max(0.0, energy - max(0.0, before))
            remaining = max(0.0, before - energy)
            remaining_fee = round(remaining * inc_rate, 2) if inc_rate is not None else None
            payable = charger_payable_eur(energy, before, ov_rate)
        elif price is not None:
            cost, reason = round(energy * price, 2), "per_kwh"
            included_kwh = energy
            extra_kwh = 0.0
            remaining_fee = None
            payable = cost
        else:
            continue
        by_session[session.id] = {
            "plan_id": str(plan.id),
            "plan_name": plan.name,
            "plan_type": plan.plan_type,
            "plan_cost_eur": cost,
            "reason": reason,
            "cost_label": "On plan",
            "included_kwh": round(included_kwh, 2),
            "overage_kwh": round(extra_kwh, 2),
            "remaining_after_kwh": round(remaining, 2) if remaining is not None else None,
            "remaining_after_fee_eur": remaining_fee,
            "included_rate_eur": round(inc_rate, 4) if inc_rate is not None else None,
            "suggested_paid_eur": payable,
        }
    return by_session


def _empty_suggestion(**overrides: Any) -> dict[str, Any]:
    payload = {
        "plan_id": None,
        "plan_name": None,
        "plan_type": None,
        "suggested_provider_name": None,
        "suggested_cost_eur": None,
        "suggested_paid_eur": None,
        "reason": "no_match",
        "remaining_kwh": None,
        "remaining_after_kwh": None,
        "remaining_fee_eur": None,
        "allotment_kwh": None,
        "included_rate_eur": None,
        "overage_rate_eur": None,
        "period_fee_eur": None,
        "matched_by": None,
    }
    payload.update(overrides)
    return payload


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

    allotment = included_allotment_kwh(plan)
    price = _as_float(plan.price_per_kwh_eur)
    inc_rate = included_rate_eur(plan)
    ov_rate = overage_rate_eur(plan)
    fee = _as_float(plan.monthly_fee_eur)

    if plan.plan_type == "subscription" and allotment is not None:
        start = plan.subscription_start_date
        if start is None or session_day is None or session_day < start:
            return {
                "suggested_cost_eur": None,
                "suggested_paid_eur": None,
                "reason": "before_start",
                "remaining_kwh": None,
                "remaining_after_kwh": None,
                "remaining_fee_eur": None,
                "allotment_kwh": allotment,
                "included_rate_eur": round(inc_rate, 4) if inc_rate is not None else None,
                "overage_rate_eur": ov_rate,
                "period_fee_eur": fee,
            }
        period = period_containing(start, plan.periodicity, session_day)
        if period is None:
            return {
                "suggested_cost_eur": None,
                "suggested_paid_eur": None,
                "reason": "before_start",
                "remaining_kwh": None,
                "remaining_after_kwh": None,
                "remaining_fee_eur": None,
                "allotment_kwh": allotment,
                "included_rate_eur": round(inc_rate, 4) if inc_rate is not None else None,
                "overage_rate_eur": ov_rate,
                "period_fee_eur": fee,
            }
        period_sessions = await sessions_for_plan_period(
            db, user_id, plan.id, period[0], period[1]
        )
        used = kwh_before_session(period_sessions, session)
        remaining = max(0.0, allotment - used)
        cost, reason = session_cost_from_remaining(energy, remaining, ov_rate, inc_rate)
        remaining_after = max(0.0, remaining - energy)
        remaining_fee = round(remaining_after * inc_rate, 2) if inc_rate is not None else None
        return {
            "suggested_cost_eur": cost,
            "suggested_paid_eur": charger_payable_eur(energy, remaining, ov_rate),
            "reason": reason,
            "remaining_kwh": round(remaining, 2),
            "remaining_after_kwh": round(remaining_after, 2),
            "remaining_fee_eur": remaining_fee,
            "allotment_kwh": allotment,
            "included_rate_eur": round(inc_rate, 4) if inc_rate is not None else None,
            "overage_rate_eur": ov_rate,
            "period_fee_eur": fee,
        }

    if price is None:
        return {
            "suggested_cost_eur": None,
            "suggested_paid_eur": None,
            "reason": "no_rate",
            "remaining_kwh": None,
            "remaining_after_kwh": None,
            "remaining_fee_eur": None,
            "allotment_kwh": allotment,
            "included_rate_eur": round(inc_rate, 4) if inc_rate is not None else None,
            "overage_rate_eur": ov_rate,
            "period_fee_eur": fee,
        }
    priced = round(energy * price, 2)
    return {
        "suggested_cost_eur": priced,
        "suggested_paid_eur": priced,
        "reason": "per_kwh",
        "remaining_kwh": None,
        "remaining_after_kwh": None,
        "remaining_fee_eur": None,
        "allotment_kwh": allotment,
        "included_rate_eur": round(inc_rate, 4) if inc_rate is not None else None,
        "overage_rate_eur": ov_rate,
        "period_fee_eur": fee,
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
            return _empty_suggestion(reason="plan_not_found")
        matched_by = "plan_id"
    else:
        chosen = match_plan_by_geofence(plans, session.latitude, session.longitude)
        if chosen is not None:
            matched_by = "geofence"

    if chosen is None:
        return _empty_suggestion()

    computed = await compute_suggested_cost(db, user_id, chosen, session, energy_kwh=energy_kwh)
    return {
        "plan_id": chosen.id,
        "plan_name": chosen.name,
        "plan_type": chosen.plan_type,
        "suggested_provider_name": chosen.name,
        "suggested_cost_eur": computed["suggested_cost_eur"],
        "suggested_paid_eur": computed.get("suggested_paid_eur"),
        "reason": computed["reason"],
        "remaining_kwh": computed["remaining_kwh"],
        "remaining_after_kwh": computed.get("remaining_after_kwh"),
        "remaining_fee_eur": computed.get("remaining_fee_eur"),
        "allotment_kwh": computed["allotment_kwh"],
        "included_rate_eur": computed.get("included_rate_eur"),
        "overage_rate_eur": computed.get("overage_rate_eur"),
        "period_fee_eur": computed.get("period_fee_eur"),
        "matched_by": matched_by,
    }


async def plan_costs_for_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    sessions: list[ChargingSession],
    plans: list[UserChargingPlan] | None = None,
) -> dict[int, dict[str, Any]]:
    """Allocated on-plan cost for each session, walking allotment in chronological order."""
    if not sessions:
        return {}
    plans = plans if plans is not None else await load_user_plans(db, user_id)
    plans_by_id = {p.id: p for p in plans}
    needed: dict[tuple[uuid.UUID, date, date], UserChargingPlan] = {}
    for session in sessions:
        if session.charging_plan_id is None:
            continue
        plan = plans_by_id.get(session.charging_plan_id)
        if plan is None or included_allotment_kwh(plan) is None:
            continue
        if session.session_start is None or plan.subscription_start_date is None:
            continue
        period = period_containing(
            plan.subscription_start_date, plan.periodicity, session.session_start.date()
        )
        if period is None:
            continue
        needed[(plan.id, period[0], period[1])] = plan

    by_session: dict[int, dict[str, Any]] = {}
    for (plan_id, period_start, period_end), plan in needed.items():
        period_sessions = await sessions_for_plan_period(
            db, user_id, plan_id, period_start, period_end
        )
        by_session.update(allocate_period_sessions(period_sessions, plan))

    for session in sessions:
        if session.id in by_session:
            continue
        if session.charging_plan_id is None:
            continue
        plan = plans_by_id.get(session.charging_plan_id)
        if plan is None:
            continue
        energy = float(session.energy_kwh or 0.0)
        price = _as_float(plan.price_per_kwh_eur)
        inc_rate = included_rate_eur(plan)
        cost = round(energy * price, 2) if price is not None else None
        by_session[session.id] = {
            "plan_id": str(plan.id),
            "plan_name": plan.name,
            "plan_type": plan.plan_type,
            "plan_cost_eur": cost,
            "reason": "per_kwh" if price is not None else "no_rate",
            "cost_label": "On plan" if price is not None else None,
            "included_kwh": round(energy, 2) if price is not None else 0.0,
            "overage_kwh": 0.0,
            "remaining_after_kwh": None,
            "remaining_after_fee_eur": None,
            "included_rate_eur": round(inc_rate, 4) if inc_rate is not None else None,
            "suggested_paid_eur": cost,
        }
    return by_session


def summarize_plan_usage(
    plan: UserChargingPlan,
    period: tuple[date, date] | None,
    period_sessions: list[ChargingSession],
) -> dict[str, Any]:
    allotment = included_allotment_kwh(plan)
    fee = _as_float(plan.monthly_fee_eur)
    inc_rate = included_rate_eur(plan)
    ov_rate = overage_rate_eur(plan)
    allocated_map = allocate_period_sessions(period_sessions, plan) if period_sessions else {}
    used_kwh = sum(float(s.energy_kwh or 0.0) for s in period_sessions)
    allocated_eur = sum(float(row["plan_cost_eur"] or 0.0) for row in allocated_map.values())
    overage_kwh = sum(float(row["overage_kwh"] or 0.0) for row in allocated_map.values())
    overage_eur = round(overage_kwh * ov_rate, 2) if ov_rate is not None else 0.0
    remaining_kwh = max(0.0, allotment - used_kwh) if allotment is not None else None
    used_pct = round(min(100.0, (used_kwh / allotment) * 100.0), 1) if allotment and allotment > 0 else None
    remaining_fee = (
        round(remaining_kwh * inc_rate, 2) if remaining_kwh is not None and inc_rate is not None else None
    )
    walk_up = round(used_kwh * ov_rate, 2) if ov_rate is not None else None
    saved = round(walk_up - allocated_eur, 2) if walk_up is not None else None
    return {
        "plan_id": str(plan.id),
        "plan_name": plan.name,
        "plan_type": plan.plan_type,
        "period_start": period[0].isoformat() if period else None,
        "period_end": period[1].isoformat() if period else None,
        "periodicity": plan.periodicity,
        "allotment_kwh": allotment,
        "used_kwh": round(used_kwh, 2),
        "remaining_kwh": round(remaining_kwh, 2) if remaining_kwh is not None else None,
        "used_pct": used_pct,
        "period_fee_eur": fee,
        "allocated_eur": round(allocated_eur, 2),
        "remaining_fee_eur": remaining_fee,
        "included_rate_eur": round(inc_rate, 4) if inc_rate is not None else None,
        "overage_rate_eur": ov_rate,
        "overage_kwh": round(overage_kwh, 2),
        "overage_eur": overage_eur,
        "sessions_count": len(period_sessions),
        "walk_up_eur": walk_up,
        "saved_vs_public_eur": max(0.0, saved) if saved is not None else None,
    }


async def current_subscription_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    plans = await load_user_plans(db, user_id)
    today = as_of or date.today()
    rows: list[dict[str, Any]] = []
    for plan in plans:
        if plan.plan_type != "subscription":
            continue
        period = None
        period_sessions: list[ChargingSession] = []
        if plan.subscription_start_date is not None:
            period = period_containing(plan.subscription_start_date, plan.periodicity, today)
            if period is not None:
                period_sessions = await sessions_for_plan_period(
                    db, user_id, plan.id, period[0], period[1]
                )
        rows.append(summarize_plan_usage(plan, period, period_sessions))
    return rows


def window_for_fees(from_date: date | None, to_date: date | None, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = from_date or date(today.year - 20, 1, 1)
    end = (to_date + timedelta(days=1)) if to_date else (today + timedelta(days=1))
    return start, end
