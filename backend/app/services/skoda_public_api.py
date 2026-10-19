"""Official MyŠkoda Public API client (X-API-Key).

https://public.api.connect.skoda-auto.cz/docs
Rate limit: 20 requests / hour / VIN — callers must budget (1 snapshot per cycle).

Patterns aligned with mobility-lab-vsb/skoda-public-api (MIT): typed models,
RateLimit-* / X-API-Key-Expires-At headers, problem+json errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.schemas.skoda_public import VehicleResponse

logger = logging.getLogger(__name__)

BETA_URL = "https://public.api.connect.skoda-auto.cz"
TEST_URL = "https://public.test-api.connect.skoda-auto.cz"

# One composite GET per collector cycle (never N includes = N requests).
DEFAULT_INCLUDE = (
    "info",
    "status",
    "charging",
    "odometer",
    "parkingPosition",
    "airConditioning",
    "fuelStatus",
    "operations",
)


class SkodaPublicAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SkodaPublicAuthError(SkodaPublicAPIError):
    """401 invalid/expired key or 403 not bound to VIN."""


class SkodaPublicRateLimitError(SkodaPublicAPIError):
    """429 rate limit or vehicle not accepting requests."""


class SkodaPublicTimeoutError(SkodaPublicAPIError):
    pass


@dataclass
class PublicResponseMeta:
    rate_limit_remaining: int | None = None
    rate_limit_reset: int | None = None
    rate_limit_limit: int | None = None
    api_key_expires_at: str | None = None


class SkodaPublicAPIClient:
    """Thin async client for one vehicle (or many) with a user API key."""

    def __init__(self, api_key: str, base_url: str = BETA_URL, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
        )
        self.last_meta = PublicResponseMeta()

    def _capture_meta(self, headers: httpx.Headers) -> None:
        def _int(name: str) -> int | None:
            raw = headers.get(name)
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        self.last_meta = PublicResponseMeta(
            rate_limit_remaining=_int("RateLimit-Remaining"),
            rate_limit_reset=_int("RateLimit-Reset"),
            rate_limit_limit=_int("RateLimit-Limit"),
            api_key_expires_at=headers.get("X-API-Key-Expires-At"),
        )

    def _raise_for_status(self, resp: httpx.Response) -> dict[str, Any]:
        self._capture_meta(resp.headers)
        if resp.status_code == 401:
            raise SkodaPublicAuthError("Invalid or expired X-API-Key", 401)
        if resp.status_code == 403:
            raise SkodaPublicAuthError("API key not authorized for this vehicle", 403)
        if resp.status_code == 429:
            raise SkodaPublicRateLimitError(
                f"Rate limited (Retry-After={resp.headers.get('Retry-After')})", 429
            )
        if resp.status_code == 404:
            raise SkodaPublicAPIError("Vehicle not found", 404)
        if resp.status_code == 422:
            raise SkodaPublicAPIError("Operation not supported", 422)
        if resp.status_code >= 500:
            raise SkodaPublicAPIError(f"Upstream {resp.status_code}", resp.status_code)
        if resp.status_code >= 400:
            raise SkodaPublicAPIError(f"HTTP {resp.status_code}: {resp.text[:200]}", resp.status_code)
        try:
            return resp.json()
        except Exception as exc:
            raise SkodaPublicAPIError("Invalid JSON response", resp.status_code) from exc

    async def get_vehicle(
        self,
        vin: str,
        include: list[str] | tuple[str, ...] | None = None,
    ) -> tuple[VehicleResponse, PublicResponseMeta]:
        """GET /api/v1/vehicles/{vin} with optional include= (one HTTP request)."""
        params: dict[str, str] = {}
        if include:
            params["include"] = ",".join(include)
        try:
            resp = await self._client.get(f"/api/v1/vehicles/{vin}", params=params or None)
        except httpx.TimeoutException as exc:
            raise SkodaPublicTimeoutError(str(exc)) from exc
        payload = self._raise_for_status(resp)
        return VehicleResponse.model_validate(payload), self.last_meta

    async def get_vehicle_snapshot(self, vin: str) -> tuple[VehicleResponse, PublicResponseMeta]:
        """Collector snapshot: one request with the standard include set."""
        return await self.get_vehicle(vin, include=DEFAULT_INCLUDE)

    async def start_charging(self, vin: str) -> PublicResponseMeta:
        return await self._post(f"/api/v1/vehicles/{vin}/charging/start")

    async def stop_charging(self, vin: str) -> PublicResponseMeta:
        return await self._post(f"/api/v1/vehicles/{vin}/charging/stop")

    async def start_air_conditioning(
        self, vin: str, temperature: float, unit: str = "CELSIUS"
    ) -> PublicResponseMeta:
        body = {
            "targetTemperature": {"value": temperature, "unit": unit},
            "airConditioningWithoutExternalPower": True,
        }
        return await self._post(f"/api/v1/vehicles/{vin}/air-conditioning/start", body)

    async def stop_air_conditioning(self, vin: str) -> PublicResponseMeta:
        return await self._post(f"/api/v1/vehicles/{vin}/air-conditioning/stop")

    async def _post(self, path: str, json_body: dict | None = None) -> PublicResponseMeta:
        try:
            resp = await self._client.post(path, json=json_body)
        except httpx.TimeoutException as exc:
            raise SkodaPublicTimeoutError(str(exc)) from exc
        self._raise_for_status(resp)
        return self.last_meta

    async def close(self) -> None:
        await self._client.aclose()


def parse_expires_at(meta: PublicResponseMeta) -> datetime | None:
    raw = meta.api_key_expires_at
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
