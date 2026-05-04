import asyncio
from collections import OrderedDict
from datetime import datetime, date, timedelta, timezone
from uuid import UUID
from typing import Any
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.database import get_db
from app.models.telemetry import Trip, ChargingSession, VehiclePosition, ChargingState, VehicleState, ConnectionState, BatteryHealth, PowerUsage, ChargingCurve, ChargingPower, DriveRangeEstimatedFull, DriveConsumption, ClimatizationState, OutsideTemperature, BatteryTemperature, WeconnectError
from app.models.user import User
from app.models.vehicle import UserVehicle
from app.schemas.telemetry import PulseResponse

from pydantic import BaseModel

router = APIRouter()

# =============================================================================
# Calibration & Engineering Constants
# =============================================================================
# Used by vampire drain analysis (get_vampire_drain). Edit here to tune thresholds.
VAMPIRE_DRAIN_DEFAULTS = {
    "min_parked_hours":    1.0,   # Ignore intervals shorter than this (not real vampire drain)
    "max_parked_hours":   72.0,   # Ignore intervals longer than this (BMS sleep / abnormal)
    "max_drain_rate_pct": 0.15,   # Max realistic vampire drain %/hr (exclude abnormal spikes)
    "max_dsoc_pct":       15.0,   # Max expected SoC drop in one parked interval (exclude outliers)
}

class ChargingSessionUpdate(BaseModel):
    actual_cost_eur: float
    energy_kwh: float
    provider_name: str | None = None

async def get_user_vehicle(user_id: UUID, vehicle_id: UUID, db: AsyncSession) -> UserVehicle:
    stmt = select(UserVehicle).where(UserVehicle.id == vehicle_id, UserVehicle.user_id == user_id)
    result = await db.execute(stmt)
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


def _calibration(vehicle: UserVehicle):
    """Return per-vehicle efficiency thresholds, falling back to app-level defaults."""
    return {
        "charger_power_kw":            vehicle.charger_power_kw             or 22.0,
        "ice_l_per_100km":             vehicle.ice_l_per_100km              or 8.0,
        "uphill_kwh_per_100km_per_100m": vehicle.uphill_kwh_per_100km_per_100m or 0.20,
        "downhill_kwh_per_100km_per_100m": vehicle.downhill_kwh_per_100km_per_100m or 0.15,
        "speed_city_threshold_kmh":    vehicle.speed_city_threshold_kmh    or 50.0,
        "speed_highway_threshold_kmh": vehicle.speed_highway_threshold_kmh or 90.0,
        "temp_cold_max_celsius":       vehicle.temp_cold_max_celsius       or 5.0,
        "temp_optimal_min_celsius":    vehicle.temp_optimal_min_celsius    or 15.0,
        "temp_optimal_max_celsius":    vehicle.temp_optimal_max_celsius    or 25.0,
    }


@router.get("/{vehicle_id}/analytics/efficiency")
async def get_efficiency_curve(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns average consumption mapped by temperature to visualize the 'Winter Penalty'."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    from sqlalchemy import table, column
    v_stats = table("v_winter_penalty_stats",
        column("user_vehicle_id"),
        column("temperature"),
        column("avg_consumption"),
        column("data_points")
    )
    
    stmt = (
        select(
            v_stats.c.temperature.label("temp"),
            v_stats.c.avg_consumption.label("avg_consumption_kwh_100km"),
            v_stats.c.data_points.label("trip_count")
        )
        .where(v_stats.c.user_vehicle_id == vehicle_id)
        .order_by(v_stats.c.temperature)
    )
    
    result = await db.execute(stmt)
    data = result.all()
    
    return [
        {
            "temperature_celsius": int(row.temp) if row.temp is not None else 0,
            "consumption_kwh_100km": round(float(row.avg_consumption_kwh_100km), 2) if row.avg_consumption_kwh_100km else 0,
            "trips_recorded": row.trip_count
        }
        for row in data
    ]

@router.get("/{vehicle_id}/analytics/charging-sessions")
async def get_charging_sessions(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=10000)
):
    """List recent charging sessions for the UI."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(ChargingSession)
        .where(ChargingSession.user_vehicle_id == vehicle_id)
        .order_by(ChargingSession.session_start.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "session_start": s.session_start.isoformat() if s.session_start else None,
            "session_end": s.session_end.isoformat() if s.session_end else None,
            "start_level": s.start_level,
            "end_level": s.end_level,
            "energy_kwh": round(s.energy_kwh, 2) if s.energy_kwh else None,
            "base_cost_eur": round(s.base_cost_eur, 2) if s.base_cost_eur else None,
            "actual_cost_eur": round(s.actual_cost_eur, 2) if s.actual_cost_eur else None,
            "provider_name": s.provider_name,
            "avg_temp_celsius": round(s.avg_temp_celsius, 1) if s.avg_temp_celsius else None,
        }
        for s in sessions
    ]

@router.patch("/{vehicle_id}/analytics/charging-sessions/{session_id}")
async def update_charging_session(
    vehicle_id: UUID,
    session_id: int,
    payload: ChargingSessionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Allow users to manually override the automated charging session deltas with exact receipt data."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = select(ChargingSession).where(
        ChargingSession.id == session_id,
        ChargingSession.user_vehicle_id == vehicle_id
    )
    result = await db.execute(stmt)
    session_obj = result.scalar_one_or_none()
    
    if not session_obj:
        raise HTTPException(status_code=404, detail="Charging session not found")
        
    session_obj.actual_cost_eur = payload.actual_cost_eur
    session_obj.energy_kwh = payload.energy_kwh
    if payload.provider_name is not None:
        session_obj.provider_name = payload.provider_name
        
    await db.commit()
    return {"status": "success", "message": "Charging session updated"}


@router.get("/{vehicle_id}/analytics/pulse", response_model=PulseResponse)
async def get_live_pulse(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns the live state of the car, combining charging, position, and weather."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    pos_res = await db.execute(
        select(VehiclePosition)
        .where(VehiclePosition.user_vehicle_id == vehicle_id)
        .order_by(VehiclePosition.captured_at.desc()).limit(1)
    )
    pos = pos_res.scalar_one_or_none()
    
    charge_res = await db.execute(
        select(ChargingState)
        .where(ChargingState.user_vehicle_id == vehicle_id)
        .order_by(ChargingState.first_date.desc()).limit(1)
    )
    charge = charge_res.scalar_one_or_none()
    
    conn_res = await db.execute(
        select(ConnectionState)
        .where(ConnectionState.user_vehicle_id == vehicle_id)
        .order_by(ConnectionState.captured_at.desc()).limit(1)
    )
    conn = conn_res.scalar_one_or_none()

    pulse = {
        "status": "PARKED",
        "battery_pct": 0,
        "remaining_range_km": 0,
        "temperature_celsius": None,
        "weather_code": None,
        "is_online": False,
        "charging_power_kw": 0,
        "remaining_charge_time_min": 0,
    }

    if conn:
        pulse["is_online"] = bool(conn.is_online)
        if conn.in_motion:
            pulse["status"] = "DRIVING"

    if charge:
        pulse["battery_pct"] = charge.battery_pct or 0
        pulse["remaining_range_km"] = int((charge.remaining_range_m or 0) / 1000)
        
        if charge.state in ("CHARGING", "READY_FOR_CHARGING"):
            pulse["status"] = "CHARGING"
            pulse["charging_power_kw"] = charge.charge_power_kw or 0
            pulse["remaining_charge_time_min"] = charge.remaining_time_min or 0

    if pos:
        pulse["temperature_celsius"] = pos.outside_temp_celsius
        pulse["weather_code"] = pos.weather_condition
        
    return pulse


@router.get("/{vehicle_id}/analytics/battery-health")
async def get_battery_health(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=10000)
):
    """Return battery health metrics including HV system, cell voltages, and derived SoH.
    
    Provides two SoH values:
    - skoda_soh_pct: raw hv_battery_soh from Skoda BMS (may be stale/cached)
    - derived_soh_pct: our own estimate from charging sessions (energy / delta_soc)
    - derived_capacity_kwh: our estimated current full capacity in kWh
    """
    await get_user_vehicle(user.id, vehicle_id, db)

    # Fetch latest Skoda BMS reading
    stmt_bh = (
        select(BatteryHealth)
        .where(BatteryHealth.user_vehicle_id == vehicle_id)
        .order_by(BatteryHealth.captured_at.desc())
        .limit(1)
    )
    bh_result = await db.execute(stmt_bh)
    latest_bh = bh_result.scalar_one_or_none()

    # Fetch factory battery capacity for this vehicle
    vehicle_stmt = select(UserVehicle.battery_capacity_kwh).where(UserVehicle.id == vehicle_id)
    vehicle_result = await db.execute(vehicle_stmt)
    factory_kwh = vehicle_result.scalar_one_or_none()

    # Compute SoH estimates from charging sessions
    # Filter: ΔSOC 15-65% (avoid short charges and regen-heavy large charges)
    # Cap: estimated capacity ≤ 103% of factory (excludes regen-inflated values)
    soh_stmt = text("""
        SELECT 
            session_start::date as charge_date,
            start_level,
            end_level,
            energy_kwh,
            ROUND((energy_kwh / ((end_level - start_level)/100.0))::numeric, 2) as estimated_kwh,
            ROUND(((energy_kwh / ((end_level - start_level)/100.0)) / :factory_kwh * 100)::numeric, 1) as soh_pct,
            (end_level - start_level) as delta_soc
        FROM charging_sessions
        WHERE user_vehicle_id = :vehicle_id
          AND end_level IS NOT NULL AND start_level IS NOT NULL
          AND energy_kwh IS NOT NULL AND energy_kwh > 0
          AND (end_level - start_level) BETWEEN 15 AND 65
        ORDER BY session_start DESC
        LIMIT 50
    """)
    soh_result = await db.execute(soh_stmt, {"vehicle_id": str(vehicle_id), "factory_kwh": factory_kwh})
    soh_estimates = soh_result.fetchall()

    # Build monthly averaged curve (last 6 months)
    curve_data = []
    valid = []
    latest_derived = None
    latest_derived_kwh = None

    if not factory_kwh or factory_kwh <= 0:
        return {
            "skoda_soh_pct": latest_bh.hv_battery_soh if latest_bh else None,
            "skoda_degradation_pct": latest_bh.hv_battery_degradation_pct if latest_bh else None,
            "factory_capacity_kwh": factory_kwh,
            "derived_soh_pct": None,
            "derived_capacity_kwh": None,
            "total_soh_estimates": len(soh_estimates) if soh_estimates else 0,
            "curve": [],
        }

    if soh_estimates:
        # Filter valid estimates (≤ 103% of factory — excludes regen noise)
        limit_kwh = float(factory_kwh) * 1.03
        valid = [r for r in soh_estimates if r.estimated_kwh and float(r.estimated_kwh) <= limit_kwh]
        if valid:
            # Group by month
            from collections import defaultdict
            by_month: dict[str, list[float]] = defaultdict(list)
            for r in valid:
                month = str(r.charge_date)[:7]  # "YYYY-MM"
                by_month[month].append(float(r.estimated_kwh))
            for month in sorted(by_month.keys()):
                vals = by_month[month]
                avg_kwh = round(sum(vals) / len(vals), 2)
                soh_pct = round((avg_kwh / float(factory_kwh)) * 100, 1)
                curve_data.append({
                    "month": month,
                    "estimated_kwh": avg_kwh,
                    "soh_pct": soh_pct,
                    "sample_count": len(vals),
                })

    # Latest derived SoH (most recent valid estimate)
    if valid:
        latest_derived = round((float(valid[0].estimated_kwh) / float(factory_kwh)) * 100, 1)
        latest_derived_kwh = float(valid[0].estimated_kwh)

    return {
        "skoda_soh_pct": latest_bh.hv_battery_soh if latest_bh else None,
        "skoda_degradation_pct": latest_bh.hv_battery_degradation_pct if latest_bh else None,
        "factory_capacity_kwh": factory_kwh,
        "derived_soh_pct": latest_derived,
        "derived_capacity_kwh": latest_derived_kwh if latest_derived else None,
        "total_soh_estimates": len(soh_estimates) if soh_estimates else 0,
        "curve": curve_data,
    }

@router.get("/{vehicle_id}/analytics/power-usage")
async def get_power_usage(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=10000)
):
    """Return detailed power consumption breakdown over time."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(PowerUsage)
        .where(PowerUsage.user_vehicle_id == vehicle_id)
        .order_by(PowerUsage.captured_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    return [
        {
            "captured_at": r.captured_at.isoformat(),
            "total_power_kw": r.total_power_kw,
            "motor_power_kw": r.motor_power_kw,
            "hvac_power_kw": r.hvac_power_kw,
            "auxiliary_power_kw": r.auxiliary_power_kw,
            "battery_heater_power_kw": r.battery_heater_power_kw,
        }
        for r in records
    ]

@router.get("/{vehicle_id}/analytics/charging-curves")
async def get_charging_curves(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=10000)
):
    """Return charging curve points (power/voltage vs SoC)."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(ChargingCurve)
        .where(ChargingCurve.user_vehicle_id == vehicle_id)
        .order_by(ChargingCurve.captured_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    return [
        {
            "captured_at": r.captured_at.isoformat(),
            "soc_pct": r.soc_pct,
            "power_kw": r.power_kw,
            "voltage_v": r.voltage_v,
            "current_a": r.current_a,
            "battery_temp_celsius": r.battery_temp_celsius,
            "charger_temp_celsius": r.charger_temp_celsius,
        }
        for r in records
    ]


@router.get("/{vehicle_id}/analytics/legacy/charging-power-curve")
async def get_legacy_charging_power_curve(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=500, ge=1, le=10000)
):
    """Query 41 & 51: Real-time charging power curve."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(ChargingPower)
        .where(ChargingPower.user_vehicle_id == vehicle_id)
        .order_by(ChargingPower.first_date.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    return [
        {
            "time": r.first_date.isoformat(),
            "power": r.power
        }
        for r in records
    ]

@router.get("/{vehicle_id}/analytics/legacy/power-vs-battery-temp")
async def get_legacy_power_vs_battery_temp(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Query 29: Charging power Min/Avg/Max grouped by Battery Temperature."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    # We'll map it natively through a raw query-like aggregation
    stmt = (
        select(
            func.round(BatteryTemperature.battery_temperature).label("temp"),
            func.min(ChargingPower.power).label("min_p"),
            func.avg(ChargingPower.power).label("avg_p"),
            func.max(ChargingPower.power).label("max_p")
        )
        .join(ChargingPower, ChargingPower.user_vehicle_id == BatteryTemperature.user_vehicle_id)
        .where(BatteryTemperature.user_vehicle_id == vehicle_id)
        .where(BatteryTemperature.first_date == ChargingPower.first_date) # Approximation for overlapping time
        .group_by("temp")
        .order_by("temp")
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    return [
        {
            "battery_temperature": int(row.temp) if row.temp is not None else 0,
            "min_power": round(float(row.min_p), 2) if row.min_p else 0,
            "avg_power": round(float(row.avg_p), 2) if row.avg_p else 0,
            "max_power": round(float(row.max_p), 2) if row.max_p else 0,
        }
        for row in rows
    ]

@router.get("/{vehicle_id}/analytics/legacy/errors")
async def get_legacy_weconnect_errors(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Query 48: Connection Errors over time."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(WeconnectError)
        .where(WeconnectError.user_vehicle_id == vehicle_id)
        .order_by(WeconnectError.datetime.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    return [
        {
            "datetime": r.datetime.isoformat(),
            "error_text": r.error_text
        }
        for r in records
    ]
    
@router.get("/{vehicle_id}/analytics/legacy/climatization")
async def get_legacy_climatization(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Query 58: Climatization states over time."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(ClimatizationState)
        .where(ClimatizationState.user_vehicle_id == vehicle_id)
        .order_by(ClimatizationState.first_date.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    return [
        {
            "time": r.first_date.isoformat(),
            "state": r.state
        }
        for r in records
    ]


@router.get("/{vehicle_id}/analytics/movement-stats")
async def get_movement_stats(
    vehicle_id: UUID,
    from_date: datetime = Query(...),
    to_date: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns accurate time-budget breakdown using real vehicle_states and charging_states."""
    await get_user_vehicle(user.id, vehicle_id, db)

    # Ensure from_date/to_date are timezone-aware (UTC) so comparisons with
    # timezone-aware DB columns (vehicle_states, charging_states) don't fail
    if from_date.tzinfo is None:
        from_date = from_date.replace(tzinfo=timezone.utc)
    if to_date.tzinfo is None:
        to_date = to_date.replace(tzinfo=timezone.utc)

    # Query vehicle states in range
    vs_stmt = (
        select(VehicleState)
        .where(
            VehicleState.user_vehicle_id == vehicle_id,
            VehicleState.first_date < to_date,
            VehicleState.last_date > from_date,
        )
        .order_by(VehicleState.first_date)
    )
    vs_result = await db.execute(vs_stmt)
    vs_rows = vs_result.scalars().all()

    # Query charging states in range
    cs_stmt = (
        select(ChargingState)
        .where(
            ChargingState.user_vehicle_id == vehicle_id,
            ChargingState.first_date < to_date,
            ChargingState.last_date > from_date,
            ChargingState.state == "CHARGING",
        )
        .order_by(ChargingState.first_date)
    )
    cs_result = await db.execute(cs_stmt)
    cs_rows = cs_result.scalars().all()

    def clamp_seconds(row_first, row_last, period_from, period_to) -> float:
        start = max(row_first, period_from)
        end = min(row_last, period_to)
        return max(0.0, (end - start).total_seconds())

    parked_s = driving_s = offline_s = ignition_s = 0.0
    for row in vs_rows:
        secs = clamp_seconds(row.first_date, row.last_date, from_date, to_date)
        state = (row.state or "").upper()
        if state == "PARKED":
            parked_s += secs
        elif state == "DRIVING":
            driving_s += secs
        elif state == "OFFLINE":
            offline_s += secs
        elif state == "IGNITION_ON":
            ignition_s += secs

    charging_s = 0.0
    for row in cs_rows:
        charging_s += clamp_seconds(row.first_date, row.last_date, from_date, to_date)

    return {
        "parked_seconds": round(parked_s),
        "driving_seconds": round(driving_s),
        "charging_seconds": round(charging_s),
        "offline_seconds": round(offline_s),
        "ignition_seconds": round(ignition_s),
        "total_seconds": round(parked_s + driving_s + offline_s + ignition_s),
    }


@router.get("/{vehicle_id}/analytics/time-budget")
async def get_time_budget(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    All-time time budget, fully aggregated in the DB.
    - vehicle_states with first_date != last_date: sum duration directly (PARKED, DRIVING, etc.)
    - charging_states (CHARGING snapshots): reconstruct sessions via gap detection (gap > 30 min = new session),
      add 5 min per session to cover the last snapshot interval.
    Returns totals in seconds per category.
    """
    await get_user_vehicle(user.id, vehicle_id, db)

    # -- Vehicle state durations (from view) --
    vs_sql = """
        SELECT state, SUM(duration_seconds) AS total_seconds
        FROM v_vehicle_state_durations
        WHERE user_vehicle_id = :vid
        GROUP BY state
    """
    vs_result = await db.execute(text(vs_sql), {"vid": str(vehicle_id)})
    vs_rows = vs_result.fetchall()

    state_seconds: dict[str, float] = {}
    for row in vs_rows:
        state_seconds[row[0].upper()] = float(row[1] or 0)

    # -- Charging: sum durations from analytics view --
    cs_sql = """
        SELECT COALESCE(SUM(duration_seconds), 0) AS total_seconds
        FROM v_charging_sessions_analytics
        WHERE user_vehicle_id = :vid
    """
    cs_result = await db.execute(text(cs_sql), {"vid": str(vehicle_id)})
    charging_seconds = float(cs_result.scalar() or 0)

    return {
        "parked_seconds":   round(state_seconds.get("PARKED", 0)),
        "driving_seconds":  round(state_seconds.get("DRIVING", 0)),
        "charging_seconds": round(charging_seconds),
        "ignition_seconds": round(state_seconds.get("IGNITION_ON", 0)),
        "offline_seconds":  round(state_seconds.get("OFFLINE", 0)),
    }

@router.get("/{vehicle_id}/analytics/charging-curve-integrals")
async def get_charging_curve_integrals(
    vehicle_id: UUID,
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Plot Charging Power (kW) over SoC (%) and calculate the "wasted time"
    (time spent charging from 80% to 100%).
    """
    vehicle = await get_user_vehicle(user.id, vehicle_id, db)
    cal = _calibration(vehicle)
    min_power_filter = cal["charger_power_kw"] * 0.5  # Exclude AC charging (half of vehicle max)

    # 1. Curve data: Average Power kW per SoC %
    # Using ChargingState for a more consistent representation across all sessions
    stmt_curve = (
        select(
            ChargingState.battery_pct.label("soc"),
            func.avg(ChargingState.charge_power_kw).label("avg_power"),
            func.max(ChargingState.charge_power_kw).label("max_power"),
            func.count(ChargingState.id).label("samples")
        )
        .where(
            ChargingState.user_vehicle_id == vehicle_id,
            ChargingState.state == "CHARGING",
            ChargingState.charge_power_kw > min_power_filter,  # Exclude slow AC charging (HC-015)
            ChargingState.battery_pct.is_not(None)
        )
    )
    if from_date:
        stmt_curve = stmt_curve.where(ChargingState.first_date >= from_date)
    if to_date:
        stmt_curve = stmt_curve.where(ChargingState.first_date <= to_date)
        
    stmt_curve = (
        stmt_curve
        .group_by(ChargingState.battery_pct)
        .order_by(ChargingState.battery_pct)
    )
    result_curve = await db.execute(stmt_curve)
    curve_data = result_curve.all()
    
    curve = [
        {
            "soc_pct": row.soc,
            "avg_power_kw": round(float(row.avg_power), 2),
            "max_power_kw": round(float(row.max_power), 2),
            "samples": row.samples
        }
        for row in curve_data
    ]

    # 2. Time wasted calculation: duration of charging >= 80%
    from sqlalchemy import case
    
    # We want average time per charging session.
    # We'll calculate the sum of duration for each category, and also count the number of distinct charging days/sessions.
    # To simplify, we sum the time, then divide by the approximate number of sessions.
    
    stmt_metrics = (
        select(
            case(
                (ChargingState.battery_pct >= 80, "wasted"),
                else_="fast"
            ).label("category"),
            func.sum(
                func.least(
                    func.greatest(0, func.extract("epoch", ChargingState.last_date - ChargingState.first_date)),
                    1800
                )
            ).label("total_seconds")
        )
        .where(
            ChargingState.user_vehicle_id == vehicle_id,
            ChargingState.state == "CHARGING"
        )
    )
    if from_date:
        stmt_metrics = stmt_metrics.where(ChargingState.first_date >= from_date)
    if to_date:
        stmt_metrics = stmt_metrics.where(ChargingState.first_date <= to_date)
        
    stmt_metrics = stmt_metrics.group_by("category")
    
    res = await db.execute(stmt_metrics)
    metrics_map = {row.category: row.total_seconds for row in res.all()}
    
    # Let's count approximate distinct charging sessions in this period
    # Grouping by date of first_date is a simple proxy for distinct sessions
    stmt_sessions = (
        select(func.count(func.distinct(func.date(ChargingState.first_date))))
        .where(
            ChargingState.user_vehicle_id == vehicle_id,
            ChargingState.state == "CHARGING"
        )
    )
    if from_date:
        stmt_sessions = stmt_sessions.where(ChargingState.first_date >= from_date)
    if to_date:
        stmt_sessions = stmt_sessions.where(ChargingState.first_date <= to_date)
        
    res_sessions = await db.execute(stmt_sessions)
    session_count = res_sessions.scalar() or 1
    if session_count < 1:
        session_count = 1
    
    wasted_seconds = metrics_map.get("wasted", 0.0) or 0.0
    fast_charge_seconds = metrics_map.get("fast", 0.0) or 0.0

    wasted_minutes = round((wasted_seconds / session_count) / 60)
    fast_charge_minutes = round((fast_charge_seconds / session_count) / 60)

    return {
        "curve": curve,
        "metrics": {
            "wasted_minutes_80_100": wasted_minutes,
            "fast_charge_minutes_0_80": fast_charge_minutes,
            "total_charging_minutes": wasted_minutes + fast_charge_minutes,
            "session_count": session_count
        }
    }

@router.get("/{vehicle_id}/analytics/advanced-overview")
async def get_advanced_analytics_overview(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns a summarized overview of advanced analytics:
    - Efficiency stats (Short/Med/Long)
    - Weather impact (Cold vs Warm)
    - Phantom Drain
    - Energy/Cost summaries
    """
    await get_user_vehicle(user.id, vehicle_id, db)

    # 1. Trip Stats
    trip_sql = text("""
        SELECT short_trips_count, medium_trips_count, long_trips_count, total_trips,
               avg_eff_cold, avg_eff_warm, avg_eff_overall
        FROM v_advanced_trip_stats
        WHERE user_vehicle_id = :vid
    """)
    trip_res = await db.execute(trip_sql, {"vid": str(vehicle_id)})
    trip_row = trip_res.fetchone()

    # 2. Phantom Drain
    drain_sql = text("""
        SELECT avg_drain_pct_per_day
        FROM v_phantom_drain_stats
        WHERE user_vehicle_id = :vid
    """)
    drain_res = await db.execute(drain_sql, {"vid": str(vehicle_id)})
    drain_row = drain_res.fetchone()

    # 3. Energy Prices
    energy_price = None
    country_code = "LT"
    v_res = await db.execute(select(UserVehicle).where(UserVehicle.id == vehicle_id))
    veh = v_res.scalar_one_or_none()
    if veh:
        country_code = getattr(veh, "country_code", "LT")
        from app.models.fuel_price import FuelPrice, CountryEconomics
        
        # Get latest electricity price for country
        eco_res = await db.execute(
            select(CountryEconomics)
            .where(CountryEconomics.country_code == country_code)
            .order_by(CountryEconomics.date.desc())
            .limit(1)
        )
        eco = eco_res.scalar_one_or_none()
        elec_price = float(eco.electricity_price_kwh_eur) if eco and eco.electricity_price_kwh_eur else 0.25
        
        # Get latest petrol price for country
        fuel_res = await db.execute(
            select(FuelPrice)
            .where(FuelPrice.country_code == country_code)
            .where(FuelPrice.fuel_type == "Euro95")
            .order_by(FuelPrice.week_date.desc())
            .limit(1)
        )
        fuel = fuel_res.scalar_one_or_none()
        petrol_price = float(fuel.price_eur_liter) if fuel and fuel.price_eur_liter else 1.65
    else:
        elec_price = 0.25
        petrol_price = 1.65

    # 4. Actual Charging Prices
    actual_price_sql = text("""
        SELECT SUM(actual_cost_eur) / SUM(energy_kwh) as avg_price 
        FROM charging_sessions 
        WHERE user_vehicle_id = :vid AND actual_cost_eur IS NOT NULL AND energy_kwh > 0
    """)
    actual_price_res = await db.execute(actual_price_sql, {"vid": str(vehicle_id)})
    actual_price_row = actual_price_res.fetchone()
    actual_avg_price = float(actual_price_row[0]) if actual_price_row and actual_price_row[0] else None

    # Safe math fallbacks
    overall_eff = float(trip_row[6]) if trip_row and trip_row[6] else 18.5
    cold_eff = float(trip_row[4]) if trip_row and trip_row[4] else overall_eff
    warm_eff = float(trip_row[5]) if trip_row and trip_row[5] else overall_eff
    cold_penalty = ((cold_eff - warm_eff) / warm_eff * 100) if warm_eff > 0 else 0

    # Build response with dynamic data and safe fallbacks
    return {
        "efficiency": {
            "avg_kwh_100km": round(overall_eff, 1),
            "cold_penalty_pct": round(cold_penalty, 1),
            "cold_eff_kwh_100km": round(cold_eff, 1),
            "warm_eff_kwh_100km": round(warm_eff, 1),
        },
        "trip_types": {
            "short_pct": round(float(trip_row[0]) / float(trip_row[3]) * 100 if trip_row and trip_row[3] > 0 else 0, 1),
            "medium_pct": round(float(trip_row[1]) / float(trip_row[3]) * 100 if trip_row and trip_row[3] > 0 else 0, 1),
            "long_pct": round(float(trip_row[2]) / float(trip_row[3]) * 100 if trip_row and trip_row[3] > 0 else 0, 1),
        },
        "phantom_drain": {
            "pct_per_day": round(float(drain_row[0]), 2) if drain_row and drain_row[0] is not None else 0.0,
        },
        "energy_prices": {
            "country_code": country_code,
            "electricity_eur_kwh": elec_price,
            "petrol_eur_l": petrol_price,
            "user_avg_electricity_eur_kwh": actual_avg_price,
        }
    }


@router.get("/{vehicle_id}/analytics/hvac-isolation")
async def get_hvac_isolation(
    vehicle_id: UUID,
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Analyzes trips with similar speeds to isolate the kWh cost of heating/cooling.
    Uses per-vehicle speed and temperature thresholds from calibration.
    """
    vehicle = await get_user_vehicle(user.id, vehicle_id, db)
    cal = _calibration(vehicle)
    city_thresh = cal["speed_city_threshold_kmh"]
    hw_thresh = cal["speed_highway_threshold_kmh"]
    cold_max = cal["temp_cold_max_celsius"]
    opt_min = cal["temp_optimal_min_celsius"]
    opt_max = cal["temp_optimal_max_celsius"]
    
    stmt = select(
        Trip.distance_km,
        Trip.kwh_consumed,
        Trip.avg_temp_celsius,
        Trip.start_date,
        Trip.end_date
    ).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.distance_km > 2,
        Trip.kwh_consumed.is_not(None),
        Trip.kwh_consumed > 0,
        Trip.avg_temp_celsius.is_not(None),
        Trip.end_date.is_not(None)
    )

    if from_date:
        stmt = stmt.where(Trip.start_date >= from_date)
    if to_date:
        stmt = stmt.where(Trip.start_date <= to_date)
        
    res = await db.execute(stmt)
    rows = res.fetchall()
    
    buckets = {
        "city": {"cold": [], "optimal": []},
        "mixed": {"cold": [], "optimal": []},
        "highway": {"cold": [], "optimal": []}
    }
    
    for r in rows:
        dist = r.distance_km
        kwh = r.kwh_consumed
        temp = r.avg_temp_celsius
        duration_h = (r.end_date - r.start_date).total_seconds() / 3600.0
        
        if duration_h < 0.001 or dist <= 0:
            continue
            
        speed = dist / duration_h
        eff = (kwh / dist) * 100.0
        
        s_cat = "mixed"
        if speed < city_thresh:
            s_cat = "city"
        elif speed > hw_thresh:
            s_cat = "highway"

        t_cat = None
        if temp <= cold_max:
            t_cat = "cold"
        elif opt_min <= temp <= opt_max:
            t_cat = "optimal"
            
        if t_cat:
            buckets[s_cat][t_cat].append(eff)
            
    results = []
    for s_cat, t_data in buckets.items():
        cold_list = t_data["cold"]
        opt_list = t_data["optimal"]
        
        if len(cold_list) > 0 and len(opt_list) > 0:
            avg_cold = sum(cold_list) / len(cold_list)
            avg_opt = sum(opt_list) / len(opt_list)
            
            diff = max(0, avg_cold - avg_opt)
            
            results.append({
                "speed_profile": s_cat,
                "avg_speed_desc": f"0-{city_thresh:.0f} km/h" if s_cat == "city" else f"{city_thresh:.0f}-{hw_thresh:.0f} km/h" if s_cat == "mixed" else "90+ km/h",
                "cold_trips": len(cold_list),
                "optimal_trips": len(opt_list),
                "optimal_kwh_100km": round(avg_opt, 1),
                "cold_kwh_100km": round(avg_cold, 1),
                "hvac_cost_kwh_100km": round(diff, 1) if diff > 0 else 0,
                "message": f"Heating costs ~{round(diff, 1) if diff > 0 else 0} kWh/100km at ≤5°C for {s_cat} driving."
            })
            
    return {
        "metrics": results,
        "summary": "Compared cold (≤5°C) vs optimal (15-25°C) temperatures across similar speed profiles to isolate HVAC/heating auxiliary power usage."
    }



# =============================================================================
# TASK 2: HVAC / Auxiliary Power Isolation (temperature band group)
# =============================================================================
@router.get("/{vehicle_id}/analytics/hvac-cost")
async def get_hvac_cost(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
):
    """
    Groups trips into temperature bands and compares cold vs warm trips at similar
    avg speeds to isolate HVAC/auxiliary power cost.
    Bands: < -10°C, -10 to 0°C, 0-10°C, 10-20°C, > 20°C.
    Output: "Heating costs you ~X.X kWh/100km at -5°C"
    """
    vehicle = await get_user_vehicle(user.id, vehicle_id, db)
    cal = _calibration(vehicle)
    city_thresh = cal["speed_city_threshold_kmh"]
    hw_thresh = cal["speed_highway_threshold_kmh"]

    # Temperature band edges
    TEMP_BANDS = [
        ("<-10°C",       -999,  -10),
        ("-10-0°C",      -10,    0),
        ("0-10°C",         0,   10),
        ("10-20°C",      10,   20),
        (">20°C",         20,  999),
    ]

    stmt = select(
        Trip.distance_km,
        Trip.kwh_consumed,
        Trip.avg_temp_celsius,
        Trip.start_date,
        Trip.end_date,
    ).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.distance_km > 2,
        Trip.kwh_consumed.is_not(None),
        Trip.kwh_consumed > 0,
        Trip.avg_temp_celsius.is_not(None),
        Trip.end_date.is_not(None),
    ).order_by(Trip.start_date.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    rows = res.fetchall()

    # bucket[band_label][speed_cat] = list of efficiencies
    bucket: dict[str, dict[str, list[float]]] = {
        b[0]: {"city": [], "mixed": [], "highway": []}
        for b in TEMP_BANDS
    }

    for r in rows:
        dist = r.distance_km or 0
        kwh = r.kwh_consumed or 0
        temp = r.avg_temp_celsius or 0
        duration_h = (r.end_date - r.start_date).total_seconds() / 3600.0
        if duration_h < 0.001 or dist <= 0:
            continue

        speed = dist / duration_h
        eff = (kwh / dist) * 100.0

        s_cat = "mixed"
        if speed < city_thresh:
            s_cat = "city"
        elif speed > hw_thresh:
            s_cat = "highway"


        for band_label, lo, hi in TEMP_BANDS:
            if lo < temp <= hi or (lo == -999 and temp <= hi) or (hi == 999 and temp > lo):
                bucket[band_label][s_cat].append(eff)
                break

    # Pick reference band = 10-20°C or 0-10°C as "no HVAC needed"
    # Track which band(s) actually contributed data
    reference_bands = ["10-20°C", "0-10°C"]
    reference_effs: list[float] = []
    active_reference_band: str | None = None
    for rb in reference_bands:
        for sc in ["city", "mixed", "highway"]:
            effs = bucket[rb][sc]
            if effs:
                reference_effs.extend(effs)
                if active_reference_band is None:
                    active_reference_band = rb
    ref_avg = (sum(reference_effs) / len(reference_effs)) if reference_effs else None
    reference_band_label = f"{active_reference_band} (no HVAC needed baseline)" if active_reference_band else "10-20°C (no HVAC needed baseline)"


    results: list[dict] = []
    cold_ref_temp = -5.0  # representative cold temperature

    for band_label, lo, hi in TEMP_BANDS:
        band_data = bucket[band_label]
        # Use city+mixed combined as representative
        all_effs: list[float] = band_data["city"] + band_data["mixed"]
        if not all_effs:
            continue

        band_avg = sum(all_effs) / len(all_effs)
        count = len(all_effs)
        diff = 0.0
        if ref_avg is not None:
            diff = max(0, band_avg - ref_avg)


        results.append({
            "band": band_label,
            "representative_temp_celsius": cold_ref_temp if lo < 0 else (lo + hi) / 2,
            "avg_kwh_100km": round(band_avg, 1),
            "reference_kwh_100km": round(ref_avg, 1) if ref_avg else None,
            "hvac_cost_kwh_100km": round(diff, 1) if diff > 0 else 0,
            "trip_count": count,
            "message": f"Heating costs you ~{round(diff, 1) if diff > 0 else 0} kWh/100km at {band_label.lower()}",
        })


    return {
        "metrics": results,
        "reference_band": reference_band_label,
        "reference_kwh_100km": round(ref_avg, 1) if ref_avg else None,
        "summary": f"HVAC cost: ~{round(results[0]['hvac_cost_kwh_100km'], 1) if results else 0} kWh/100km at {results[0]['band']}" if results else "Not enough data to compute HVAC cost.",
    }



# =============================================================================
# TASK 1: Charging Curve Integrals (v2 using charging_curves table)
# =============================================================================
@router.get("/{vehicle_id}/analytics/charging-curve-integrals-v2")
async def get_charging_curve_integrals_v2(
    vehicle_id: UUID,
    session_id: int | None = Query(None, description="Filter by specific charging session ID"),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Plot Charging Power (kW) over SoC (%) and calculate the 'wasted time'
    (time spent charging from 80% to 100%). Uses charging_curves table.
    Optionally filter by specific charging session via session_id.
    """
    await get_user_vehicle(user.id, vehicle_id, db)

    # Build base filter conditions
    base_where = [
        ChargingCurve.user_vehicle_id == vehicle_id,
        ChargingCurve.power_kw.is_not(None),
        ChargingCurve.soc_pct.is_not(None),
    ]
    if session_id is not None:
        base_where.append(ChargingCurve.session_id == session_id)

    # Curve data: Average Power kW per SoC %
    stmt_curve = (
        select(
            ChargingCurve.soc_pct.label("soc"),
            func.avg(ChargingCurve.power_kw).label("avg_power"),
            func.max(ChargingCurve.power_kw).label("max_power"),
            func.count(ChargingCurve.id).label("samples")
        )
        .where(*base_where)
        .group_by(ChargingCurve.soc_pct)
        .order_by(ChargingCurve.soc_pct)
    )
    if from_date:
        stmt_curve = stmt_curve.where(ChargingCurve.captured_at >= from_date)
    if to_date:
        stmt_curve = stmt_curve.where(ChargingCurve.captured_at <= to_date)

    result_curve = await db.execute(stmt_curve)
    curve_data = result_curve.all()

    curve = [
        {
            "soc_pct": round(float(row.soc), 1) if row.soc else 0,
            "avg_power_kw": round(float(row.avg_power), 2) if row.avg_power else 0,
            "max_power_kw": round(float(row.max_power), 2) if row.max_power else 0,
            "samples": row.samples
        }
        for row in curve_data
    ]

    # SoC bracket integrals (0-20, 20-50, 50-80, 80-100)
    stmt_brackets = (
        select(
            func.floor(ChargingCurve.soc_pct / 20).label("bracket"),
            func.count(ChargingCurve.id).label("count"),
            func.avg(ChargingCurve.power_kw).label("avg_power"),
            func.min(ChargingCurve.captured_at).label("min_time"),
            func.max(ChargingCurve.captured_at).label("max_time"),
        )
        .where(*base_where)
        .group_by("bracket")
        .order_by("bracket")
    )
    if from_date:
        stmt_brackets = stmt_brackets.where(ChargingCurve.captured_at >= from_date)
    if to_date:
        stmt_brackets = stmt_brackets.where(ChargingCurve.captured_at <= to_date)

    res_brackets = await db.execute(stmt_brackets)

    bracket_map = {row.bracket: row for row in res_brackets.all()}

    bracket_defs = [
        {"label": "0-20%", "key": 0.0, "energy_kwh": 0.0, "minutes": 0, "samples": 0},
        {"label": "20-50%", "key": 1.0, "energy_kwh": 0.0, "minutes": 0, "samples": 0},
        {"label": "50-80%", "key": 2.0, "energy_kwh": 0.0, "minutes": 0, "samples": 0},
        {"label": "80-100%", "key": 3.0, "energy_kwh": 0.0, "minutes": 0, "samples": 0},
    ]

    # Estimate: 5-min sampling interval fallback; use actual time when min/max are available
    for bd in bracket_defs:
        row = bracket_map.get(bd["key"])
        if row:
            avg_p = float(row.avg_power) if row.avg_power else 0
            count = row.count or 0
            bd["energy_kwh"] = round(avg_p * count / 12, 2)
            # Try to compute actual duration from timestamps
            if row.min_time and row.max_time and hasattr(row.min_time, 'total_seconds'):
                min_t = row.min_time
                max_t = row.max_time
                if min_t.tzinfo is not None and max_t.tzinfo is None:
                    max_t = max_t.replace(tzinfo=min_t.tzinfo)
                elif min_t.tzinfo is None and max_t.tzinfo is not None:
                    min_t = min_t.replace(tzinfo=max_t.tzinfo)
                actual_minutes = (max_t - min_t).total_seconds() / 60.0
                if actual_minutes > 0:
                    bd["minutes"] = round(actual_minutes)
                else:
                    bd["minutes"] = round(count * 5)
            else:
                bd["minutes"] = round(count * 5)
            bd["samples"] = count

    wasted_row = bracket_map.get(3.0)
    if wasted_row and hasattr(wasted_row, 'min_time') and wasted_row.min_time and wasted_row.max_time:
        min_t = wasted_row.min_time
        max_t = wasted_row.max_time
        if min_t.tzinfo is not None and max_t.tzinfo is None:
            max_t = max_t.replace(tzinfo=min_t.tzinfo)
        elif min_t.tzinfo is None and max_t.tzinfo is not None:
            min_t = min_t.replace(tzinfo=max_t.tzinfo)
        wasted_minutes = round((max_t - min_t).total_seconds() / 60.0)
    else:
        wasted_minutes = round(wasted_row.count * 5) if wasted_row and wasted_row.count else 0

    total_energy = sum(b["energy_kwh"] for b in bracket_defs)

    # Compute overall session duration from earliest→latest timestamp across all brackets.
    # This is consistent with wasted_minutes (which also uses actual timestamps), unlike
    # the sum of bracket estimates which can be much smaller than the real session span
    # (e.g. fast 0-80% brackets + slow 80-100% bracket → wasted_pct > 100%).
    overall_min_ts = None
    overall_max_ts = None
    for row in bracket_map.values():
        if hasattr(row, 'min_time') and hasattr(row, 'max_time') and row.min_time and row.max_time:
            mt = row.min_time
            mx = row.max_time
            if mt.tzinfo is not None and mx.tzinfo is None:
                mx = mx.replace(tzinfo=mt.tzinfo)
            elif mt.tzinfo is None and mx.tzinfo is not None:
                mt = mt.replace(tzinfo=mx.tzinfo)
            if overall_min_ts is None or mt < overall_min_ts:
                overall_min_ts = mt
            if overall_max_ts is None or mx > overall_max_ts:
                overall_max_ts = mx

    if overall_min_ts is not None and overall_max_ts is not None and overall_max_ts > overall_min_ts:
        total_minutes = round((overall_max_ts - overall_min_ts).total_seconds() / 60.0)
    else:
        total_minutes = sum(b["minutes"] for b in bracket_defs)

    if total_minutes == 0:
        return {
            "curve": curve,
            "brackets": bracket_defs,
            "wasted_minutes_80_100": 0,
            "total_energy_kwh": 0,
            "total_minutes": 0,
            "wasted_pct": 0,
            "message": "No charging data available for this period."
        }

    return {
        "curve": curve,
        "brackets": bracket_defs,
        "wasted_minutes_80_100": wasted_minutes,
        "total_energy_kwh": total_energy,
        "total_minutes": total_minutes,
        "wasted_pct": min(100, round(wasted_minutes / total_minutes * 100, 1)) if total_minutes > 0 else 0
    }


# =============================================================================
# TASK 3: Elevation Penalty & Regen Efficiency
# =============================================================================
_elevation_cache: OrderedDict[str, float] = OrderedDict()


async def _get_nearest_elevation(lat: float, lon: float, vehicle_id: UUID, db: AsyncSession) -> float | None:
    """Get elevation from vehicle_positions nearest to given lat/lon."""
    if lat is None or lon is None:
        return None
    cache_key = f"{lat:.4f},{lon:.4f}"
    if cache_key in _elevation_cache:
        _elevation_cache.move_to_end(cache_key)
        return _elevation_cache[cache_key]
    try:
        stmt = text(
            "SELECT elevation_m FROM vehicle_positions "
            "WHERE user_vehicle_id = :vid "
            "  AND elevation_m IS NOT NULL "
            "  AND latitude IS NOT NULL "
            "  AND longitude IS NOT NULL "
            "ORDER BY ("
            "    (latitude - :lat)^2 + (longitude - :lon)^2"
            ") ASC "
            "LIMIT 1"
        )
        res = await db.execute(stmt, {"vid": str(vehicle_id), "lat": lat, "lon": lon})
        row = res.first()
        elevation = float(row[0]) if row else None
        if elevation is not None:
            _elevation_cache[cache_key] = elevation
            if len(_elevation_cache) > 500:
                _elevation_cache.popitem(last=False)
        return elevation
    except Exception:
        return None


@router.get("/{vehicle_id}/analytics/elevation-penalty")
async def get_elevation_penalty(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    For each trip, calculate elevation gain/loss using OpenTopoData API.
    Uses asyncio.gather for concurrent fetching, with vehicle centroid fallback
    and background-job-style caching for repeated lookups.
    Uses per-vehicle calibration (uphill/downhill coefficients) with fallback defaults.
    """
    vehicle = await get_user_vehicle(user.id, vehicle_id, db)
    cal = _calibration(vehicle)

    # Fetch all trips in one query
    stmt = select(Trip).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.start_lat.is_not(None),
        Trip.start_lon.is_not(None),
        Trip.end_lat.is_not(None),
        Trip.end_lon.is_not(None),
        Trip.distance_km.is_not(None),
        Trip.distance_km > 5
    ).order_by(Trip.start_date.desc()).limit(100)

    res = await db.execute(stmt)
    trips = res.scalars().all()

    if not trips:
        return {
            "trips": [],
            "summary": {"total_trips": 0, "total_uphill_kwh": 0, "total_downhill_kwh": 0, "net_energy_kwh": 0},
            "message": "No trips with GPS data available for elevation analysis."
        }

    # Batch-fetch all elevations concurrently (single round-trip per trip via cache)
    elev_futures = [
        _get_nearest_elevation(trip.start_lat, trip.start_lon, vehicle_id, db)
        for trip in trips
    ] + [
        _get_nearest_elevation(trip.end_lat, trip.end_lon, vehicle_id, db)
        for trip in trips
    ]
    elev_results = await asyncio.gather(*elev_futures)
    n = len(trips)
    start_elevs = elev_results[:n]
    end_elevs   = elev_results[n:]

    results = []
    for i, trip in enumerate(trips):
        start_elev = start_elevs[i]
        end_elev   = end_elevs[i]

        if start_elev is None and end_elev is None:
            # No elevation data at all for this trip — skip it
            continue

        # Use 0 as fallback for missing end if start exists (and vice versa)
        start_elev = start_elev if start_elev is not None else (end_elev or 0)
        end_elev   = end_elev   if end_elev   is not None else (start_elev or 0)

        elev_change = end_elev - start_elev
        distance     = trip.distance_km or 1

        if elev_change >= 0:
            uphill_kwh    = round(elev_change * cal["uphill_kwh_per_100km_per_100m"] / 100 * distance, 3)
            downhill_kwh = 0.0
        else:
            uphill_kwh    = 0.0
            downhill_kwh = round(abs(elev_change) * cal["downhill_kwh_per_100km_per_100m"] / 100 * distance, 3)

        net_kwh = round(uphill_kwh - downhill_kwh, 3)

        results.append({
            "trip_id":           trip.id,
            "start_date":        trip.start_date.isoformat() if trip.start_date else None,
            "distance_km":       round(distance, 1),
            "start_elevation_m": start_elev,
            "end_elevation_m":   end_elev,
            "elevation_change_m": round(elev_change, 1),
            "uphill_kwh_per_100km": uphill_kwh,
            "downhill_kwh_per_100km": downhill_kwh,
            "net_energy_kwh": net_kwh,
        })

    uphill_sum   = sum(r["uphill_kwh_per_100km"]    for r in results)
    downhill_sum = sum(r["downhill_kwh_per_100km"] for r in results)

    return {
        "trips": results,
        "summary": {
            "total_trips":       len(results),
            "total_uphill_kwh":  round(uphill_sum, 2),
            "total_downhill_kwh": round(downhill_sum, 2),
            "net_energy_kwh":    round(uphill_sum - downhill_sum, 2),
        },
        "method": "vehicle_positions.elevation_m via nearest-point SQL",
    }


# =============================================================================
# TASK 4: Ideal Cruising Speed Matrix
# =============================================================================
@router.get("/{vehicle_id}/analytics/speed-temp-matrix")
async def get_speed_temp_matrix(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Speed × Temperature → avg kWh/100km matrix.

    Uses per-vehicle speed and temperature thresholds from calibration.
    """
    vehicle = await get_user_vehicle(user.id, vehicle_id, db)
    cal = _calibration(vehicle)
    city_thresh = cal["speed_city_threshold_kmh"]
    hw_thresh = cal["speed_highway_threshold_kmh"]
    cold_max = cal["temp_cold_max_celsius"]
    opt_min = cal["temp_optimal_min_celsius"]
    opt_max = cal["temp_optimal_max_celsius"]

    stmt = select(Trip).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.distance_km.is_not(None),
        Trip.distance_km > 2,
        Trip.kwh_consumed.is_not(None),
        Trip.kwh_consumed > 0,
        Trip.avg_temp_celsius.is_not(None),
        Trip.end_date.is_not(None)
    )

    res = await db.execute(stmt)
    trips = res.scalars().all()

    matrix: dict[str, dict[str, list[float]]] = {
        "city": {"cold": [], "mild": [], "optimal": [], "hot": []},
        "mixed": {"cold": [], "mild": [], "optimal": [], "hot": []},
        "highway": {"cold": [], "mild": [], "optimal": [], "hot": []},
    }

    for trip in trips:
        duration_h = (trip.end_date - trip.start_date).total_seconds() / 3600.0
        if duration_h < 0.01:
            continue
        speed = trip.distance_km / duration_h
        temp = trip.avg_temp_celsius
        eff = (trip.kwh_consumed / trip.distance_km) * 100.0

        s_cat = "mixed"
        if speed < city_thresh:
            s_cat = "city"
        elif speed > hw_thresh:
            s_cat = "highway"

        t_cat = "mild"
        if temp <= cold_max:
            t_cat = "cold"
        elif opt_min <= temp <= opt_max:
            t_cat = "optimal"
        elif temp > opt_max:
            t_cat = "hot"

        matrix[s_cat][t_cat].append(eff)

    speed_cats = ["city", "mixed", "highway"]
    temp_cats = ["cold", "mild", "optimal", "hot"]
    temp_labels = {
        "cold": f"≤{cold_max:.0f}°C",
        "mild": f"{cold_max:.0f}-{opt_min:.0f}°C",
        "optimal": f"{opt_min:.0f}-{opt_max:.0f}°C",
        "hot": f">{opt_max:.0f}°C",
    }
    speed_labels = {
        "city": f"<{city_thresh:.0f} km/h",
        "mixed": f"{city_thresh:.0f}-{hw_thresh:.0f} km/h",
        "highway": f">{hw_thresh:.0f} km/h",
    }

    grid = []
    for sc in speed_cats:
        for tc in temp_cats:
            vals = matrix[sc][tc]
            avg_val = round(sum(vals) / len(vals), 1) if vals else None
            grid.append({
                "speed_category": sc,
                "speed_label": speed_labels[sc],
                "temp_category": tc,
                "temp_label": temp_labels[tc],
                "avg_kwh_100km": avg_val,
                "trip_count": len(vals)
            })

    matrix_data = [[None for _ in temp_cats] for _ in speed_cats]
    count_data = [[0 for _ in temp_cats] for _ in speed_cats]
    for item in grid:
        si = speed_cats.index(item["speed_category"])
        ti = temp_cats.index(item["temp_category"])
        matrix_data[si][ti] = item["avg_kwh_100km"]
        count_data[si][ti] = item["trip_count"]

    return {
        "grid": grid,
        "speed_categories": [speed_labels[sc] for sc in speed_cats],
        "temp_categories": [temp_labels[tc] for tc in temp_cats],
        "matrix_values": matrix_data,
        "trip_counts": count_data,
    }


# =============================================================================
# TASK 6: Vampire Drain Cost Analysis
# =============================================================================
@router.get("/{vehicle_id}/analytics/vampire-drain")
async def get_vampire_drain(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Calculate average SoC loss per hour while parked, translate to kWh and EUR."""
    await get_user_vehicle(user.id, vehicle_id, db)

    from app.models.vehicle import UserVehicle
    v_res = await db.execute(select(UserVehicle).where(UserVehicle.id == vehicle_id))
    veh = v_res.scalar_one_or_none()
    battery_kwh = 50.0  # Safe default for EVs if vehicle has no stored capacity
    if veh:
        cap = getattr(veh, "battery_capacity_kwh", None)
        if cap and cap > 0:
            battery_kwh = float(cap)

    country_code = "LT"
    if veh:
        cc = getattr(veh, "country_code", None)
        if cc:
            country_code = str(cc)

    from app.models.fuel_price import CountryEconomics
    elec_price = 0.0
    eco_res = await db.execute(
        select(CountryEconomics)
        .where(CountryEconomics.country_code == country_code)
        .order_by(CountryEconomics.date.desc())
        .limit(1)
    )
    eco = eco_res.scalar_one_or_none()
    if eco and eco.electricity_price_kwh_eur:
        elec_price = float(eco.electricity_price_kwh_eur)

    # Analyze vehicle_states for PARKED sessions to calculate SoC drain rate
    stmt_vs = (
        select(VehicleState)
        .where(VehicleState.user_vehicle_id == vehicle_id)
        .order_by(VehicleState.first_date)
        .limit(500)
    )
    vs_res = await db.execute(stmt_vs)
    vs_records = vs_res.scalars().all()

    # Also get charging states for battery_pct
    stmt_cs = (
        select(ChargingState)
        .where(ChargingState.user_vehicle_id == vehicle_id)
        .where(ChargingState.battery_pct.is_not(None))
        .order_by(ChargingState.first_date)
        .limit(500)
    )
    cs_res = await db.execute(stmt_cs)
    cs_records = cs_res.scalars().all()

    # Build a time-series: (timestamp, battery_pct, state) from charging_states
    soc_timeline: list[tuple[datetime, int, str]] = []
    for rec in cs_records:
        if rec.first_date and rec.battery_pct is not None:
            soc_timeline.append((rec.first_date, int(rec.battery_pct), rec.state or ""))

    # Calculate drain from SoC timeline: CONNECT_CABLE -> CONNECT_CABLE only
    # Filter to realistic vampire drain: < 0.15%/hr, dsoc < 15%, dt 1-72h
    soc_drain_rates: list[float] = []
    for i in range(1, len(soc_timeline)):
        t0, soc0, s0 = soc_timeline[i - 1]
        t1, soc1, s1 = soc_timeline[i]
        dt_h = (t1 - t0).total_seconds() / 3600.0
        dsoc = float(soc0) - float(soc1)
        # Only CONNECT_CABLE->CONNECT_CABLE transitions (plugged in, not driving)
        # and realistic drain rates (< 0.15%/hr = ~3.6%/day max for real vampire drain)
        if s0 == "CONNECT_CABLE" and s1 == "CONNECT_CABLE":
            cfg = VAMPIRE_DRAIN_DEFAULTS
            if cfg["min_parked_hours"] < dt_h < cfg["max_parked_hours"] and 0 < dsoc < cfg["max_dsoc_pct"]:
                rate = dsoc / dt_h
                if rate < cfg["max_drain_rate_pct"]:
                    soc_drain_rates.append(rate)

    avg_pct_per_hour = 0.0
    if soc_drain_rates:
        # Use median of realistic rates to avoid skew from long parked sessions
        sorted_rates = sorted(soc_drain_rates)
        mid = len(sorted_rates) // 2
        median_rate = sorted_rates[mid] if len(sorted_rates) % 2 == 1 else (
            sorted_rates[mid - 1] + sorted_rates[mid]
        ) / 2
        # Use median rather than mean to avoid skew from long-parked outliers
        avg_pct_per_hour = median_rate

    if avg_pct_per_hour <= 0:
        avg_pct_per_hour = 0.0  # No assumed vampire drain when no data (HC-026/031)

    drain_pct_per_day = avg_pct_per_hour * 24
    drain_kwh_per_day = battery_kwh * drain_pct_per_day / 100
    drain_kwh_per_week = drain_kwh_per_day * 7
    drain_kwh_per_month = drain_kwh_per_day * 30

    return {
        "avg_drain_pct_per_hour": round(avg_pct_per_hour, 4),
        "avg_drain_pct_per_day": round(drain_pct_per_day, 2),
        "drain_kwh_per_day": round(drain_kwh_per_day, 3),
        "drain_kwh_per_week": round(drain_kwh_per_week, 3),
        "drain_kwh_per_month": round(drain_kwh_per_month, 3),
        "electricity_price_eur_kwh": round(elec_price, 4),
        "cost_per_day_eur": round(drain_kwh_per_day * elec_price, 4),
        "cost_per_week_eur": round(drain_kwh_per_week * elec_price, 3),
        "cost_per_month_eur": round(drain_kwh_per_month * elec_price, 2),
        "battery_capacity_kwh": battery_kwh,
    }


# =============================================================================
# TASK 6b: Charging Economics — Base Grid Cost vs DC Provider Markup
# =============================================================================
class ChargingEconomicsSession(BaseModel):
    session_id: int
    session_start: str | None
    charging_type: str | None
    energy_kwh: float | None
    base_grid_cost_eur: float | None   # energy_kwh × electricity_price (home equivalent)
    paid_eur: float | None              # what user actually paid
    markup_eur: float | None            # DC provider extra charge
    provider_name: str | None

class ChargingEconomicsResponse(BaseModel):
    sessions: list[ChargingEconomicsSession]
    total_energy_kwh: float
    total_base_grid_cost_eur: float
    total_paid_eur: float
    total_markup_eur: float
    electricity_price_eur_kwh: float
    country_code: str


@router.get("/{vehicle_id}/analytics/charging-economics", response_model=ChargingEconomicsResponse)
async def get_charging_economics(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    from_date: date | None = None,
    to_date: date | None = None,
):
    """
    Break down each charging session into:
    - Base grid cost  : energy_kwh × country electricity price  (what it would cost at home)
    - Paid            : actual_cost_eur or base_cost_eur         (what was actually charged)
    - Markup          : paid − base grid cost                    (DC provider's extra fee)

    Uses CountryEconomics.electricity_price_kwh_eur as the home-equivalent price.
    """
    vehicle = await get_user_vehicle(user.id, vehicle_id, db)
    country_code = str(vehicle.country_code) if vehicle.country_code else "LT"

    from app.models.fuel_price import CountryEconomics

    # Fetch electricity price for the vehicle's country
    elec_price = 0.25  # sensible EUR/kWh default
    eco_res = await db.execute(
        select(CountryEconomics)
        .where(CountryEconomics.country_code == country_code)
        .order_by(CountryEconomics.date.desc())
        .limit(1)
    )
    eco = eco_res.scalar_one_or_none()
    if eco and eco.electricity_price_kwh_eur:
        elec_price = float(eco.electricity_price_kwh_eur)

    # Fetch charging sessions
    stmt = (
        select(ChargingSession)
        .where(ChargingSession.user_vehicle_id == vehicle_id)
        .where(ChargingSession.energy_kwh.is_not(None))
    )
    if from_date:
        stmt = stmt.where(ChargingSession.session_start >= from_date)
    if to_date:
        stmt = stmt.where(ChargingSession.session_start <= to_date)

    stmt = stmt.order_by(ChargingSession.session_start.desc())
    res = await db.execute(stmt)
    sessions = res.scalars().all()

    rows: list[ChargingEconomicsSession] = []
    total_energy = 0.0
    total_base = 0.0
    total_paid = 0.0

    for s in sessions:
        energy = s.energy_kwh or 0.0
        paid = float(s.actual_cost_eur if s.actual_cost_eur is not None else (s.base_cost_eur or 0.0))
        base_cost = energy * elec_price
        markup = paid - base_cost

        rows.append(ChargingEconomicsSession(
            session_id=s.id,
            session_start=s.session_start.isoformat() if s.session_start else None,
            charging_type=s.charging_type,
            energy_kwh=round(energy, 2),
            base_grid_cost_eur=round(base_cost, 3),
            paid_eur=round(paid, 2),
            markup_eur=round(markup, 2),
            provider_name=s.provider_name,
        ))
        total_energy += energy
        total_base += base_cost
        total_paid += paid

    return ChargingEconomicsResponse(
        sessions=rows,
        total_energy_kwh=round(total_energy, 2),
        total_base_grid_cost_eur=round(total_base, 2),
        total_paid_eur=round(total_paid, 2),
        total_markup_eur=round(total_paid - total_base, 2),
        electricity_price_eur_kwh=round(elec_price, 4),
        country_code=country_code,
    )


# =============================================================================
# TASK 7: Dynamic ICE-Equivalent TCO
# =============================================================================
@router.get("/{vehicle_id}/analytics/ice-tco")
async def get_ice_tco(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Compare per-trip EV cost vs ICE fuel cost using per-vehicle ice_l_per_100km calibration."""
    vehicle = await get_user_vehicle(user.id, vehicle_id, db)
    cal = _calibration(vehicle)
    ice_l_per_100km = cal["ice_l_per_100km"]

    country_code = vehicle.country_code or "LT"

    from app.models.fuel_price import FuelPrice, CountryEconomics

    elec_price = 0.0
    eco_res = await db.execute(
        select(CountryEconomics)
        .where(CountryEconomics.country_code == country_code)
        .order_by(CountryEconomics.date.desc())
        .limit(1)
    )
    eco = eco_res.scalar_one_or_none()
    if eco and eco.electricity_price_kwh_eur:
        elec_price = float(eco.electricity_price_kwh_eur)

    petrol_price = 1.65
    fuel_res = await db.execute(
        select(FuelPrice)
        .where(FuelPrice.country_code == country_code)
        .where(FuelPrice.fuel_type == "Euro95")
        .order_by(FuelPrice.week_date.desc())
        .limit(1)
    )
    fuel = fuel_res.scalar_one_or_none()
    if fuel and fuel.price_eur_liter:
        petrol_price = float(fuel.price_eur_liter)

    stmt = select(Trip).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.distance_km.is_not(None),
        Trip.distance_km > 1,
        Trip.kwh_consumed.is_not(None),
        Trip.start_date.is_not(None)
    ).order_by(Trip.start_date).limit(200)

    res = await db.execute(stmt)
    trips = res.scalars().all()

    results = []
    cum_ev = 0.0
    cum_ice = 0.0

    for trip in trips:
        distance = trip.distance_km or 0
        kwh = trip.kwh_consumed or 0

        ev_cost = kwh * elec_price
        ice_cost = (distance * ice_l_per_100km / 100) * petrol_price
        savings = ice_cost - ev_cost

        cum_ev += ev_cost
        cum_ice += ice_cost

        results.append({
            "trip_id": trip.id,
            "start_date": trip.start_date.isoformat() if trip.start_date else None,
            "distance_km": round(distance, 1),
            "kwh_consumed": round(kwh, 2),
            "ev_cost_eur": round(ev_cost, 3),
            "ice_cost_eur": round(ice_cost, 3),
            "savings_eur": round(savings, 3),
            "cumulative_ev_cost_eur": round(cum_ev, 2),
            "cumulative_ice_cost_eur": round(cum_ice, 2),
        })

    return {
        "trips": results,
        "summary": {
            "total_trips": len(results),
            "total_distance_km": round(sum(t.distance_km or 0 for t in trips), 1),
            "total_ev_cost_eur": round(cum_ev, 2),
            "total_ice_cost_eur": round(cum_ice, 2),
            "total_savings_eur": round(cum_ice - cum_ev, 2),
            "electricity_price_eur_kwh": round(elec_price, 4),
            "petrol_price_eur_l": round(petrol_price, 3),
            "ice_l_per_100km": round(ice_l_per_100km, 1),
        }
    }


# =============================================================================
# TASK 8: Route-Specific Efficiency Profiling
# =============================================================================
async def _reverse_geocode(lat: float, lon: float, db: AsyncSession) -> str:
    """Look up a location name from geocoded_locations cache, or return a coords fallback."""
    from decimal import Decimal
    from sqlalchemy import text
    # Round to 5 decimal places for consistent cache key
    lat_r = Decimal(str(lat)).quantize(Decimal("1.00000"))
    lon_r = Decimal(str(lon)).quantize(Decimal("1.00000"))
    stmt = text(
        "SELECT display_name FROM geocoded_locations WHERE latitude = :lat AND longitude = :lon LIMIT 1"
    )
    row = (await db.execute(stmt, {"lat": lat_r, "lon": lon_r})).fetchone()
    if row and row[0]:
        return row[0]
    return f"{lat:.5f}, {lon:.5f}"


def _geohash(lat: float, lon: float, precision: int = 4) -> str:
    """Simple geohash: rounded lat/lon."""
    return f"{round(lat, precision)}_{round(lon, precision)}"


@router.get("/{vehicle_id}/analytics/route-efficiency")
async def get_route_efficiency(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cluster trips by start/end geohash; compute historical efficiency per route."""
    await get_user_vehicle(user.id, vehicle_id, db)

    stmt = select(Trip).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.start_lat.is_not(None),
        Trip.start_lon.is_not(None),
        Trip.end_lat.is_not(None),
        Trip.end_lon.is_not(None),
        Trip.distance_km.is_not(None),
        Trip.distance_km > 2,
        Trip.kwh_consumed.is_not(None),
        Trip.kwh_consumed > 0
    ).order_by(Trip.start_date.desc()).limit(200)

    res = await db.execute(stmt)
    trips = res.scalars().all()

    # Pre-geocode all unique start/end coordinates in one DB round-trip
    from decimal import Decimal as DDec
    unique_coords = list({
        (DDec(str(round(trip.start_lat, 5))).quantize(DDec("1.00000")),
         DDec(str(round(trip.start_lon, 5))).quantize(DDec("1.00000")))
        for trip in trips
    } | {
        (DDec(str(round(trip.end_lat, 5))).quantize(DDec("1.00000")),
         DDec(str(round(trip.end_lon, 5))).quantize(DDec("1.00000")))
        for trip in trips
    })
    coord_to_name: dict[tuple[float, float], str] = {}
    if unique_coords:
        # Find nearest geocoded location for each trip coordinate (within ~100m / 0.001°)
        for lat, lon in unique_coords:
            nearest = await db.execute(text(
                """SELECT display_name FROM geocoded_locations
                   WHERE ABS(latitude - :lat) < 0.002 AND ABS(longitude - :lon) < 0.002
                   ORDER BY (ABS(latitude - :lat) + ABS(longitude - :lon)) ASC LIMIT 1"""
            ), {"lat": float(lat), "lon": float(lon)})
            row = nearest.fetchone()
            coord_to_name[(round(float(lat), 5), round(float(lon), 5))] = (
                row[0] if row and row[0] else f"{float(lat):.5f}, {float(lon):.5f}"
            )

    route_groups: dict[str, dict] = {}

    for trip in trips:
        start_gh = _geohash(trip.start_lat, trip.start_lon)
        end_gh = _geohash(trip.end_lat, trip.end_lon)
        route_key = f"{start_gh}->{end_gh}"
        start_key = (round(trip.start_lat, 5), round(trip.start_lon, 5))
        end_key = (round(trip.end_lat, 5), round(trip.end_lon, 5))
        start_name = coord_to_name.get(start_key, f"{trip.start_lat:.5f}, {trip.start_lon:.5f}")
        end_name = coord_to_name.get(end_key, f"{trip.end_lat:.5f}, {trip.end_lon:.5f}")

        if route_key not in route_groups:
            route_groups[route_key] = {
                "start_name": start_name,
                "end_name": end_name,
                "efficiencies": [],
                "temps": [],
                "distances": [],
            }

        eff = (trip.kwh_consumed / trip.distance_km) * 100.0
        route_groups[route_key]["efficiencies"].append(eff)
        if trip.avg_temp_celsius:
            route_groups[route_key]["temps"].append(trip.avg_temp_celsius)
        route_groups[route_key]["distances"].append(trip.distance_km)

    results = []
    for route_key, data in route_groups.items():
        effs = data["efficiencies"]
        avg_eff = round(sum(effs) / len(effs), 1) if effs else 0
        avg_temp = round(sum(data["temps"]) / len(data["temps"]), 1) if data["temps"] else None
        total_dist = sum(data["distances"])
        score = max(0, 100 - (avg_eff - 12) * 10) if avg_eff > 0 else 50

        results.append({
            "route_key": f"{data['start_name']} → {data['end_name']}",
            "start_location": data["start_name"],
            "end_location": data["end_name"],
            "trip_count": len(effs),
            "avg_kwh_100km": avg_eff,
            "min_kwh_100km": round(min(effs), 1) if effs else 0,
            "max_kwh_100km": round(max(effs), 1) if effs else 0,
            "avg_temp_celsius": avg_temp,
            "total_distance_km": round(total_dist, 1),
            "efficiency_score": round(score, 1),
        })

    results.sort(key=lambda x: x["trip_count"], reverse=True)

    return {
        "routes": results[:50],
        "total_routes": len(results),
    }


# =============================================================================
# TASK 9: Predictive Arrival SoC
# =============================================================================
@router.get("/{vehicle_id}/analytics/predictive-soc")
async def get_predictive_soc(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Predict arrival SoC using historical consumption data and current conditions."""
    await get_user_vehicle(user.id, vehicle_id, db)

    from app.models.vehicle import UserVehicle
    v_res = await db.execute(select(UserVehicle).where(UserVehicle.id == vehicle_id))
    veh = v_res.scalar_one_or_none()
    battery_kwh = 50.0  # Safe default for EVs if vehicle has no stored capacity
    charge_res = await db.execute(
        select(ChargingState)
        .where(ChargingState.user_vehicle_id == vehicle_id)
        .order_by(ChargingState.first_date.desc())
        .limit(1)
    )
    charge = charge_res.scalar_one_or_none()
    current_soc = float(charge.battery_pct) if charge and charge.battery_pct else 50.0
    if veh:
        cap = getattr(veh, "battery_capacity_kwh", None)
        if cap and cap > 0:
            battery_kwh = float(cap)

    vehicle = await get_user_vehicle(user.id, vehicle_id, db)
    cal = _calibration(vehicle)
    cold_max = cal["temp_cold_max_celsius"]
    opt_min = cal["temp_optimal_min_celsius"]
    opt_max = cal["temp_optimal_max_celsius"]

    pos_res = await db.execute(
        select(VehiclePosition)
        .where(VehiclePosition.user_vehicle_id == vehicle_id)
        .order_by(VehiclePosition.captured_at.desc())
        .limit(1)
    )
    pos = pos_res.scalar_one_or_none()
    current_temp = float(pos.outside_temp_celsius) if pos and pos.outside_temp_celsius else 10.0

    # Fetch trips early — needed for HC-028 range fallback calculation
    trips_stmt = select(Trip).where(
        Trip.user_vehicle_id == vehicle_id,
        Trip.distance_km.is_not(None),
        Trip.distance_km > 5,
        Trip.kwh_consumed.is_not(None),
        Trip.kwh_consumed > 0,
        Trip.avg_temp_celsius.is_not(None)
    ).order_by(Trip.start_date.desc()).limit(100)
    trips_res = await db.execute(trips_stmt)
    trips = trips_res.scalars().all()

    remaining_range_km = 0.0
    if charge and charge.remaining_range_m:
        remaining_range_km = charge.remaining_range_m / 1000.0
    else:
        # HC-028: derive fallback range from battery_kwh × avg trip efficiency (km/kWh)
        if trips and len(trips) > 0:
            all_effs_km_per_kwh = [100.0 / max((t.kwh_consumed / t.distance_km), 0.1) for t in trips if t.distance_km and t.distance_km > 0]
            avg_efficiency = sum(all_effs_km_per_kwh) / len(all_effs_km_per_kwh) if all_effs_km_per_kwh else 8.0
        else:
            avg_efficiency = 8.0  # default km/kWh fallback
        remaining_range_km = (current_soc / 100) * battery_kwh * avg_efficiency

    # HC-029 FIX: target_distance_km should be the *planned* trip distance, not remaining_range_km.
    # remaining_range_km = how far the car can still drive (not how far the planned trip is).
    # Using remaining_range_km as target_distance causes arrival SOC to be calculated for
    # driving the full remaining range rather than the actual planned trip, producing
    # wrong (often very low) arrival SOC for short trips.
    # Use the average of recent trip distances as a realistic estimate of planned trip length.
    if trips and len(trips) > 0:
        recent_distances = [t.distance_km for t in trips[:10] if t.distance_km and t.distance_km > 0]
        avg_trip_distance = sum(recent_distances) / len(recent_distances) if recent_distances else (cal["charger_power_kw"] * 9.09)
    else:
        avg_trip_distance = cal["charger_power_kw"] * 9.09
    target_distance_km = avg_trip_distance

    if not trips:
        return {
            "current_soc_pct": round(current_soc, 1),
            "estimated_range_km": round(remaining_range_km, 1),
            "predicted_arrival_soc_pct": round(current_soc, 1),
            "confidence_pct": 30,
            "message": "Not enough trip data for prediction.",
            "consumption_by_temp": {},
            "consumption_data": []
        }

    temps_bucket = {"cold": [], "mild": [], "optimal": [], "hot": []}
    for trip in trips:
        temp = trip.avg_temp_celsius
        eff = (trip.kwh_consumed / trip.distance_km) * 100.0 if trip.distance_km else 0
        if temp < cold_max:
            temps_bucket["cold"].append(eff)
        elif cold_max <= temp < opt_min:
            temps_bucket["mild"].append(eff)
        elif opt_min <= temp <= opt_max:
            temps_bucket["optimal"].append(eff)
        else:
            temps_bucket["hot"].append(eff)

    if current_temp < cold_max:
        temp_cat = "cold"
    elif cold_max <= current_temp < opt_min:
        temp_cat = "mild"
    elif opt_min <= current_temp <= opt_max:
        temp_cat = "optimal"
    else:
        temp_cat = "hot"

    cat_effs = temps_bucket[temp_cat]
    if not cat_effs:
        all_effs = [e for bucket in temps_bucket.values() for e in bucket]
        baseline_consumption = sum(all_effs) / len(all_effs) if all_effs else 18.0
    else:
        baseline_consumption = sum(cat_effs) / len(cat_effs)

    energy_needed_kwh = (baseline_consumption / 100) * target_distance_km
    current_energy_kwh = (current_soc / 100) * battery_kwh
    remaining_energy_kwh = current_energy_kwh - energy_needed_kwh
    arrival_soc = (remaining_energy_kwh / battery_kwh) * 100.0

    cat_trips = len(cat_effs)
    confidence = min(95, 30 + cat_trips * 5)
    arrival_soc = max(0.0, arrival_soc)  # Clamp floor only; upper bound enforced by caller

    return {
        "current_soc_pct": round(current_soc, 1),
        "current_temp_celsius": round(current_temp, 1),
        "target_distance_km": round(target_distance_km, 1),
        "estimated_range_km": round(remaining_range_km, 1),
        "predicted_arrival_soc_pct": round(arrival_soc, 1),
        "confidence_pct": round(confidence, 1),
        "baseline_consumption_kwh_100km": round(baseline_consumption, 1),
        "energy_needed_kwh": round(energy_needed_kwh, 2),
        "message": f"At {current_temp}°C with {baseline_consumption:.1f} kWh/100km, you'll arrive with ~{round(arrival_soc)}% battery.",
        "consumption_by_temp": {
            cat: round(sum(v) / len(v), 1) if v else None
            for cat, v in temps_bucket.items()
        }
    }
