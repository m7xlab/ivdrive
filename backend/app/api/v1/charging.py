"""Charging data API endpoints.

Provides:
- GET /api/v1/vehicles/{vehicle_id}/charging/history — paginated charging session list
- GET /api/v1/vehicles/{vehicle_id}/charging/sessions/{session_id} — single session detail
- GET /api/v1/vehicles/{vehicle_id}/charging/stats — aggregated charging statistics
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.database import get_db
from app.models.telemetry import ChargingSession
from app.models.user import User
from app.models.vehicle import UserVehicle

router = APIRouter(prefix="/api/v1/vehicles", tags=["charging"])


# ─── Response schemas ────────────────────────────────────────────────────────


class ChargingSessionSummary(BaseModel):
    id: int
    session_start: datetime | None
    session_end: datetime | None
    start_level: float | None
    end_level: float | None
    charging_type: str | None
    energy_kwh: float | None
    base_cost_eur: float | None
    actual_cost_eur: float | None
    provider_name: str | None
    avg_temp_celsius: float | None
    latitude: float | None
    longitude: float | None

    model_config = {"from_attributes": True}


class ChargingSessionDetail(ChargingSessionSummary):
    odometer: float | None
    duration_minutes: float | None


class ChargingStats(BaseModel):
    total_sessions: int
    total_energy_kwh: float
    total_cost_eur: float
    avg_energy_per_session_kwh: float
    avg_cost_per_session_eur: float
    sessions_this_month: int
    energy_this_month_kwh: float
    cost_this_month_eur: float


class PaginatedChargingHistory(BaseModel):
    items: list[ChargingSessionSummary]
    total: int
    page: int
    page_size: int
    pages: int


# ─── Helpers ────────────────────────────────────────────────────────────────


async def get_user_vehicle(
    user_id: UUID,
    vehicle_id: UUID,
    db: AsyncSession,
) -> UserVehicle:
    stmt = select(UserVehicle).where(
        UserVehicle.id == vehicle_id,
        UserVehicle.user_id == user_id,
    )
    result = await db.execute(stmt)
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/{vehicle_id}/charging/history", response_model=PaginatedChargingHistory)
async def get_charging_history(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
) -> PaginatedChargingHistory:
    """Return paginated charging session history for a vehicle."""
    await get_user_vehicle(user.id, vehicle_id, db)

    # Count total
    count_stmt = select(func.count(ChargingSession.id)).where(
        ChargingSession.user_vehicle_id == vehicle_id
    )
    if from_date:
        count_stmt = count_stmt.where(ChargingSession.session_start >= from_date)
    if to_date:
        count_stmt = count_stmt.where(ChargingSession.session_start <= to_date)
    total = await db.scalar(count_stmt) or 0

    # Fetch page
    stmt = (
        select(ChargingSession)
        .where(ChargingSession.user_vehicle_id == vehicle_id)
        .order_by(ChargingSession.session_start.desc())
    )
    if from_date:
        stmt = stmt.where(ChargingSession.session_start >= from_date)
    if to_date:
        stmt = stmt.where(ChargingSession.session_start <= to_date)

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    sessions = result.scalars().all()

    items = [
        ChargingSessionSummary(
            id=s.id,
            session_start=s.session_start,
            session_end=s.session_end,
            start_level=s.start_level,
            end_level=s.end_level,
            charging_type=s.charging_type,
            energy_kwh=round(s.energy_kwh, 2) if s.energy_kwh else None,
            base_cost_eur=round(s.base_cost_eur, 2) if s.base_cost_eur else None,
            actual_cost_eur=round(s.actual_cost_eur, 2) if s.actual_cost_eur else None,
            provider_name=s.provider_name,
            avg_temp_celsius=round(s.avg_temp_celsius, 1) if s.avg_temp_celsius else None,
            latitude=s.latitude,
            longitude=s.longitude,
        )
        for s in sessions
    ]

    pages = (total + page_size - 1) // page_size if total > 0 else 1

    return PaginatedChargingHistory(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{vehicle_id}/charging/sessions/{session_id}", response_model=ChargingSessionDetail)
async def get_charging_session(
    vehicle_id: UUID,
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChargingSessionDetail:
    """Return detailed data for a single charging session."""
    await get_user_vehicle(user.id, vehicle_id, db)

    stmt = select(ChargingSession).where(
        ChargingSession.id == session_id,
        ChargingSession.user_vehicle_id == vehicle_id,
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Charging session not found")

    duration_minutes: float | None = None
    if session.session_start and session.session_end:
        delta = session.session_end - session.session_start
        duration_minutes = round(delta.total_seconds() / 60, 1)

    return ChargingSessionDetail(
        id=session.id,
        session_start=session.session_start,
        session_end=session.session_end,
        start_level=session.start_level,
        end_level=session.end_level,
        charging_type=session.charging_type,
        energy_kwh=round(session.energy_kwh, 2) if session.energy_kwh else None,
        base_cost_eur=round(session.base_cost_eur, 2) if session.base_cost_eur else None,
        actual_cost_eur=round(session.actual_cost_eur, 2) if session.actual_cost_eur else None,
        provider_name=session.provider_name,
        avg_temp_celsius=round(session.avg_temp_celsius, 1) if session.avg_temp_celsius else None,
        latitude=session.latitude,
        longitude=session.longitude,
        odometer=session.odometer,
        duration_minutes=duration_minutes,
    )


@router.get("/{vehicle_id}/charging/stats", response_model=ChargingStats)
async def get_charging_stats(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChargingStats:
    """Return aggregated charging statistics for a vehicle.

    Includes all-time totals and this-month breakdowns for kWh and cost.
    """
    await get_user_vehicle(user.id, vehicle_id, db)

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # All-time stats
    all_stmt = select(
        func.count(ChargingSession.id).label("count"),
        func.coalesce(func.sum(ChargingSession.energy_kwh), 0).label("total_kwh"),
        func.coalesce(func.sum(ChargingSession.actual_cost_eur), 0).label("total_cost"),
    ).where(ChargingSession.user_vehicle_id == vehicle_id)

    all_res = await db.execute(all_stmt)
    all_row = all_res.one()

    total_sessions = all_row.count or 0
    total_energy = float(all_row.total_kwh or 0)
    total_cost = float(all_row.total_cost or 0)
    avg_energy = total_energy / total_sessions if total_sessions > 0 else 0.0
    avg_cost = total_cost / total_sessions if total_sessions > 0 else 0.0

    # This-month stats
    month_stmt = select(
        func.count(ChargingSession.id).label("count"),
        func.coalesce(func.sum(ChargingSession.energy_kwh), 0).label("total_kwh"),
        func.coalesce(func.sum(ChargingSession.actual_cost_eur), 0).label("total_cost"),
    ).where(
        ChargingSession.user_vehicle_id == vehicle_id,
        ChargingSession.session_start >= month_start,
    )
    month_res = await db.execute(month_stmt)
    month_row = month_res.one()

    sessions_this_month = month_row.count or 0
    energy_this_month = float(month_row.total_kwh or 0)
    cost_this_month = float(month_row.total_cost or 0)

    return ChargingStats(
        total_sessions=total_sessions,
        total_energy_kwh=round(total_energy, 2),
        total_cost_eur=round(total_cost, 2),
        avg_energy_per_session_kwh=round(avg_energy, 2),
        avg_cost_per_session_eur=round(avg_cost, 2),
        sessions_this_month=sessions_this_month,
        energy_this_month_kwh=round(energy_this_month, 2),
        cost_this_month_eur=round(cost_this_month, 2),
    )
