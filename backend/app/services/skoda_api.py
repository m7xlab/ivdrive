from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.schemas.skoda import (
    AirConditioningResponse,
    ChargingResponse,
    ConnectionStatusResponse,
    DrivingRangeResponse,
    GarageResponse,
    MaintenanceResponse,
    PositionResponse,
    VehicleStatusResponse,
)

# Command client lives in skoda_commands_client (no unofficial myskoda library).
from app.services.skoda_commands_client import SkodaCommandClient  # noqa: F401

logger = logging.getLogger(__name__)

_BASE = settings.skoda_base_url


class SkodaAPIClient:
    """Read-only client for telemetry collection using manual HTTP calls.
    
    Kept for backward compatibility with the DataCollector until it is refactored.
    """
    def __init__(self, access_token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "iVDrive/1.0",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def get_garage(self) -> GarageResponse:
        resp = await self._client.get("/api/v2/garage")
        resp.raise_for_status()
        return GarageResponse.model_validate(resp.json())

    async def get_charging(self, vin: str) -> ChargingResponse:
        resp = await self._client.get(f"/api/v1/charging/{vin}")
        resp.raise_for_status()
        return ChargingResponse.model_validate(resp.json())

    async def get_driving_range(self, vin: str) -> DrivingRangeResponse:
        resp = await self._client.get(f"/api/v2/vehicle-status/{vin}/driving-range")
        resp.raise_for_status()
        return DrivingRangeResponse.model_validate(resp.json())

    async def get_vehicle_status(self, vin: str) -> VehicleStatusResponse:
        resp = await self._client.get(f"/api/v2/vehicle-status/{vin}")
        resp.raise_for_status()
        return VehicleStatusResponse.model_validate(resp.json())

    async def get_air_conditioning(self, vin: str) -> AirConditioningResponse:
        resp = await self._client.get(f"/api/v2/air-conditioning/{vin}")
        resp.raise_for_status()
        return AirConditioningResponse.model_validate(resp.json())

    async def get_position(self, vin: str) -> PositionResponse:
        resp = await self._client.get("/api/v1/maps/positions", params={"vin": vin})
        resp.raise_for_status()
        return PositionResponse.model_validate(resp.json())

    async def get_maintenance(self, vin: str) -> MaintenanceResponse:
        resp = await self._client.get(f"/api/v3/vehicle-maintenance/vehicles/{vin}/report")
        resp.raise_for_status()
        return MaintenanceResponse.model_validate(resp.json())

    async def get_connection_status(self, vin: str) -> ConnectionStatusResponse:
        resp = await self._client.get(f"/api/v2/connection-status/{vin}/readiness")
        resp.raise_for_status()
        return ConnectionStatusResponse.model_validate(resp.json())

    async def get_single_trips(self, vin: str) -> dict:
        """MyŠkoda server-side trip history (journeys with stops, ~60 days). Read-only."""
        resp = await self._client.get(f"/api/v1/trip-statistics/{vin}/single-trips")
        resp.raise_for_status()
        return resp.json()

    async def get_warning_lights(self, vin: str) -> dict:
        resp = await self._client.get(f"/api/v1/vehicle-health-report/warning-lights/{vin}")
        resp.raise_for_status()
        return resp.json()

    async def get_garage_vehicle(self, vin: str) -> dict:
        resp = await self._client.get(f"/api/v2/garage/vehicles/{vin}")
        resp.raise_for_status()
        return resp.json()

    async def get_vehicle_renders(self, vin: str) -> dict:
        resp = await self._client.get(f"/api/v1/vehicle-information/{vin}/renders")
        resp.raise_for_status()
        return resp.json()

    # Legacy command methods removed/deprecated in favor of SkodaCommandClient
    # to avoid confusion.

    async def close(self) -> None:
        await self._client.aclose()

