import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import get_current_active_user
from app.config import settings
from app.database import get_db
from app.models.geofence import Geofence  # noqa: F401
from app.models.telemetry import (
    DriveConsumption,
    DriveRangeEstimatedFull,
    BatteryTemperature,
    ChargingPower,
    OutsideTemperature,
    AirConditioningState,
    ChargingSession,
    ChargingState,
    ConnectionState,
    Drive,
    DriveLevel,
    DriveRange,
    MaintenanceReport,
    OdometerReading,
    Trip,
    VehiclePosition,
    VehicleState,
)
from app.models.user import User
from app.models.vehicle import ConnectorSession, UserVehicle
from app.schemas.telemetry import (
    VisitedLocationItem,
    AirConditioningItem,
    BatteryHistoryItem,
    ChargingSessionItem,
    ChargingStateItem,
    ConnectionStateItem,
    EfficiencyPoint,
    MaintenanceItem,
    OdometerItem,
    PositionItem,
    RangeAt100Point,
    RangeHistoryItem,
    StateBandItem,
    StatisticsPeriod,
    TripItem,
    TripAnalyticsItem,
    VehicleStateItem,
    WLTPResponse,
)
from app.schemas.vehicle import VehicleCreate, VehicleResponse, VehicleStatusResponse, VehicleUpdate, VehicleReauth
from app.services.crypto import decrypt_field, encrypt_field, hash_field
from app.services.events import publish_vehicle_deleted, publish_vehicle_linked, publish_vehicle_refresh, publish_vehicle_updated
from app.services.skoda_auth import SkodaAuthClient

logger = logging.getLogger(__name__)

router = APIRouter()


def _stmt_to_sql(stmt) -> str | None:
    """Compile SQLAlchemy statement to string for debug logging. Returns None on error."""
    try:
        compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False})
        return str(compiled)
    except Exception:
        return None


def _log_statistics_query(
    route: str,
    vehicle_id: uuid.UUID,
    *,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int | None = None,
    result_count: int | None = None,
    extra: dict | None = None,
    sql: str | None = None,
) -> None:
    """Log query params and result count only when STATISTICS_QUERY_DEBUG=true. Optionally include compiled SQL."""
    if not getattr(settings, "statistics_query_debug", False):
        return
    payload = {
        "route": route,
        "vehicle_id": str(vehicle_id),
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "limit": limit,
        "result_count": result_count,
    }
    if extra:
        payload["extra"] = extra
    if sql:
        payload["sql"] = sql[:2000] + "..." if len(sql) > 2000 else sql
    logger.info("[STATISTICS_QUERY_DEBUG] %s", json.dumps(payload, default=str))


async def _get_user_vehicle(
    vehicle_id: uuid.UUID, user: User, db: AsyncSession
) -> UserVehicle:
    result = await db.execute(
        select(UserVehicle)
        .where(UserVehicle.id == vehicle_id, UserVehicle.user_id == user.id)
        .options(selectinload(UserVehicle.connector_session))
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


def _vehicle_to_response(v: UserVehicle) -> VehicleResponse:
    cs = v.connector_session
    return VehicleResponse(
        id=v.id,
        display_name=v.display_name,
        manufacturer=v.manufacturer,
        model=v.model,
        model_year=v.model_year,
        collection_enabled=v.collection_enabled,
        active_interval_seconds=v.active_interval_seconds,
        parked_interval_seconds=v.parked_interval_seconds,
        wltp_range_km=v.wltp_range_km,
        country_code=v.country_code,
        image_url=v.image_url,
        body_type=v.body_type,
        trim_level=v.trim_level,
        exterior_colour=v.exterior_colour,
        battery_capacity_kwh=v.battery_capacity_kwh,
        max_charging_power_kw=v.max_charging_power_kw,
        engine_power_kw=v.engine_power_kw,
        software_version=v.software_version,
        capabilities=v.capabilities,
        specifications=v.specifications,
        warning_lights=v.warning_lights,
        connector_status=cs.status if cs else None,
        last_fetch_at=cs.last_fetch_at if cs else None,
        created_at=v.created_at,
    )


@router.get("", response_model=list[VehicleResponse], include_in_schema=False)
@router.get("/", response_model=list[VehicleResponse])
async def list_vehicles(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserVehicle)
        .where(UserVehicle.user_id == user.id)
        .options(selectinload(UserVehicle.connector_session))
    )
    return [_vehicle_to_response(v) for v in result.scalars().all()]


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    body: VehicleCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vin_hash = hash_field(body.vin)
    existing = await db.execute(
        select(UserVehicle).where(UserVehicle.vin_hash == vin_hash)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vehicle with this VIN already registered",
        )

    connector_config = json.dumps({
        "username": body.skoda_username,
        "password": body.skoda_password,
        "spin": body.skoda_spin,
    })

    vehicle = UserVehicle(
        user_id=user.id,
        vin_hash=vin_hash,
        vin_encrypted=encrypt_field(body.vin),
        display_name=body.display_name,
        connector_config_encrypted=encrypt_field(connector_config),
        collection_enabled=True,
        active_interval_seconds=body.active_interval_seconds,
        parked_interval_seconds=body.parked_interval_seconds,
        wltp_range_km=body.wltp_range_km,
        country_code=body.country_code or "LT",
    )
    db.add(vehicle)
    await db.flush()

    auth = SkodaAuthClient()
    try:
        tokens = await auth.login(body.skoda_username, body.skoda_password)
    except Exception as e:
        logger.warning("Skoda auth failed, rolling back vehicle creation", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await auth.close()

    access_token = tokens.get("accessToken") or tokens.get("access_token", "")
    refresh_token = tokens.get("refreshToken") or tokens.get("refresh_token", "")
    expires_in = tokens.get("expiresIn") or tokens.get("expires_in", 3600)
    token_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
    logger.info("Skoda auth succeeded for vehicle %s", vehicle.id)

    cs = ConnectorSession(
        user_vehicle_id=vehicle.id,
        connector_type="skoda",
        status="active",
        access_token_encrypted=encrypt_field(access_token),
        refresh_token_encrypted=encrypt_field(refresh_token),
        token_expires_at=token_expires_at,
    )
    db.add(cs)
    await db.commit()

    # Attach session to vehicle to avoid lazy-load MissingGreenlet crash
    vehicle.connector_session = cs

    await publish_vehicle_linked(
        str(vehicle.id), vehicle.parked_interval_seconds
    )

    return _vehicle_to_response(vehicle)


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    v = await _get_user_vehicle(vehicle_id, user, db)
    return _vehicle_to_response(v)


@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vehicle, field, value)
    await db.commit()
    await db.refresh(vehicle)

    await publish_vehicle_updated(
        str(vehicle.id),
        vehicle.parked_interval_seconds,
        vehicle.collection_enabled,
    )
    return _vehicle_to_response(vehicle)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    vid = str(vehicle.id)
    await db.delete(vehicle)
    await db.commit()
    await publish_vehicle_deleted(vid)


@router.post("/{vehicle_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_vehicle(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a one-time out-of-band full telemetry fetch for the vehicle,
    regardless of the current Smart Polling state or interval."""
    await _get_user_vehicle(vehicle_id, user, db)
    await publish_vehicle_refresh(str(vehicle_id))
    return {"status": "queued", "message": "Manual refresh triggered successfully"}


@router.post("/{vehicle_id}/reauthenticate", status_code=status.HTTP_200_OK)
async def reauthenticate_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleReauth,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    
    config_str = decrypt_field(vehicle.connector_config_encrypted)
    config = json.loads(config_str)
    
    username = body.skoda_username or config.get("username")
    password = body.skoda_password or config.get("password")
    spin = body.skoda_spin or config.get("spin")
    
    auth = SkodaAuthClient()
    try:
        tokens = await auth.login(username, password)
    except Exception as e:
        logger.warning("Re-auth failed for vehicle %s", vehicle.id, exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await auth.close()

    if body.skoda_username or body.skoda_password or body.skoda_spin:
        new_config = json.dumps({"username": username, "password": password, "spin": spin})
        vehicle.connector_config_encrypted = encrypt_field(new_config)

    access_token = tokens.get("accessToken") or tokens.get("access_token", "")
    refresh_token = tokens.get("refreshToken") or tokens.get("refresh_token", "")
    expires_in = tokens.get("expiresIn") or tokens.get("expires_in", 3600)
    token_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
    
    # Needs to eagerly load connector session or use execute
    cs_res = await db.execute(select(ConnectorSession).where(ConnectorSession.user_vehicle_id == vehicle.id))
    cs = cs_res.scalar_one_or_none()
    if cs:
        cs.access_token_encrypted = encrypt_field(access_token)
        cs.refresh_token_encrypted = encrypt_field(refresh_token)
        cs.token_expires_at = token_expires_at
        cs.status = "active"
    
    await db.commit()
    await publish_vehicle_refresh(str(vehicle.id))
    return {"status": "success", "message": "Re-authenticated successfully and queued for refresh"}


@router.get("/{vehicle_id}/status", response_model=VehicleStatusResponse)
async def get_vehicle_status(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)

    vin_plain = decrypt_field(vehicle.vin_encrypted)
    vin_last4 = vin_plain[-4:]

    latest_level_result = await db.execute(
        select(DriveLevel)
        .join(Drive, DriveLevel.drive_id == Drive.id)
        .where(Drive.user_vehicle_id == vehicle.id)
        .order_by(DriveLevel.last_date.desc())
        .limit(1)
    )
    latest_level = latest_level_result.scalar_one_or_none()

    latest_range_result = await db.execute(
        select(DriveRange)
        .join(Drive, DriveRange.drive_id == Drive.id)
        .where(Drive.user_vehicle_id == vehicle.id)
        .order_by(DriveRange.last_date.desc())
        .limit(1)
    )
    latest_range = latest_range_result.scalar_one_or_none()

    latest_charging_result = await db.execute(
        select(ChargingState)
        .where(ChargingState.user_vehicle_id == vehicle.id)
        .order_by(ChargingState.last_date.desc())
        .limit(1)
    )
    latest_charging = latest_charging_result.scalar_one_or_none()

    latest_state_result = await db.execute(
        select(VehicleState)
        .where(VehicleState.user_vehicle_id == vehicle.id)
        .order_by(VehicleState.last_date.desc())
        .limit(1)
    )
    latest_state = latest_state_result.scalar_one_or_none()

    latest_pos_result = await db.execute(
        select(VehiclePosition)
        .where(VehiclePosition.user_vehicle_id == vehicle.id)
        .order_by(VehiclePosition.captured_at.desc())
        .limit(1)
    )
    latest_pos = latest_pos_result.scalar_one_or_none()

    latest_ac_result = await db.execute(
        select(AirConditioningState)
        .where(AirConditioningState.user_vehicle_id == vehicle.id)
        .order_by(AirConditioningState.captured_at.desc())
        .limit(1)
    )
    latest_ac = latest_ac_result.scalar_one_or_none()

    latest_maint_result = await db.execute(
        select(MaintenanceReport)
        .where(MaintenanceReport.user_vehicle_id == vehicle.id)
        .order_by(MaintenanceReport.captured_at.desc())
        .limit(1)
    )
    latest_maint = latest_maint_result.scalar_one_or_none()

    latest_conn_result = await db.execute(
        select(ConnectionState)
        .where(ConnectionState.user_vehicle_id == vehicle.id)
        .order_by(ConnectionState.captured_at.desc())
        .limit(1)
    )
    latest_conn = latest_conn_result.scalar_one_or_none()

    timestamps = [
        t
        for t in [
            latest_level.last_date if latest_level else None,
            latest_range.last_date if latest_range else None,
            latest_charging.last_date if latest_charging else None,
            latest_state.last_date if latest_state else None,
            latest_pos.captured_at if latest_pos else None,
        ]
        if t is not None
    ]

    cs = vehicle.connector_session

    return VehicleStatusResponse(
        vin_last4=vin_last4,
        display_name=vehicle.display_name,
        manufacturer=vehicle.manufacturer,
        model=vehicle.model,
        model_year=vehicle.model_year,
        image_url=vehicle.image_url,
        battery_capacity_kwh=vehicle.battery_capacity_kwh,
        latest_battery_level=latest_level.level if latest_level else None,
        latest_range_km=latest_range.range_km if latest_range else None,
        latest_charging_state=latest_charging.state if latest_charging else None,
        latest_vehicle_state=latest_state.state if latest_state else None,
        latest_position=(
            {"latitude": latest_pos.latitude, "longitude": latest_pos.longitude}
            if latest_pos
            else None
        ),
        last_updated=max(timestamps) if timestamps else None,
        charging_power_kw=latest_charging.charge_power_kw if latest_charging else None,
        remaining_charge_time_min=latest_charging.remaining_time_min if latest_charging else None,
        target_soc=latest_charging.target_soc_pct if latest_charging else None,
        charge_type=latest_charging.charge_type if latest_charging else None,
        doors_locked=latest_state.doors_locked if latest_state else None,
        doors_open=latest_state.doors_open if latest_state else None,
        windows_open=latest_state.windows_open if latest_state else None,
        lights_on=latest_state.lights_on if latest_state else None,
        trunk_open=latest_state.trunk_open if latest_state else None,
        bonnet_open=latest_state.bonnet_open if latest_state else None,
        climate_state=latest_ac.state if latest_ac else None,
        target_temp=latest_ac.target_temp_celsius if latest_ac else None,
        outside_temp=latest_ac.outside_temp_celsius if latest_ac else None,
        odometer_km=latest_maint.mileage_in_km if latest_maint else None,
        inspection_due_days=latest_maint.inspection_due_in_days if latest_maint else None,
        is_online=latest_conn.is_online if latest_conn else None,
        is_in_motion=latest_conn.in_motion if latest_conn else None,
        connector_status=cs.status if cs else None,
    )


def _apply_time_filters(stmt, date_column, from_date, to_date, limit, skip: int = 0):
    if from_date:
        stmt = stmt.where(date_column >= from_date)
    if to_date:
        stmt = stmt.where(date_column <= to_date)
    return stmt.order_by(date_column.desc()).offset(skip).limit(limit)


def _apply_time_filters_chronological(stmt, date_column, from_date, to_date, limit, skip: int = 0):
    """Same as _apply_time_filters but order asc so we get the first N segments in the range (for step charts)."""
    if from_date:
        stmt = stmt.where(date_column >= from_date)
    if to_date:
        stmt = stmt.where(date_column <= to_date)
    return stmt.order_by(date_column.asc()).offset(skip).limit(limit)


def _merge_bands(
    rows: list,
    bands: list,
    state: str,
    *,
    gap_max: timedelta,
    from_attr: str = "first_date",
    to_attr: str = "last_date",
) -> None:
    """Merge consecutive rows into single bands when gap between end of one and start of next <= gap_max."""
    for r in rows:
        t_from = getattr(r, from_attr)
        if not t_from:
            continue
        t_to = getattr(r, to_attr) or t_from
        if bands and bands[-1].state == state and bands[-1].to_date and (t_from - bands[-1].to_date) <= gap_max:
            bands[-1] = StateBandItem(from_date=bands[-1].from_date, to_date=max(bands[-1].to_date, t_to), state=state)
        else:
            bands.append(StateBandItem(from_date=t_from, to_date=t_to, state=state))


@router.get("/{vehicle_id}/battery", response_model=list[BatteryHistoryItem])
async def get_battery_history(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = (
        select(DriveLevel)
        .join(Drive, DriveLevel.drive_id == Drive.id)
        .where(Drive.user_vehicle_id == vehicle.id)
    )
    stmt = _apply_time_filters(stmt, DriveLevel.last_date, from_date, to_date, limit)
    result = await db.execute(stmt)
    rows = [r for r in result.scalars().all() if r.level is not None]
    _log_statistics_query(
        "battery", vehicle_id, from_date=from_date, to_date=to_date, limit=limit, result_count=len(rows), sql=_stmt_to_sql(stmt)
    )
    return [BatteryHistoryItem(timestamp=row.last_date, level=row.level) for row in rows]


@router.get("/{vehicle_id}/range", response_model=list[RangeHistoryItem])
async def get_range_history(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = (
        select(DriveRange)
        .join(Drive, DriveRange.drive_id == Drive.id)
        .where(Drive.user_vehicle_id == vehicle.id)
    )
    stmt = _apply_time_filters(stmt, DriveRange.last_date, from_date, to_date, limit)
    result = await db.execute(stmt)
    rows = [r for r in result.scalars().all() if r.range_km is not None]
    _log_statistics_query(
        "range", vehicle_id, from_date=from_date, to_date=to_date, limit=limit, result_count=len(rows), sql=_stmt_to_sql(stmt)
    )
    return [RangeHistoryItem(timestamp=row.last_date, range_km=row.range_km) for row in rows]


@router.get("/{vehicle_id}/overview/levels-step", response_model=list[BatteryHistoryItem])
async def get_levels_step(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Level (SoC %) collapsed into step segments — consecutive identical values merged."""
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = (
        select(DriveLevel.first_date, DriveLevel.last_date, DriveLevel.level)
        .join(Drive, DriveLevel.drive_id == Drive.id)
        .where(Drive.user_vehicle_id == vehicle.id, DriveLevel.level.isnot(None))
    )
    if from_date:
        stmt = stmt.where(DriveLevel.last_date >= from_date)
    if to_date:
        stmt = stmt.where(DriveLevel.last_date <= to_date)
    stmt = stmt.order_by(DriveLevel.first_date.asc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).all()

    # Collapse consecutive identical levels into step segments
    out: list[BatteryHistoryItem] = []
    prev_level: float | None = None
    for r in rows:
        lvl = float(r.level)
        ts = r.first_date
        if lvl != prev_level:
            out.append(BatteryHistoryItem(timestamp=ts, level=lvl))
            prev_level = lvl
        last_ts = r.last_date or ts
        if len(out) >= 2 and out[-1].level == lvl and out[-2].level == lvl:
            out[-1] = BatteryHistoryItem(timestamp=last_ts, level=lvl)
        elif len(out) >= 1 and out[-1].timestamp != last_ts:
            out.append(BatteryHistoryItem(timestamp=last_ts, level=lvl))

    _log_statistics_query(
        "overview/levels-step", vehicle_id, from_date=from_date, to_date=to_date, limit=limit,
        result_count=len(out), sql=_stmt_to_sql(stmt)
    )
    return out


@router.get("/{vehicle_id}/overview/ranges-step", response_model=list[RangeHistoryItem])
async def get_ranges_step(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Range (km) collapsed into step segments — consecutive identical values merged."""
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = (
        select(DriveRange.first_date, DriveRange.last_date, DriveRange.range_km)
        .join(Drive, DriveRange.drive_id == Drive.id)
        .where(Drive.user_vehicle_id == vehicle.id, DriveRange.range_km.isnot(None))
    )
    if from_date:
        stmt = stmt.where(DriveRange.last_date >= from_date)
    if to_date:
        stmt = stmt.where(DriveRange.last_date <= to_date)
    stmt = stmt.order_by(DriveRange.first_date.asc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).all()

    # Collapse consecutive identical ranges into step segments
    out: list[RangeHistoryItem] = []
    prev_km: float | None = None
    for r in rows:
        km = float(r.range_km)
        ts = r.first_date
        if km != prev_km:
            out.append(RangeHistoryItem(timestamp=ts, range_km=km))
            prev_km = km
        last_ts = r.last_date or ts
        if len(out) >= 2 and out[-1].range_km == km and out[-2].range_km == km:
            out[-1] = RangeHistoryItem(timestamp=last_ts, range_km=km)
        elif len(out) >= 1 and out[-1].timestamp != last_ts:
            out.append(RangeHistoryItem(timestamp=last_ts, range_km=km))

    _log_statistics_query(
        "overview/ranges-step", vehicle_id, from_date=from_date, to_date=to_date, limit=limit,
        result_count=len(out), sql=_stmt_to_sql(stmt)
    )
    return out


@router.get("/{vehicle_id}/overview/outside-temperature", response_model=list[dict])
async def get_outside_temperature(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Outside temperature from air_conditioning_states (Grafana outside_temperatures-style)."""
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = (
        select(AirConditioningState.captured_at, AirConditioningState.outside_temp_celsius)
        .where(
            AirConditioningState.user_vehicle_id == vehicle.id,
            AirConditioningState.outside_temp_celsius.isnot(None),
        )
    )
    stmt = _apply_time_filters(stmt, AirConditioningState.captured_at, from_date, to_date, limit)
    rows = (await db.execute(stmt)).all()
    out_ac = [{"time": r.captured_at.isoformat(), "outside_temp_celsius": float(r.outside_temp_celsius)} for r in rows]
    _log_statistics_query(
        "overview/outside-temperature", vehicle_id, from_date=from_date, to_date=to_date, limit=limit, result_count=len(out_ac), sql=_stmt_to_sql(stmt)
    )
    return out_ac


@router.get("/{vehicle_id}/charging", response_model=list[ChargingStateItem])
async def get_charging_history(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = select(ChargingState).where(
        ChargingState.user_vehicle_id == vehicle.id
    )
    stmt = _apply_time_filters(stmt, ChargingState.last_date, from_date, to_date, limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    _log_statistics_query(
        "charging", vehicle_id, from_date=from_date, to_date=to_date, limit=limit, result_count=len(rows), sql=_stmt_to_sql(stmt)
    )
    return rows


@router.get("/{vehicle_id}/charging/sessions", response_model=list[ChargingSessionItem])
async def get_charging_sessions(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = select(ChargingSession).where(
        ChargingSession.user_vehicle_id == vehicle.id
    )
    stmt = _apply_time_filters(
        stmt, ChargingSession.session_start, from_date, to_date, limit
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{vehicle_id}/trips", response_model=list[TripItem])
async def get_trips(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = select(Trip).where(Trip.user_vehicle_id == vehicle.id)
    stmt = _apply_time_filters(stmt, Trip.start_date, from_date, to_date, limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{vehicle_id}/trips-analytics", response_model=list[TripAnalyticsItem])
async def get_trips_analytics(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns trip analytics data from the v_trip_analytics view.
    """
    from sqlalchemy import select, column
    await _get_user_vehicle(vehicle_id, user, db)

    stmt = (
        select(
            column("id").label("trip_id"),
            column("start_date").label("start_time"),
            column("end_date").label("end_time"),
            column("start_lat").label("start_latitude"),
            column("start_lon").label("start_longitude"),
            column("end_lat").label("destination_latitude"),
            column("end_lon").label("destination_longitude"),
            column("distance_km").label("distance_km"),
            column("duration_minutes").label("duration_minutes"),
            column("average_speed_kmh").label("average_speed_kmh"),
            column("total_kwh_consumed").label("kwh_used"),
            column("efficiency_kwh_per_100km").label("efficiency_kwh_100km"),
        )
        .select_from(text("v_trip_analytics"))
        .where(column("user_vehicle_id") == vehicle_id)
    )

    if from_date:
        stmt = stmt.where(column("start_date") >= from_date)
    if to_date:
        stmt = stmt.where(column("start_date") <= to_date)

    stmt = stmt.order_by(column("start_date").desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    rows = result.fetchall()

    _log_statistics_query(
        "trips-analytics",
        vehicle_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        result_count=len(rows),
        sql=_stmt_to_sql(stmt),
    )

    return [
        TripAnalyticsItem(
            trip_id=row.trip_id,
            start_time=row.start_time,
            end_time=row.end_time,
            start_latitude=row.start_latitude,
            start_longitude=row.start_longitude,
            destination_latitude=row.destination_latitude,
            destination_longitude=row.destination_longitude,
            distance_km=row.distance_km,
            duration_minutes=row.duration_minutes,
            average_speed_kmh=row.average_speed_kmh,
            kwh_used=row.kwh_used,
            efficiency_kwh_100km=row.efficiency_kwh_100km,
        )
        for row in rows
    ]



@router.get("/{vehicle_id}/positions", response_model=list[PositionItem])
async def get_positions(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = select(VehiclePosition).where(
        VehiclePosition.user_vehicle_id == vehicle.id
    )
    stmt = _apply_time_filters(
        stmt, VehiclePosition.captured_at, from_date, to_date, limit
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{vehicle_id}/air-conditioning", response_model=list[AirConditioningItem])
async def get_air_conditioning_history(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = select(AirConditioningState).where(
        AirConditioningState.user_vehicle_id == vehicle.id
    )
    stmt = _apply_time_filters(stmt, AirConditioningState.captured_at, from_date, to_date, limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{vehicle_id}/maintenance", response_model=list[MaintenanceItem])
async def get_maintenance_history(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = select(MaintenanceReport).where(
        MaintenanceReport.user_vehicle_id == vehicle.id
    )
    stmt = _apply_time_filters(stmt, MaintenanceReport.captured_at, from_date, to_date, limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{vehicle_id}/odometer", response_model=list[OdometerItem])
async def get_odometer_history(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = select(OdometerReading).where(
        OdometerReading.user_vehicle_id == vehicle.id
    )
    stmt = _apply_time_filters(stmt, OdometerReading.captured_at, from_date, to_date, limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    _log_statistics_query(
        "odometer", vehicle_id, from_date=from_date, to_date=to_date, limit=limit, result_count=len(rows), sql=_stmt_to_sql(stmt)
    )
    return rows


@router.get("/{vehicle_id}/connection-states", response_model=list[ConnectionStateItem])
async def get_connection_states(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = select(ConnectionState).where(
        ConnectionState.user_vehicle_id == vehicle.id
    )
    stmt = _apply_time_filters(stmt, ConnectionState.captured_at, from_date, to_date, limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{vehicle_id}/overview/state-bands", response_model=list[StateBandItem])
async def get_overview_state_bands(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return time bands for Car Overview state timeline: Online, Climatization, Charging, Driving."""
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    bands: list[StateBandItem] = []

    # Charging: from charging_states (CHARGING/CONSERVATION); merge consecutive rows within 30 min into one band
    stmt_c = (
        select(ChargingState.first_date, ChargingState.last_date)
        .where(
            ChargingState.user_vehicle_id == vehicle.id,
            ChargingState.state.in_(["CHARGING", "CONSERVATION"]),
        )
    )
    if from_date:
        stmt_c = stmt_c.where(ChargingState.last_date >= from_date)
    if to_date:
        stmt_c = stmt_c.where(ChargingState.first_date <= to_date)
    stmt_c = stmt_c.order_by(ChargingState.first_date.asc()).limit(limit * 2)
    rows_c = (await db.execute(stmt_c)).all()
    _merge_bands(rows_c, bands, "charging", gap_max=timedelta(minutes=30), from_attr="first_date", to_attr="last_date")

    # Driving: from connection_states where ignition_on=True or in_motion=True (collector never writes Trip)
    stmt_conn_drive = (
        select(ConnectionState.captured_at, ConnectionState.ignition_on, ConnectionState.in_motion)
        .where(ConnectionState.user_vehicle_id == vehicle.id)
    )
    if from_date:
        stmt_conn_drive = stmt_conn_drive.where(ConnectionState.captured_at >= from_date)
    if to_date:
        stmt_conn_drive = stmt_conn_drive.where(ConnectionState.captured_at <= to_date)
    stmt_conn_drive = stmt_conn_drive.order_by(ConnectionState.captured_at.asc()).limit(limit * 2)
    rows_drive = (await db.execute(stmt_conn_drive)).all()
    i = 0
    while i < len(rows_drive):
        r = rows_drive[i]
        if r.ignition_on is True or r.in_motion is True:
            t_from = r.captured_at
            t_to = r.captured_at
            j = i + 1
            while j < len(rows_drive) and (rows_drive[j].ignition_on is True or rows_drive[j].in_motion is True):
                t_to = rows_drive[j].captured_at
                j += 1
            bands.append(StateBandItem(from_date=t_from, to_date=t_to, state="driving"))
            i = j
        else:
            i += 1

    # Online: build intervals from connection_states (consecutive is_online=True)
    stmt_conn = (
        select(ConnectionState.captured_at, ConnectionState.is_online)
        .where(ConnectionState.user_vehicle_id == vehicle.id)
    )
    if from_date:
        stmt_conn = stmt_conn.where(ConnectionState.captured_at >= from_date)
    if to_date:
        stmt_conn = stmt_conn.where(ConnectionState.captured_at <= to_date)
    stmt_conn = stmt_conn.order_by(ConnectionState.captured_at.asc()).limit(limit * 2)
    rows_conn = (await db.execute(stmt_conn)).all()
    i = 0
    while i < len(rows_conn):
        if rows_conn[i].is_online is True:
            t_from = rows_conn[i].captured_at
            t_to = rows_conn[i].captured_at
            j = i + 1
            while j < len(rows_conn) and rows_conn[j].is_online is True:
                t_to = rows_conn[j].captured_at
                j += 1
            bands.append(StateBandItem(from_date=t_from, to_date=t_to, state="online"))
            i = j
        else:
            i += 1

    # Climatization: air_conditioning_states where state != 'OFF'; merge consecutive within 30 min
    stmt_ac = (
        select(AirConditioningState.captured_at)
        .where(
            AirConditioningState.user_vehicle_id == vehicle.id,
            AirConditioningState.state.isnot(None),
            AirConditioningState.state != "OFF",
        )
    )
    if from_date:
        stmt_ac = stmt_ac.where(AirConditioningState.captured_at >= from_date)
    if to_date:
        stmt_ac = stmt_ac.where(AirConditioningState.captured_at <= to_date)
    stmt_ac = stmt_ac.order_by(AirConditioningState.captured_at.asc()).limit(limit * 2)
    rows_ac = (await db.execute(stmt_ac)).all()
    # Build (first_date, last_date) pairs: use captured_at for both; merge if next row within 30 min
    ac_bands: list[tuple[datetime, datetime]] = []
    for r in rows_ac:
        t = r.captured_at
        if ac_bands and (t - ac_bands[-1][1]) <= timedelta(minutes=30):
            ac_bands[-1] = (ac_bands[-1][0], t)
        else:
            ac_bands.append((t, t))
    for t_from, t_to in ac_bands:
        bands.append(StateBandItem(from_date=t_from, to_date=t_to, state="climatization"))

    bands.sort(key=lambda b: b.from_date)
    result = bands[:limit]
    bands_by_state: dict[str, int] = {}
    for b in result:
        bands_by_state[b.state] = bands_by_state.get(b.state, 0) + 1
    sql_parts = [_stmt_to_sql(stmt_c), _stmt_to_sql(stmt_conn_drive), _stmt_to_sql(stmt_conn), _stmt_to_sql(stmt_ac)]
    sql_combined = " | ".join(p for p in sql_parts if p) or None
    _log_statistics_query(
        "overview/state-bands", vehicle_id, from_date=from_date, to_date=to_date, limit=limit, result_count=len(result), extra={"bands_by_state": bands_by_state}, sql=sql_combined
    )
    return result


@router.get("/{vehicle_id}/overview/wltp", response_model=WLTPResponse)
async def get_overview_wltp(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """WLTP range in km for reference line (from user setting, drives, or specifications)."""
    vehicle = await _get_user_vehicle(vehicle_id, user, db)

    # 1. User setting (Priority)
    if vehicle.wltp_range_km:
        return WLTPResponse(wltp_range_km=vehicle.wltp_range_km)

    # 2. Latest drive entry
    stmt = (
        select(Drive.wltp_range)
        .where(Drive.user_vehicle_id == vehicle.id, Drive.wltp_range.isnot(None))
        .order_by(Drive.id.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return WLTPResponse(wltp_range_km=float(row))
    
    # 3. Fallback to specifications
    spec = vehicle.specifications or {}
    wltp = spec.get("wltpRange") or spec.get("wltp_range")
    if wltp is not None:
        try:
            return WLTPResponse(wltp_range_km=float(wltp))
        except (TypeError, ValueError):
            pass
            
    # 4. Model-based fallbacks
    model_str = (vehicle.model or "").upper()
    trim_str = (vehicle.trim_level or "").upper()
    
    if "ENYAQ" in model_str:
        if "80X" in trim_str or "RS" in trim_str or "VRS" in trim_str:
            wltp = 520.0
        elif "80" in trim_str:
            wltp = 540.0
        elif "60" in trim_str:
            wltp = 410.0
        else:
            wltp = 500.0
        return WLTPResponse(wltp_range_km=wltp)

    return WLTPResponse(wltp_range_km=None)


def _apply_time_filters_range_drive(
    stmt, from_date: datetime | None, to_date: datetime | None, limit: int, date_col, skip: int = 0
):
    if from_date:
        stmt = stmt.where(date_col >= from_date)
    if to_date:
        stmt = stmt.where(date_col <= to_date)
    return stmt.order_by(date_col.asc()).limit(limit * 2)


@router.get("/{vehicle_id}/overview/range-at-100", response_model=list[dict])
async def get_overview_range_at_100(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = (
        select(
            DriveRange.first_date,
            DriveRange.last_date,
            (DriveRange.range_km / (DriveLevel.level / 100.0)).label("range_estimated_full"),
        )
        .join(Drive, DriveRange.drive_id == Drive.id)
        .join(
            DriveLevel,
            (DriveLevel.drive_id == DriveRange.drive_id)
            & (DriveLevel.first_date == DriveRange.first_date)
        )
        .where(
            Drive.user_vehicle_id == vehicle.id,
            DriveLevel.level.isnot(None),
            DriveLevel.level > 0,
            DriveRange.range_km.isnot(None),
        )
    )
    stmt = _apply_time_filters(
        stmt, DriveRange.last_date, from_date, to_date, limit
    )
    rows = (await db.execute(stmt)).all()
    out = []
    for r in rows:
        val = float(r.range_estimated_full)
        out.append({"time": r.first_date.isoformat(), "range_estimated_full": val})
        out.append({"time": (r.last_date or r.first_date).isoformat(), "range_estimated_full": val})
    out.sort(key=lambda p: p["time"])
    out = out[: limit * 2]
    return out


@router.get("/{vehicle_id}/overview/efficiency", response_model=list[dict])
async def get_overview_efficiency(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Efficiency % = range_estimated_full / wltp_range * 100 (Grafana-style)."""
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    wltp_resp = await get_overview_wltp(vehicle_id, user, db)
    wltp = wltp_resp.wltp_range_km
    if wltp is None or wltp <= 0:
        return []

    stmt = (
        select(
            DriveRange.first_date,
            DriveRange.last_date,
            (((DriveRange.range_km / (DriveLevel.level / 100.0)) / float(wltp)) * 100.0).label("efficiency_pct"),
        )
        .join(Drive, DriveRange.drive_id == Drive.id)
        .join(
            DriveLevel,
            (DriveLevel.drive_id == DriveRange.drive_id)
            & (DriveLevel.first_date == DriveRange.first_date)
        )
        .where(
            Drive.user_vehicle_id == vehicle.id,
            DriveLevel.level.isnot(None),
            DriveLevel.level > 0,
            DriveRange.range_km.isnot(None),
        )
    )
    stmt = _apply_time_filters(
        stmt, DriveRange.last_date, from_date, to_date, limit
    )
    rows = (await db.execute(stmt)).all()
    out = []
    for r in rows:
        val = float(r.efficiency_pct)
        out.append({"time": r.first_date.isoformat(), "efficiency_pct": val})
        out.append({"time": (r.last_date or r.first_date).isoformat(), "efficiency_pct": val})
    out.sort(key=lambda p: p["time"])
    out = out[: limit * 2]
    return out


@router.get("/{vehicle_id}/statistics", response_model=list[StatisticsPeriod])
async def get_statistics(
    vehicle_id: uuid.UUID,
    period: str = Query(default="day", pattern="^(day|week|month|year)$"),
    limit: int = Query(default=30, ge=1, le=365),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)

    trunc_map = {"day": "day", "week": "week", "month": "month", "year": "year"}
    trunc = trunc_map[period]

    # Sub-query for Trips
    trip_where = [Trip.user_vehicle_id == vehicle.id]
    if from_date:
        trip_where.append(Trip.start_date >= from_date)
    if to_date:
        trip_where.append(Trip.start_date <= to_date)
    time_driven_expr = func.sum(case((Trip.end_date.isnot(None), func.extract("epoch", Trip.end_date - Trip.start_date)), else_=0,))
    median_expr = func.percentile_cont(0.5).within_group((Trip.end_odometer - Trip.start_odometer).asc()).label("median_distance")
    stmt_trip = (
        select(
            func.date_trunc(trunc, Trip.start_date).label("period"),
            func.count().label("drives_count"),
            func.coalesce(func.sum(Trip.end_odometer - Trip.start_odometer), 0).label("total_distance"),
            func.coalesce(time_driven_expr, 0).label("time_driven_seconds"),
            median_expr,
        )
        .where(*trip_where)
        .group_by("period")
        .order_by(text("period DESC"))
        .offset(skip).limit(limit)
    )
    trip_stats = await db.execute(stmt_trip)
    trip_rows = {row.period: row for row in trip_stats.all()}

    # Sub-query for Charging
    charge_where = [ChargingSession.user_vehicle_id == vehicle.id]
    if from_date:
        charge_where.append(ChargingSession.session_start >= from_date)
    if to_date:
        charge_where.append(ChargingSession.session_start <= to_date)
    time_charging_expr = func.sum(func.extract("epoch", func.coalesce(ChargingSession.session_end, ChargingSession.session_start) - ChargingSession.session_start,))
    stmt_charge = (
        select(
            func.date_trunc(trunc, ChargingSession.session_start).label("period"),
            func.count().label("sessions_count"),
            func.coalesce(func.sum(ChargingSession.energy_kwh), 0).label("total_energy"),
            func.coalesce(time_charging_expr, 0).label("time_charging_seconds"),
        )
        .where(*charge_where)
        .group_by("period")
        .order_by(text("period DESC"))
        .offset(skip).limit(limit)
    )
    charge_stats = await db.execute(stmt_charge)
    charge_rows = {row.period: row for row in charge_stats.all()}

    # Sub-query for Consumption
    params = {"vehicle_id": vehicle_id}
    consume_where_clauses = ["user_vehicle_id = :vehicle_id"]
    if from_date:
        consume_where_clauses.append("consumption_day >= :from_date")
        params["from_date"] = from_date
    if to_date:
        consume_where_clauses.append("consumption_day <= :to_date")
        params["to_date"] = to_date
    stmt_consume = (
        select(
            func.date_trunc(trunc, text("consumption_day")).label("period"),
            func.sum(text("total_kwh_consumed")).label("total_energy_consumed"),
        )
        .select_from(text("v_daily_consumption"))
        .where(text(" AND ".join(consume_where_clauses)))
        .params(params)
        .group_by("period")
        .order_by(text("period DESC"))
        .offset(skip).limit(limit)
    )
    consume_stats = await db.execute(stmt_consume)
    consume_rows = {row.period: row for row in consume_stats.all()}

    # Merge results
    all_periods = sorted(set(list(trip_rows.keys()) + list(charge_rows.keys()) + list(consume_rows.keys())), reverse=True)[:limit]

    results = []
    for p in all_periods:
        tr = trip_rows.get(p)
        cr = charge_rows.get(p)
        co = consume_rows.get(p)
        sessions_count = int(cr.sessions_count) if cr else 0
        total_energy = float(cr.total_energy) if cr else 0
        time_charging = float(cr.time_charging_seconds) if cr else 0
        total_consumed = float(co.total_energy_consumed) if co else 0
        results.append(
            StatisticsPeriod(
                period=p.isoformat() if p else "",
                drives_count=int(tr.drives_count) if tr else 0,
                total_distance_km=float(tr.total_distance) if tr else 0,
                time_driven_seconds=float(tr.time_driven_seconds) if tr else 0,
                median_distance_km=float(tr.median_distance) if tr and tr.median_distance is not None else None,
                charging_sessions_count=sessions_count,
                total_energy_kwh=total_energy,
                total_kwh_consumed=total_consumed,
                avg_energy_per_session_kwh=round(total_energy / sessions_count, 2) if sessions_count else 0,
                time_charging_seconds=time_charging,
            )
        )

    _log_statistics_query(
        "statistics", vehicle_id, from_date=from_date, to_date=to_date, limit=limit, result_count=len(results), extra={"period": period}, sql=" | ".join(filter(None, [_stmt_to_sql(stmt_trip), _stmt_to_sql(stmt_charge), _stmt_to_sql(stmt_consume)])) or None
    )
    return results


@router.get("/{vehicle_id}/overview/battery-temperature", response_model=list[dict])
async def get_battery_temperature(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = (
        select(BatteryTemperature.first_date, BatteryTemperature.battery_temperature)
        .where(
            BatteryTemperature.user_vehicle_id == vehicle.id,
            BatteryTemperature.battery_temperature.isnot(None),
        )
    )
    stmt = _apply_time_filters(stmt, BatteryTemperature.first_date, from_date, to_date, limit)
    rows = (await db.execute(stmt)).all()
    return [{"time": r.first_date.isoformat(), "battery_temperature": float(r.battery_temperature)} for r in rows]

@router.get("/{vehicle_id}/overview/charging-power", response_model=list[dict])
async def get_charging_power(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    stmt = (
        select(ChargingPower.first_date, ChargingPower.power)
        .where(
            ChargingPower.user_vehicle_id == vehicle.id,
            ChargingPower.power.isnot(None),
        )
    )
    stmt = _apply_time_filters(stmt, ChargingPower.first_date, from_date, to_date, limit)
    rows = (await db.execute(stmt)).all()
    return [{"time": r.first_date.isoformat(), "power": float(r.power)} for r in rows]


@router.get("/{vehicle_id}/overview/electric-consumption", response_model=list[dict])
async def get_overview_electric_consumption(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_user_vehicle(vehicle_id, user, db)
    # Get battery capacity from vehicle spec, fallback to 77 kWh (Enyaq 80)
    battery_kwh = float(vehicle.battery_capacity_kwh) if vehicle.battery_capacity_kwh else 77.0
    
    # Consumption (kWh/100km) = (battery_capacity / range_estimated_full) * 100
    stmt = (
        select(
            DriveRange.first_date,
            DriveRange.last_date,
            ((battery_kwh / (DriveRange.range_km / (DriveLevel.level / 100.0))) * 100.0).label("consumption"),
        )
        .join(Drive, DriveRange.drive_id == Drive.id)
        .join(
            DriveLevel,
            (DriveLevel.drive_id == DriveRange.drive_id)
            & (DriveLevel.first_date == DriveRange.first_date)
        )
        .where(
            Drive.user_vehicle_id == vehicle.id,
            DriveLevel.level.isnot(None),
            DriveLevel.level > 0,
            DriveRange.range_km.isnot(None),
            DriveRange.range_km > 0
        )
    )
    stmt = _apply_time_filters(
        stmt, DriveRange.last_date, from_date, to_date, limit
    )
    rows = (await db.execute(stmt)).all()
    out = []
    for r in rows:
        val = float(r.consumption)
        out.append({"time": r.first_date.isoformat(), "consumption": val})
        out.append({"time": (r.last_date or r.first_date).isoformat(), "consumption": val})
    out.sort(key=lambda p: p["time"])
    return out[: limit * 2]


@router.get("/{vehicle_id}/overview/visited", response_model=list[VisitedLocationItem])
async def get_visited_locations(
    vehicle_id: uuid.UUID,
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
    skip: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Historical visited locations combining vehicle positions and charging session locations."""
    from sqlalchemy import union_all, literal_column
    vehicle = await _get_user_vehicle(vehicle_id, user, db)

    # 1. Drive positions
    q1 = select(
        VehiclePosition.latitude,
        VehiclePosition.longitude,
        VehiclePosition.captured_at.label("timestamp"),
        literal_column("'position'").label("source")
    ).where(VehiclePosition.user_vehicle_id == vehicle.id)
    if from_date:
        q1 = q1.where(VehiclePosition.captured_at >= from_date)
    if to_date:
        q1 = q1.where(VehiclePosition.captured_at <= to_date)

    # 2. Charging session locations
    q2 = select(
        ChargingSession.latitude,
        ChargingSession.longitude,
        ChargingSession.session_start.label("timestamp"),
        literal_column("'charging'").label("source")
    ).where(
        ChargingSession.user_vehicle_id == vehicle.id,
        ChargingSession.latitude.isnot(None),
        ChargingSession.longitude.isnot(None),
    )
    if from_date:
        q2 = q2.where(ChargingSession.session_start >= from_date)
    if to_date:
        q2 = q2.where(ChargingSession.session_start <= to_date)

    # Combine with UNION ALL and paginate in SQL natively
    stmt = union_all(q1, q2).order_by(text("timestamp ASC")).offset(skip).limit(limit)
    
    rows = (await db.execute(stmt)).all()
    results = [
        VisitedLocationItem(latitude=r.latitude, longitude=r.longitude, timestamp=r.timestamp, source=r.source)
        for r in rows
    ]

    _log_statistics_query(
        "overview/visited", vehicle_id, from_date=from_date, to_date=to_date,
        limit=limit, result_count=len(results),
    )
    return results
