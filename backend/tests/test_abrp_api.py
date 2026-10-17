"""Unit tests for the ABRP HTTP client (mocked transport, no real network)."""

import json

import httpx
import pytest

from app.services.abrp_api import ABRPAPIError, ABRPAPIClient


def _client_with_handler(handler) -> tuple[ABRPAPIClient, httpx.AsyncClient]:
    client = ABRPAPIClient("user-token-abc", "user-api-key-xyz")
    transport = httpx.MockTransport(handler)
    # Swap the underlying client's transport
    client._client = httpx.AsyncClient(
        base_url="https://api.iternio.com/1",
        timeout=10.0,
        transport=transport,
    )
    return client, client._client


@pytest.mark.asyncio
async def test_send_tlm_builds_query_with_api_key_token_and_tlm():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"status": "ok", "result": {}})

    client, _ = _client_with_handler(handler)
    try:
        tlm = {"utc": 1700000000, "soc": 80.0, "power": -11.0}
        resp = await client.send_tlm(tlm)
        assert resp.status == "ok"
        params = captured["params"]
        assert params.get("token") == "user-token-abc"
        assert params.get("api_key") == "user-api-key-xyz"
        assert json.loads(params["tlm"]) == tlm
        assert "/tlm/send" in captured["url"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_send_tlm_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "errors": ["bad token"]})

    client, _ = _client_with_handler(handler)
    try:
        with pytest.raises(ABRPAPIError):
            await client.send_tlm({"utc": 1, "soc": 1.0})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_send_tlm_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": "error"})

    client, _ = _client_with_handler(handler)
    try:
        with pytest.raises(ABRPAPIError):
            await client.send_tlm({"utc": 1, "soc": 1.0})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_send_bulk_posts_data_array():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "ok"})

    client, _ = _client_with_handler(handler)
    try:
        items = [
            {"token": "t1", "tlm_list": [{"utc": 1, "soc": 50.0}]},
            {"token": "t2", "tlm_list": [{"utc": 1, "soc": 60.0}]},
        ]
        await client.send_bulk(items)
        assert captured["path"].endswith("/tlm/bulk")
        assert captured["body"]["data"] == items
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_next_charge_parses_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "result": {"next_charge": 86.0}})

    client, _ = _client_with_handler(handler)
    try:
        resp = await client.get_next_charge()
        assert resp.result is not None
        assert resp.result.next_charge == 86.0
    finally:
        await client.close()
