"""MyŠkoda BFF (mysmob) telemetry + commands client. Private API — optional Login source."""

from __future__ import annotations

import logging

import httpx

from app.services.skoda_bff_auth import MYSMOB_BASE, bearer_headers

logger = logging.getLogger(__name__)


class SkodaBFFError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SkodaBFFClient:
    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._client = httpx.AsyncClient(
            base_url=MYSMOB_BASE,
            timeout=30.0,
            headers=bearer_headers(access_token),
        )

    async def _get(self, path: str) -> dict:
        resp = await self._client.get(path)
        if resp.status_code >= 400:
            raise SkodaBFFError(f"BFF GET {path} -> HTTP {resp.status_code}", resp.status_code)
        return resp.json()

    async def _post(self, path: str, json_body: dict | None = None) -> dict | None:
        resp = await self._client.post(path, json=json_body or {})
        if resp.status_code >= 400:
            raise SkodaBFFError(f"BFF POST {path} -> HTTP {resp.status_code}", resp.status_code)
        if not resp.content:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    async def _put(self, path: str, json_body: dict | None = None) -> dict | None:
        resp = await self._client.put(path, json=json_body or {})
        if resp.status_code >= 400:
            raise SkodaBFFError(f"BFF PUT {path} -> HTTP {resp.status_code}", resp.status_code)
        if not resp.content:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    # ── telemetry ──────────────────────────────────────────────────────────

    async def get_charging(self, vin: str) -> dict:
        return await self._get(f"/api/v1/charging/{vin}")

    async def get_vehicle_status(self, vin: str) -> dict:
        return await self._get(f"/api/v2/vehicle-status/{vin}")

    async def get_driving_range(self, vin: str) -> dict:
        return await self._get(f"/api/v2/vehicle-status/{vin}/driving-range")

    async def get_parking(self, vin: str) -> dict:
        return await self._get(f"/api/v3/maps/positions/vehicles/{vin}/parking")

    async def get_readiness(self, vin: str) -> dict:
        return await self._get(f"/api/v2/connection-status/{vin}/readiness")

    async def get_vehicle_info(self, vin: str) -> dict:
        return await self._get(f"/api/v1/vehicle-information/{vin}")

    async def get_maintenance(self, vin: str) -> dict:
        return await self._get(f"/api/v3/vehicle-maintenance/vehicles/{vin}")

    # ── commands ───────────────────────────────────────────────────────────

    async def wake(self, vin: str) -> None:
        await self._post(f"/api/v1/vehicle-wakeup/{vin}")

    async def lock(self, vin: str) -> None:
        await self._post(f"/api/v1/vehicle-access/{vin}/lock")

    async def unlock(self, vin: str) -> None:
        await self._post(f"/api/v1/vehicle-access/{vin}/unlock")

    async def start_charging(self, vin: str) -> None:
        await self._post(f"/api/v1/charging/{vin}/start")

    async def stop_charging(self, vin: str) -> None:
        await self._post(f"/api/v1/charging/{vin}/stop")

    async def set_charge_limit(self, vin: str, percent: int) -> None:
        await self._put(
            f"/api/v1/charging/{vin}/set-charge-limit",
            {"targetStateOfChargeInPercent": int(percent)},
        )

    async def set_charge_mode(self, vin: str, mode: str) -> None:
        await self._put(
            f"/api/v1/charging/{vin}/set-charge-mode",
            {"chargeMode": mode},
        )

    async def start_climate(self, vin: str, temp_c: float) -> None:
        await self._post(
            f"/api/v2/air-conditioning/{vin}/start",
            {"targetTemperature": {"value": float(temp_c), "unit": "CELSIUS"}},
        )

    async def stop_climate(self, vin: str) -> None:
        await self._post(f"/api/v2/air-conditioning/{vin}/stop")

    # ── public API key minting ─────────────────────────────────────────────

    async def list_public_api_keys(self) -> dict:
        return await self._get("/api/v2/public-api-keys")

    async def mint_public_api_key(self, vin: str, name: str = "iVDrive") -> dict:
        data = await self._post("/api/v2/public-api-keys", {"name": name, "vin": vin})
        if not data or not data.get("key"):
            raise SkodaBFFError("mint returned no key")
        return data

    async def delete_public_api_key(self, key_id: str) -> None:
        resp = await self._client.delete(f"/api/v2/public-api-keys/{key_id}")
        if resp.status_code >= 400:
            raise SkodaBFFError(f"delete key -> HTTP {resp.status_code}", resp.status_code)

    async def ensure_public_api_key(self, vin: str) -> str | None:
        """Return an existing valid key secret if listed… secrets are not listed.

        Inventory has no secrets — mint a new key when none named iVDrive exists
        and quota remains. Caller should persist the secret on first mint.
        """
        inv = await self.list_public_api_keys()
        vehicles = inv.get("vehicleKeys") or []
        entry = next(
            (v for v in vehicles if (v.get("vin") or "").upper() == vin.upper()),
            None,
        )
        if entry is not None:
            keys = entry.get("keys") or []
            for k in keys:
                if (k.get("name") or "") == "iVDrive" and k.get("status") == "VALID":
                    # secret is not returned by list; caller must use stored key
                    return None
            if int(entry.get("keysRemaining") or 0) <= 0:
                return None
        minted = await self.mint_public_api_key(vin)
        return minted.get("key")

    async def close(self) -> None:
        await self._client.aclose()
