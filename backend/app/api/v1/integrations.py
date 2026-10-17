"""User-facing integration settings (ABRP telemetry, etc.).

Credentials are per ABRP user:
- API key  → users.abrp_api_key_encrypted  (free Telemetry API key from ABRP account)
- Car token → abrp_connections.token_encrypted (per-vehicle Custom connection)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.models.vehicle import ABRPConnection, UserVehicle
from app.schemas.abrp import (
    AbrpConnectionOut,
    AbrpConnectionUpdate,
    AbrpNextChargeOut,
    AbrpSettingsOut,
    AbrpSettingsUpdate,
)
from app.services.abrp_sync import (
    refresh_next_charge,
    upsert_token_fields,
    upsert_user_api_key,
)

router = APIRouter()


def _hint(encrypted: str | None) -> tuple[bool, str | None]:
    if not encrypted:
        return False, None
    # Never return the secret — only a short opaque hint.
    return True, "••••" + encrypted[-4:]


def _conn_to_out(vehicle: UserVehicle, conn: ABRPConnection | None) -> AbrpConnectionOut:
    has_token, hint = _hint(conn.token_encrypted if conn else None)
    return AbrpConnectionOut(
        vehicle_id=str(vehicle.id),
        display_name=vehicle.display_name,
        enabled=bool(conn.enabled) if conn else False,
        has_token=has_token,
        token_hint=hint,
        car_model_typecode=conn.car_model_typecode if conn else None,
        last_sent_at=conn.last_sent_at if conn else None,
        last_error_text=conn.last_error_text if conn else None,
        consecutive_failures=conn.consecutive_failures if conn else 0,
        next_charge_pct=conn.next_charge_pct if conn else None,
        next_charge_fetched_at=conn.next_charge_fetched_at if conn else None,
    )


async def _get_owned_vehicle(vehicle_id: uuid.UUID, user: User, db: AsyncSession) -> UserVehicle:
    result = await db.execute(
        select(UserVehicle).where(UserVehicle.id == vehicle_id, UserVehicle.user_id == user.id)
    )
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


async def _get_or_create_conn(db: AsyncSession, vehicle_id: uuid.UUID) -> ABRPConnection:
    result = await db.execute(
        select(ABRPConnection).where(ABRPConnection.user_vehicle_id == vehicle_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        conn = ABRPConnection(user_vehicle_id=vehicle_id, enabled=False)
        db.add(conn)
        await db.flush()
    return conn


async def _load_settings(user: User, db: AsyncSession) -> AbrpSettingsOut:
    result = await db.execute(
        select(UserVehicle, ABRPConnection)
        .outerjoin(ABRPConnection, ABRPConnection.user_vehicle_id == UserVehicle.id)
        .where(UserVehicle.user_id == user.id)
        .order_by(UserVehicle.display_name)
    )
    rows = result.all()
    has_key, key_hint = _hint(user.abrp_api_key_encrypted)
    return AbrpSettingsOut(
        has_api_key=has_key,
        api_key_hint=key_hint,
        connections=[_conn_to_out(vehicle, conn) for vehicle, conn in rows],
    )


# ── User-level ABRP settings (API key) ──────────────────────────────────────


@router.get("/abrp", response_model=AbrpSettingsOut)
async def get_abrp_settings(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _load_settings(user, db)


@router.put("/abrp", response_model=AbrpSettingsOut)
async def update_abrp_settings(
    body: AbrpSettingsUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    upsert_user_api_key(user, body.api_key)
    await db.commit()
    await db.refresh(user)
    return await _load_settings(user, db)


# ── Per-vehicle ABRP connection (car token) ─────────────────────────────────


@router.put("/abrp/vehicles/{vehicle_id}", response_model=AbrpSettingsOut)
async def upsert_abrp_connection(
    vehicle_id: uuid.UUID,
    body: AbrpConnectionUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_vehicle(vehicle_id, user, db)
    conn = await _get_or_create_conn(db, vehicle_id)

    will_have_token = bool(conn.token_encrypted) if body.token is None else bool(body.token)
    if body.enabled is True and not will_have_token:
        raise HTTPException(status_code=400, detail="An ABRP vehicle token is required before enabling")

    upsert_token_fields(
        conn,
        token=body.token,
        enabled=body.enabled,
        car_model_typecode=body.car_model_typecode,
    )
    if body.enabled is True and not conn.token_encrypted:
        raise HTTPException(status_code=400, detail="An ABRP vehicle token is required before enabling")

    await db.commit()
    await db.refresh(user)
    return await _load_settings(user, db)


@router.delete("/abrp/vehicles/{vehicle_id}/token", response_model=AbrpSettingsOut)
async def clear_abrp_token(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_vehicle(vehicle_id, user, db)
    conn = await _get_or_create_conn(db, vehicle_id)
    conn.token_encrypted = None
    conn.enabled = False
    conn.last_error_text = None
    await db.commit()
    await db.refresh(user)
    return await _load_settings(user, db)


# ── next_charge (read-only from ABRP plan) ──────────────────────────────────


@router.get("/abrp/vehicles/{vehicle_id}/next-charge", response_model=AbrpNextChargeOut)
async def get_cached_next_charge(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_vehicle(vehicle_id, user, db)
    result = await db.execute(
        select(ABRPConnection).where(ABRPConnection.user_vehicle_id == vehicle_id)
    )
    conn = result.scalar_one_or_none()
    return AbrpNextChargeOut(
        vehicle_id=str(vehicle_id),
        next_charge_pct=conn.next_charge_pct if conn else None,
        fetched_at=conn.next_charge_fetched_at if conn else None,
    )


@router.post("/abrp/vehicles/{vehicle_id}/next-charge", response_model=AbrpNextChargeOut)
async def fetch_next_charge(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_owned_vehicle(vehicle_id, user, db)
    result = await db.execute(
        select(ABRPConnection).where(ABRPConnection.user_vehicle_id == vehicle_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None or not conn.token_encrypted:
        raise HTTPException(status_code=400, detail="ABRP vehicle token not configured")
    if not user.abrp_api_key_encrypted:
        raise HTTPException(status_code=400, detail="ABRP API key not configured in your settings")

    pct = await refresh_next_charge(db, vehicle)
    await db.refresh(conn)
    return AbrpNextChargeOut(
        vehicle_id=str(vehicle_id),
        next_charge_pct=pct,
        fetched_at=conn.next_charge_fetched_at,
        error=None if pct is not None else conn.last_error_text,
    )
