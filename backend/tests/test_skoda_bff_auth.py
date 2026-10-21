"""Tests for MyŠkoda BFF auth token exchange/refresh (HTTP mocked)."""

from __future__ import annotations

import httpx
import pytest

from app.services.skoda_bff_auth import (
    BFFAuthError,
    BFFAuthExpired,
    exchange_tokens,
    refresh_tokens,
)


_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return _RealAsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_exchange_tokens_posts_connect_token_type(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={"accessToken": "at", "refreshToken": "rt", "idToken": "it"},
        )

    def fake_client(*args, **kwargs):
        return _mock_client(handler)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    out = await exchange_tokens(code="abc", verifier="ver")
    assert out["accessToken"] == "at"
    assert "exchange-authorization-code" in seen["url"]
    assert "tokenType=CONNECT" in seen["url"]
    assert b"verifier" in seen["body"]


@pytest.mark.asyncio
async def test_exchange_tokens_missing_access_raises(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"refreshToken": "rt"})

    def fake_client(*args, **kwargs):
        return _mock_client(handler)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    with pytest.raises(BFFAuthError):
        await exchange_tokens(code="abc", verifier="ver")


@pytest.mark.asyncio
async def test_refresh_tokens(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, json={"accessToken": "at2", "refreshToken": "rt2"})

    def fake_client(*args, **kwargs):
        return _mock_client(handler)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    out = await refresh_tokens("rt")
    assert out["accessToken"] == "at2"
    assert "refresh-token" in seen["url"]
    assert b"token" in seen["body"]


@pytest.mark.asyncio
async def test_refresh_tokens_http_error_is_expired(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid"})

    def fake_client(*args, **kwargs):
        return _mock_client(handler)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    with pytest.raises(BFFAuthExpired):
        await refresh_tokens("rt")
