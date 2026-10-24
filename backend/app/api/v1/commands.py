import json
import logging
import re
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

from app.services.skoda_commands import CommandUnsupported

try:
    from app.services.skoda_commands_client import SkodaCommandClient
except ImportError:
    SkodaCommandClient = None

logger = logging.getLogger(__name__)

router = APIRouter()


def humanize_command_error(exc: Exception) -> str:
    """User-facing sentence for a failed command — never raw upstream text."""
    if isinstance(exc, CommandUnsupported):
        return str(exc)
    text = str(exc).lower()
    if re.search(r"\b(?:s-?pin|spin|pin)\b", text) and re.search(
        r"invalid|reject|wrong|incorrect", text
    ):
        return "That S-PIN was not accepted. Check it and try again."
    if re.search(r"api\s*key|x-api-key", text):
        return (
            "Your official API key was rejected or expired. "
            "Open Vehicles and save a new API key for this car."
        )
    if re.search(
        r"\b40[13]\b|expired|unauthorized|invalid token|token rejected|not authorized",
        text,
    ):
        return "MyŠkoda Login expired — reconnect in Vehicles."
    if isinstance(exc, (TimeoutError, ConnectionError)) or re.search(
        r"timeout|timed out|unreachable|connection refused|connection reset|connection attempt",
        text,
    ):
        return "Couldn’t reach the car. Try again in a moment."
    if re.search(r"public fallback|http\s*[45]\d\d|bff post|_post", text):
        return "The car refused this command. Try again in a moment."
    return "Command failed. Try again."


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

        # Remote heat/charge/wake means the car is about to be busy — queue a
        # refresh and let the collector flip to Live Sync so a short drive
        # right after is not missed between parked ticks.
        try:
            from app.services.events import publish_vehicle_refresh

            await publish_vehicle_refresh(str(vehicle_id))
        except Exception:
            pass

        return CommandResponse(status="completed", message="Command executed successfully")
    except CommandUnsupported as exc:
        logger.info("Command %s unsupported for %s: %s", command_name, vehicle_id, exc)
        return CommandResponse(status="failed", message=str(exc))
    except Exception as exc:
        # Real upstream error stays in server logs; UI gets a human sentence.
        logger.warning(
            "Command %s failed for vehicle %s: %s",
            command_name,
            vehicle_id,
            exc,
            exc_info=True,
        )
        return CommandResponse(status="failed", message=humanize_command_error(exc))


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
