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
from app.schemas.skoda_public import (
    SkodaLoginConnect,
    SkodaPublicSettingsOut,
    SkodaPublicSettingsUpdate,
    SkodaPublicVehicleOut,
    SkodaVehicleSourceUpdate,
)
from app.services.abrp_sync import (
    refresh_next_charge,
    upsert_token_fields,
    upsert_user_api_key,
)
from app.services.crypto import encrypt_field

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

    # Reject enable-before-token before mutating the row. Covers both:
    # token already stored (body.token is None) and a non-empty new token.
    will_have_token = bool(conn.token_encrypted) if body.token is None else bool(body.token)
    if body.enabled is True and not will_have_token:
        raise HTTPException(status_code=400, detail="An ABRP vehicle token is required before enabling")

    upsert_token_fields(
        conn,
        token=body.token,
        enabled=body.enabled,
        car_model_typecode=body.car_model_typecode,
    )

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


# ── Official MyŠkoda Public API (v1.3.0 dual-stack) ─────────────────────────


async def _load_skoda_settings(user: User, db: AsyncSession) -> SkodaPublicSettingsOut:
    from datetime import UTC, datetime

    result = await db.execute(
        select(UserVehicle)
        .where(UserVehicle.user_id == user.id)
        .order_by(UserVehicle.display_name)
    )
    vehicles = result.scalars().all()
    has_key, hint = _hint(user.skoda_public_api_key_encrypted)

    expires_at = user.skoda_public_key_expires_at
    days_left = None
    expiry_warning = None
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        days_left = max(0, (expires_at - datetime.now(UTC)).days)
        if days_left <= 0:
            expiry_warning = (
                "Your MyŠkoda API key has expired. Create a new one in the MyŠkoda app "
                "or connect MyŠkoda Login and use “Create official key”."
            )
        elif days_left <= 14:
            expiry_warning = (
                f"Your MyŠkoda API key expires in {days_left} day"
                f"{'s' if days_left != 1 else ''}. "
                "Create a new key in the MyŠkoda app or via MyŠkoda Login soon — "
                "keys cannot be renewed automatically."
            )

    has_login = bool(user.skoda_login_access_encrypted or user.skoda_login_password_encrypted)
    login_hint = None
    if user.skoda_login_email:
        email = user.skoda_login_email
        login_hint = email[:2] + "***" + email[email.find("@") :] if "@" in email else "***"

    return SkodaPublicSettingsOut(
        has_api_key=has_key,
        api_key_hint=hint,
        key_expires_at=user.skoda_public_key_expires_at,
        expires_in_days=days_left,
        expiry_warning=expiry_warning,
        last_error=user.skoda_public_last_error,
        has_login=has_login,
        login_email_hint=login_hint,
        vehicles=[
            SkodaPublicVehicleOut(
                vehicle_id=str(v.id),
                display_name=v.display_name,
                telemetry_source=v.telemetry_source or "auto",
            )
            for v in vehicles
        ],
    )


@router.get("/skoda", response_model=SkodaPublicSettingsOut)
async def get_skoda_settings(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _load_skoda_settings(user, db)


@router.put("/skoda", response_model=SkodaPublicSettingsOut)
async def update_skoda_settings(
    body: SkodaPublicSettingsUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Save or clear the user's MyŠkoda Public API key (encrypted at rest)."""
    if body.api_key is not None:
        if body.api_key == "":
            user.skoda_public_api_key_encrypted = None
            user.skoda_public_key_expires_at = None
        else:
            user.skoda_public_api_key_encrypted = encrypt_field(body.api_key.strip())
        await db.commit()
        await db.refresh(user)
    return await _load_skoda_settings(user, db)


@router.put("/skoda/vehicles/{vehicle_id}", response_model=SkodaPublicSettingsOut)
async def update_skoda_vehicle_source(
    vehicle_id: uuid.UUID,
    body: SkodaVehicleSourceUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await _get_owned_vehicle(vehicle_id, user, db)
    source = (body.telemetry_source or "auto").lower()
    if source == "legacy":
        source = "login"
    if source not in ("auto", "login", "public"):
        raise HTTPException(status_code=400, detail="telemetry_source must be auto, MyŠkoda Public API (public), or MyŠkoda Login (login)")
    vehicle.telemetry_source = source
    await db.commit()
    await db.refresh(user)
    return await _load_skoda_settings(user, db)


@router.post("/skoda/login", response_model=SkodaPublicSettingsOut)
async def connect_skoda_login(
    body: SkodaLoginConnect,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect optional MyŠkoda Login (advanced BFF channel)."""
    from app.services.skoda_bff_auth import (
        BFFAuthInvalidCredentials,
        login_with_password,
    )
    from app.services.skoda_bff_api import SkodaBFFClient

    try:
        tokens = await login_with_password(body.email.strip(), body.password)
    except BFFAuthInvalidCredentials:
        raise HTTPException(
            status_code=400,
            detail="MyŠkoda email or password is incorrect.",
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Could not reach MyŠkoda login right now. Please try again.",
        )

    user.skoda_login_email = body.email.strip()
    user.skoda_login_password_encrypted = encrypt_field(body.password)
    user.skoda_login_access_encrypted = encrypt_field(tokens.get("accessToken") or "")
    refresh = tokens.get("refreshToken") or ""
    user.skoda_login_refresh_encrypted = encrypt_field(refresh) if refresh else None

    # Keys are created per vehicle (POST /skoda/vehicles/{id}/mint-key),
    # not from this account-level connect call.

    await db.commit()
    await db.refresh(user)
    return await _load_skoda_settings(user, db)


@router.delete("/skoda/login", response_model=SkodaPublicSettingsOut)
async def disconnect_skoda_login(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove MyŠkoda Login credentials. Keeps any official API key."""
    user.skoda_login_email = None
    user.skoda_login_password_encrypted = None
    user.skoda_login_access_encrypted = None
    user.skoda_login_refresh_encrypted = None
    await db.commit()
    await db.refresh(user)
    return await _load_skoda_settings(user, db)


@router.put("/skoda/vehicles/{vehicle_id}/api-key", response_model=SkodaPublicSettingsOut)
async def set_vehicle_api_key(
    vehicle_id: uuid.UUID,
    body: SkodaPublicSettingsUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Save or clear the official API key for one vehicle (encrypted on the car)."""
    import json as _json

    vehicle = await _get_owned_vehicle(vehicle_id, user, db)
    config: dict = {}
    if vehicle.connector_config_encrypted:
        try:
            config = _json.loads(decrypt_field(vehicle.connector_config_encrypted))
        except Exception:
            config = {}
    key = (body.api_key or "").strip()
    if key:
        config["api_key"] = key
    else:
        config.pop("api_key", None)
    vehicle.connector_config_encrypted = encrypt_field(_json.dumps(config))
    await db.commit()
    await db.refresh(user)
    return await _load_skoda_settings(user, db)


@router.post("/skoda/vehicles/{vehicle_id}/mint-key", response_model=SkodaPublicSettingsOut)
async def mint_vehicle_api_key(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an official API key for one vehicle using that car's MyŠkoda login."""
    import json as _json

    from app.services.skoda_auth import SkodaAuthClient
    from app.services.skoda_bff_api import SkodaBFFClient

    vehicle = await _get_owned_vehicle(vehicle_id, user, db)
    config: dict = {}
    if vehicle.connector_config_encrypted:
        try:
            config = _json.loads(decrypt_field(vehicle.connector_config_encrypted))
        except Exception:
            config = {}
    username = config.get("username")
    password = config.get("password")
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="Save MyŠkoda email and password for this car first.",
        )
    vin = decrypt_field(vehicle.vin_encrypted)

    auth = SkodaAuthClient()
    try:
        tokens = await auth.login(username, password)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Could not log in to MyŠkoda for this car. Check email and password.",
        )
    finally:
        await auth.close()

    access = tokens.get("accessToken") or tokens.get("access_token") or ""
    if not access:
        raise HTTPException(status_code=502, detail="MyŠkoda login returned no session.")

    bff = SkodaBFFClient(access)
    try:
        minted = await bff.mint_public_api_key(vin, name="iVDrive")
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Could not create an API key right now. Try again or paste a key from the MyŠkoda app.",
        )
    finally:
        await bff.close()

    config["api_key"] = minted["key"]
    if minted.get("validUntil"):
        config["api_key_expires_at"] = str(minted["validUntil"])
    vehicle.connector_config_encrypted = encrypt_field(_json.dumps(config))
    await db.commit()
    await db.refresh(user)
    return await _load_skoda_settings(user, db)
