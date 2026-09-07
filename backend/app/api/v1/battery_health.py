"""Battery Health v2 endpoints (public, vehicle-owner-scoped).

Endpoints:
  GET /api/v1/vehicles/{vehicle_id}/battery-health-analytics
    Cache-first read from battery_health_analytics where method='combined'.
    On miss or ?force_recompute=true, run all 6 methods + persist.
  POST /api/v1/admin/battery/vehicles/{vehicle_id}/recompute-analytics
    Admin-only force-recompute (see admin_battery.py for the canonical admin route).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.database import get_db
from app.models.telemetry import BatteryHealthAnalytics
from app.models.user import User
from app.models.vehicle import UserVehicle
from app.services.battery_health_v2 import (
    CombinedAnalytics,
    MethodResult,
    compute_full_analytics,
)


router = APIRouter()


@router.get("/vehicles/{vehicle_id}/battery-health-analytics")
async def get_battery_health_analytics(
    vehicle_id: UUID,
    lookback_days: int = Query(365, ge=30, le=730),
    force_recompute: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Battery health analytics for one vehicle. Cache-first; live-compute on miss.

    Returns the combined SoH + per-method breakdown from the v2 service.
    """
    veh = await _get_owned_vehicle(db, vehicle_id, user)
    if veh is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    if not force_recompute:
        cached_combined = await _latest_combined(db, vehicle_id)
        if cached_combined is not None:
            methods = await _latest_methods(db, vehicle_id, limit=7)
            return {
                "user_vehicle_id": str(vehicle_id),
                "soh_pct": cached_combined.soh_pct,
                "confidence": cached_combined.confidence,
                "estimated_kwh": cached_combined.estimated_kwh,
                "computed_at": cached_combined.computed_at.isoformat(),
                "cached": True,
                "methods": [_method_row_to_dict(m) for m in methods],
            }

    analytics = await compute_full_analytics(db, vehicle_id, lookback_days)
    await persist_analytics(db, analytics)
    return _analytics_to_dict(analytics, cached=False)


@router.post("/vehicles/{vehicle_id}/battery-health-analytics/recompute")
async def recompute_battery_health_analytics(
    vehicle_id: UUID,
    lookback_days: int = Query(365, ge=30, le=730),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Force recompute + persist (vehicle owner can re-trigger)."""
    veh = await _get_owned_vehicle(db, vehicle_id, user)
    if veh is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    analytics = await compute_full_analytics(db, vehicle_id, lookback_days)
    await persist_analytics(db, analytics)
    return _analytics_to_dict(analytics, cached=False)


async def _get_owned_vehicle(
    db: AsyncSession, vehicle_id: UUID, user: User
) -> UserVehicle | None:
    veh = await db.get(UserVehicle, vehicle_id)
    if veh is None:
        return None
    if veh.user_id != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not your vehicle")
    return veh


async def _latest_combined(
    db: AsyncSession, vehicle_id: UUID
) -> BatteryHealthAnalytics | None:
    return (await db.execute(
        select(BatteryHealthAnalytics)
        .where(BatteryHealthAnalytics.user_vehicle_id == vehicle_id)
        .where(BatteryHealthAnalytics.method == "combined")
        .order_by(desc(BatteryHealthAnalytics.computed_at))
        .limit(1)
    )).scalar_one_or_none()


async def _latest_methods(
    db: AsyncSession, vehicle_id: UUID, limit: int = 7
) -> List[BatteryHealthAnalytics]:
    rows = (await db.execute(
        select(BatteryHealthAnalytics)
        .where(BatteryHealthAnalytics.user_vehicle_id == vehicle_id)
        .order_by(desc(BatteryHealthAnalytics.computed_at))
        .limit(limit)
    )).scalars().all()
    return list(rows)


async def persist_analytics(db: AsyncSession, analytics: CombinedAnalytics) -> None:
    """Write one row per method + one 'combined' row to battery_health_analytics."""
    now = datetime.now(timezone.utc)
    for m in analytics.methods:
        row = BatteryHealthAnalytics(
            user_vehicle_id=analytics.user_vehicle_id,
            computed_at=now,
            method=m.method,
            soh_pct=m.soh_pct if m.soh_pct is not None else 0.0,
            estimated_kwh=_extract_kwh(m),
            sample_count=m.sample_count,
            confidence=m.confidence,
            inputs_json=m.inputs,
            extra_json=m.extra,
        )
        db.add(row)
    combined_row = BatteryHealthAnalytics(
        user_vehicle_id=analytics.user_vehicle_id,
        computed_at=now,
        method="combined",
        soh_pct=analytics.soh_pct if analytics.soh_pct is not None else 0.0,
        estimated_kwh=analytics.estimated_kwh,
        sample_count=sum(m.sample_count for m in analytics.methods),
        confidence=analytics.confidence,
        inputs_json=None,
        extra_json={"anomalies": analytics.anomalies},
    )
    db.add(combined_row)
    await db.commit()


def _extract_kwh(m: MethodResult) -> float | None:
    if m.method == "tesla_capacity":
        return m.extra.get("median_kwh")
    if m.method == "cell_imbalance":
        return m.extra.get("median_imbalance_mv")  # not kWh but closest persistable
    if m.method == "throughput":
        return m.extra.get("cycles")
    if m.method == "range_drift_over_time":
        return m.extra.get("retention_pct")
    return None


def _method_row_to_dict(row: BatteryHealthAnalytics) -> Dict[str, Any]:
    return {
        "method": row.method,
        "soh_pct": row.soh_pct,
        "estimated_kwh": row.estimated_kwh,
        "sample_count": row.sample_count,
        "confidence": row.confidence,
        "inputs": row.inputs_json,
        "extra": row.extra_json,
    }


def _analytics_to_dict(analytics: CombinedAnalytics, cached: bool) -> Dict[str, Any]:
    return {
        "user_vehicle_id": str(analytics.user_vehicle_id),
        "soh_pct": analytics.soh_pct,
        "confidence": analytics.confidence,
        "estimated_kwh": analytics.estimated_kwh,
        "computed_at": analytics.computed_at.isoformat(),
        "cached": cached,
        "methods": [m.to_dict() for m in analytics.methods],
        "anomalies": analytics.anomalies,
    }
