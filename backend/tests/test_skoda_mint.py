"""Tests for minting official Public API keys from a Login session."""

from __future__ import annotations

import httpx
import pytest

from app.services.skoda_bff_api import SkodaBFFClient, SkodaBFFError

_RealAsyncClient = httpx.AsyncClient
_BASE = "https://mysmob.api.connect.skoda-auto.cz"


def _client_with_handler(handler) -> SkodaBFFClient:
    transport = httpx.MockTransport(handler)
    real = _RealAsyncClient(
        base_url=_BASE, transport=transport, headers={"authorization": "Bearer at"}
    )
    c = SkodaBFFClient.__new__(SkodaBFFClient)
    c._token = "at"
    c._client = real
    return c


@pytest.mark.asyncio
async def test_mint_key_returns_secret_once():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/public-api-keys"):
            return httpx.Response(
                201,
                json={
                    "id": "abc",
                    "key": "msk_secret",
                    "name": "iVDrive",
                    "validUntil": "2027-04-18T00:00:00Z",
                },
            )
        return httpx.Response(404)

    client = _client_with_handler(handler)
    try:
        out = await client.mint_public_api_key("TESTVIN0000000001")
    finally:
        await client.close()
    assert out["key"] == "msk_secret"
    assert out["id"] == "abc"


@pytest.mark.asyncio
async def test_ensure_returns_none_when_quota_full():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "vehicleKeys": [
                    {"vin": "TESTVIN0000000001", "keysRemaining": 0, "keys": []}
                ]
            },
        )

    client = _client_with_handler(handler)
    try:
        assert await client.ensure_public_api_key("TESTVIN0000000001") is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mint_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "no"})

    client = _client_with_handler(handler)
    try:
        with pytest.raises(SkodaBFFError):
            await client.mint_public_api_key("TESTVIN0000000001")
    finally:
        await client.close()
