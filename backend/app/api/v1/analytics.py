from datetime import datetime, date, timedelta
from uuid import UUID

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

@router.get("/{vehicle_id}/analytics/efficiency")
async def get_efficiency_curve(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns average consumption mapped by temperature to visualize the 'Winter Penalty'."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(
            func.round(Trip.avg_temp_celsius).label("temp"),
            func.avg(Trip.kwh_consumed / Trip.distance_km * 100).label("avg_consumption_kwh_100km"),
            func.count(Trip.id).label("trip_count")
        )
        .where(
            Trip.user_vehicle_id == vehicle_id,
            Trip.distance_km > 0,
            Trip.kwh_consumed > 0,
            Trip.avg_temp_celsius.isnot(None)
        )
        .group_by("temp")
        .order_by("temp")
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

@router.get("/{vehicle_id}/analytics/charging-costs")
async def get_charging_costs(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns cost savings: Base NordPool vs Actual Paid (Public Chargers)."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(
            func.sum(ChargingSession.base_cost_eur).label("total_base_cost"),
            func.sum(ChargingSession.actual_cost_eur).label("total_actual_cost"),
            func.sum(ChargingSession.energy_kwh).label("total_kwh"),
            func.count(ChargingSession.id).label("session_count")
        )
        .where(
            ChargingSession.user_vehicle_id == vehicle_id,
            ChargingSession.energy_kwh > 0
        )
    )
    
    result = await db.execute(stmt)
    row = result.first()
    
    if not row:
        return {"total_base_cost_eur": 0, "total_actual_cost_eur": 0, "total_kwh_added": 0, "markup_paid_eur": 0}
        
    base = float(row.total_base_cost or 0)
    actual = float(row.total_actual_cost or 0)
    
    return {
        "total_sessions": row.session_count or 0,
        "total_kwh_added": round(float(row.total_kwh or 0), 2),
        "total_base_cost_eur": round(base, 2),
        "total_actual_cost_eur": round(actual, 2),
        "markup_paid_eur": round(actual - base, 2) if actual > 0 else 0
    }

@router.get("/{vehicle_id}/analytics/charging-sessions")
async def get_charging_sessions(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 20
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
    limit: int = 100
):
    """Return the latest battery health metrics including 12V and cell voltages."""
    await get_user_vehicle(user.id, vehicle_id, db)
    
    stmt = (
        select(BatteryHealth)
        .where(BatteryHealth.user_vehicle_id == vehicle_id)
        .order_by(BatteryHealth.captured_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    return [
        {
            "captured_at": r.captured_at.isoformat(),
            "twelve_v_battery_voltage": r.twelve_v_battery_voltage,
            "twelve_v_battery_soc": r.twelve_v_battery_soc,
            "twelve_v_battery_soh": r.twelve_v_battery_soh,
            "hv_battery_voltage": r.hv_battery_voltage,
            "hv_battery_current": r.hv_battery_current,
            "hv_battery_temperature": r.hv_battery_temperature,
            "hv_battery_soh": r.hv_battery_soh,
            "hv_battery_degradation_pct": r.hv_battery_degradation_pct,
            "cell_voltage_min": r.cell_voltage_min,
            "cell_voltage_max": r.cell_voltage_max,
            "cell_voltage_avg": r.cell_voltage_avg,
            "cell_temperature_avg": r.cell_temperature_avg,
            "imbalance_mv": r.imbalance_mv,
        }
        for r in records
    ]

@router.get("/{vehicle_id}/analytics/power-usage")
async def get_power_usage(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 100
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
    limit: int = 100
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
    limit: int = 500
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
    vs_result = await db.execute(__import__("sqlalchemy").text(vs_sql), {"vid": str(vehicle_id)})
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
    cs_result = await db.execute(__import__("sqlalchemy").text(cs_sql), {"vid": str(vehicle_id)})
    charging_seconds = float(cs_result.scalar() or 0)

    return {
        "parked_seconds":   round(state_seconds.get("PARKED", 0)),
        "driving_seconds":  round(state_seconds.get("DRIVING", 0)),
        "charging_seconds": round(charging_seconds),
        "ignition_seconds": round(state_seconds.get("IGNITION_ON", 0)),
        "offline_seconds":  round(state_seconds.get("OFFLINE", 0)),
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
        from app.models.telemetry import EnergyPrice
        price_res = await db.execute(select(EnergyPrice).where(EnergyPrice.country_code == country_code))
        energy_price = price_res.scalar_one_or_none()

        if not energy_price and country_code != "LT":
            price_res_fallback = await db.execute(select(EnergyPrice).where(EnergyPrice.country_code == "LT"))
            energy_price = price_res_fallback.scalar_one_or_none()

    elec_price = getattr(energy_price, "electricity_price_eur_kwh", 0.25)
    petrol_price = getattr(energy_price, "petrol_price_eur_l", 1.65)

    # 4. Actual Charging Prices
    actual_price_sql = text("""
        SELECT SUM(actual_cost_eur) / SUM(energy_kwh) as avg_price 
        FROM charging_sessions 
        WHERE user_vehicle_id = :vid AND actual_cost_eur IS NOT NULL AND energy_kwh > 0
    """)
    actual_price_res = await db.execute(actual_price_sql, {"vid": str(vehicle_id)})
    actual_price_row = actual_price_res.fetchone()
    actual_avg_price = float(actual_price_row[0]) if actual_price_row and actual_price_row[0] else None

    # Build response with dynamic data and safe fallbacks
    return {
        "efficiency": {
            "avg_kwh_100km": round(float(trip_row[6]), 1) if trip_row and trip_row[6] else 18.5,
            "cold_penalty_pct": round(((float(trip_row[4]) - float(trip_row[5])) / float(trip_row[5]) * 100) if trip_row and trip_row[4] and trip_row[5] and float(trip_row[5]) != 0 else 15, 1),
            "cold_eff_kwh_100km": round(float(trip_row[4]), 1) if trip_row and trip_row[4] else 22.5,
            "warm_eff_kwh_100km": round(float(trip_row[5]), 1) if trip_row and trip_row[5] else 16.2,
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
