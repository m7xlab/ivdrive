"""HTTP client for the ABRP (Iternio) Telemetry API.

Docs: https://documenter.getpostman.com/view/7396339/SWTK5a8w
Auth (both per ABRP user): ``api_key`` (free Telemetry API key) plus a
per-vehicle ``token`` (Custom connection). Sent as query params or
``Authorization: APIKEY``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.schemas.abrp import (
    AbrpBulkResponse,
    AbrpNextChargeResponse,
    AbrpSendResponse,
)

logger = logging.getLogger(__name__)

ABRP_API_BASE_URL = "https://api.iternio.com/1"


class ABRPAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ABRPAPIClient:
    """Thin async client for one ABRP user/vehicle token.

    Both credentials are per-ABRP-user: ``api_key`` is the free Telemetry API
    key from the user's ABRP account; ``user_token`` is the per-vehicle token
    from ABRP Live Data → Custom connection.
    """

    def __init__(self, user_token: str, api_key: str) -> None:
        self._user_token = user_token
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=ABRP_API_BASE_URL,
            timeout=10.0,
            headers={"Accept": "application/json"},
        )

    def _auth_params(self) -> dict[str, str]:
        return {"api_key": self._api_key}

    def _check(self, resp: httpx.Response) -> dict[str, Any]:
        try:
            payload = resp.json()
        except Exception as exc:
            raise ABRPAPIError(f"Non-JSON response: {resp.text[:200]}", resp.status_code) from exc
        if resp.status_code >= 400:
            raise ABRPAPIError(
                f"HTTP {resp.status_code}: {payload}", resp.status_code
            )
        status = payload.get("status")
        if status and status != "ok":
            errors = payload.get("errors") or payload.get("result")
            raise ABRPAPIError(f"ABRP status={status}: {errors}", resp.status_code)
        return payload

    async def send_tlm(self, tlm: dict[str, Any]) -> AbrpSendResponse:
        """POST /tlm/send — one datapoint for one vehicle."""
        params = self._auth_params()
        params["token"] = self._user_token
        params["tlm"] = json.dumps(tlm, separators=(",", ":"))
        resp = await self._client.post("/tlm/send", params=params)
        payload = self._check(resp)
        return AbrpSendResponse.model_validate(payload)

    async def send_bulk(self, items: list[dict[str, Any]]) -> AbrpBulkResponse:
        """POST /tlm/bulk — items are ``{"token": str, "tlm_list": [tlm, …]}``."""
        params = self._auth_params()
        resp = await self._client.post(
            "/tlm/bulk", params=params, json={"data": items}
        )
        payload = self._check(resp)
        return AbrpBulkResponse.model_validate(payload)

    async def get_next_charge(self) -> AbrpNextChargeResponse:
        params = self._auth_params()
        params["token"] = self._user_token
        resp = await self._client.get("/tlm/get_next_charge", params=params)
        payload = self._check(resp)
        return AbrpNextChargeResponse.model_validate(payload)

    async def get_carmodels_list(self) -> dict[str, str]:
        """Return ``{display_name: typecode}`` for ABRP car models."""
        params = self._auth_params()
        resp = await self._client.get("/tlm/get_carmodels_list", params=params)
        payload = self._check(resp)
        result = payload.get("result") or []
        out: dict[str, str] = {}
        for entry in result:
            if isinstance(entry, dict) and entry:
                # each entry is {name: typecode}
                name, typecode = next(iter(entry.items()))
                out[str(name)] = str(typecode)
        return out

    async def close(self) -> None:
        await self._client.aclose()
