import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.models.vehicle import ConnectorSession, UserVehicle
from app.schemas.commands import ClimatizationStartRequest, CommandResponse, UnlockRequest
from app.services.crypto import decrypt_field

try:
    from app.services.skoda_commands_client import SkodaCommandClient
except ImportError:
    SkodaCommandClient = None

router = APIRouter()


async def _get_user_vehicle(
    vehicle_id: uuid.UUID, user: User, db: AsyncSession
) -> UserVehicle:
    result = await db.execute(
        select(UserVehicle).where(
            UserVehicle.id == vehicle_id, UserVehicle.user_id == user.id
        )
    )
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


async def _execute_command(
    vehicle_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    command_name: str,
    **kwargs,
) -> CommandResponse:
    if SkodaCommandClient is None:
        return CommandResponse(
            status="failed", message="Command client not available"
        )

    vehicle = await _get_user_vehicle(vehicle_id, user, db)

    # Decrypt VIN
    try:
        vin = decrypt_field(vehicle.vin_encrypted)
    except Exception:
        return CommandResponse(status="failed", message="Invalid VIN configuration")

    access_token = None
    if vehicle.connector_session and vehicle.connector_session.access_token_encrypted:
        try:
            access_token = decrypt_field(vehicle.connector_session.access_token_encrypted)
        except Exception:
            access_token = None

    public_api_key = None
    if vehicle.connector_config_encrypted:
        try:
            cfg = json.loads(decrypt_field(vehicle.connector_config_encrypted))
            public_api_key = cfg.get("api_key")
        except Exception:
            public_api_key = None
    if not public_api_key and user.skoda_public_api_key_encrypted:
        try:
            public_api_key = decrypt_field(user.skoda_public_api_key_encrypted)
        except Exception:
            public_api_key = None

    if not access_token and not public_api_key:
        return CommandResponse(
            status="failed",
            message="Connect MyŠkoda Login or add an official API key to use remote commands.",
        )

    request_spin = kwargs.pop("spin", None)

    try:
        client = SkodaCommandClient(
            access_token=access_token,
            public_api_key=public_api_key,
            spin=request_spin,
        )
        method = getattr(client, command_name, None)
        if method is None:
            return CommandResponse(
                status="failed", message=f"Unknown command: {command_name}"
            )

        await method(vin, **kwargs)

        return CommandResponse(status="completed", message="Command executed successfully")
    except Exception as exc:
        return CommandResponse(status="failed", message=str(exc))


@router.post(
    "/{vehicle_id}/commands/climatization/start",
    response_model=CommandResponse,
)
async def start_climatization(
    vehicle_id: uuid.UUID,
    body: ClimatizationStartRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _execute_command(
        vehicle_id,
        user,
        db,
        "start_climatization",
        target_temp=body.target_temperature,
    )


@router.post(
    "/{vehicle_id}/commands/climatization/stop",
    response_model=CommandResponse,
)
async def stop_climatization(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _execute_command(vehicle_id, user, db, "stop_climatization")


@router.post(
    "/{vehicle_id}/commands/charging/start",
    response_model=CommandResponse,
)
async def start_charging(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _execute_command(vehicle_id, user, db, "start_charging")


@router.post(
    "/{vehicle_id}/commands/charging/stop",
    response_model=CommandResponse,
)
async def stop_charging(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _execute_command(vehicle_id, user, db, "stop_charging")


@router.post(
    "/{vehicle_id}/commands/lock",
    response_model=CommandResponse,
)
async def lock_vehicle(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _execute_command(vehicle_id, user, db, "lock")


@router.post(
    "/{vehicle_id}/commands/unlock",
    response_model=CommandResponse,
)
async def unlock_vehicle(
    vehicle_id: uuid.UUID,
    body: UnlockRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _execute_command(
        vehicle_id, user, db, "unlock", spin=body.spin
    )


@router.post(
    "/{vehicle_id}/commands/honk-flash",
    response_model=CommandResponse,
)
async def honk_flash(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _execute_command(vehicle_id, user, db, "honk_flash")


@router.post(
    "/{vehicle_id}/commands/wake",
    response_model=CommandResponse,
)
async def wake_vehicle(
    vehicle_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _execute_command(vehicle_id, user, db, "wake")
