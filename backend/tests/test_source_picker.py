"""Source picker policy: Login wins, Public fallback, forced preferences."""

from __future__ import annotations

import pytest

from app.services import vehicle_source as vs
from app.services.skoda_normalize import NormalizedSnapshot


class _Snap(NormalizedSnapshot):
    pass


def _ok(source: str):
    async def fetch(self, vin: str) -> NormalizedSnapshot:
        return NormalizedSnapshot(
            captured_at=vs.datetime.now(vs.UTC), source=source, vin=vin, soc=1.0
        )

    async def close(self) -> None:
        return None

    return fetch


@pytest.mark.asyncio
async def test_auto_prefers_login(monkeypatch):
    async def _close(self):
        return None

    monkeypatch.setattr(vs, "login_source_from_encrypted", lambda t: vs.LoginVehicleSource("tok"))
    monkeypatch.setattr(vs, "public_source_from_encrypted", lambda t: vs.PublicVehicleSource("key"))
    monkeypatch.setattr(vs.LoginVehicleSource, "fetch_snapshot", _ok("login"))
    monkeypatch.setattr(vs.PublicVehicleSource, "fetch_snapshot", _ok("public"))
    monkeypatch.setattr(vs.LoginVehicleSource, "close", _close)
    monkeypatch.setattr(vs.PublicVehicleSource, "close", _close)

    snap, kind, err = await vs.fetch_snapshot_auto(
        vin="TESTVIN0000000001",
        preference="auto",
        api_key_encrypted="enc_pub",
        login_access_encrypted="enc_login",
    )
    assert kind == "login"
    assert snap is not None and snap.soc == 1.0
    assert err is None


@pytest.mark.asyncio
async def test_auto_falls_back_to_public_on_login_error(monkeypatch):
    async def _close(self):
        return None

    async def _fail(self, vin: str):
        raise RuntimeError("login down")

    monkeypatch.setattr(vs, "login_source_from_encrypted", lambda t: vs.LoginVehicleSource("tok"))
    monkeypatch.setattr(vs, "public_source_from_encrypted", lambda t: vs.PublicVehicleSource("key"))
    monkeypatch.setattr(vs.LoginVehicleSource, "fetch_snapshot", _fail)
    monkeypatch.setattr(vs.PublicVehicleSource, "fetch_snapshot", _ok("public"))
    monkeypatch.setattr(vs.LoginVehicleSource, "close", _close)
    monkeypatch.setattr(vs.PublicVehicleSource, "close", _close)

    snap, kind, err = await vs.fetch_snapshot_auto(
        vin="TESTVIN0000000001",
        preference="auto",
        api_key_encrypted="enc_pub",
        login_access_encrypted="enc_login",
    )
    assert kind == "public"
    assert snap is not None
    assert err is not None and "login" in err


@pytest.mark.asyncio
async def test_public_preference_ignores_login(monkeypatch):
    async def _close(self):
        return None

    async def _fail(self, vin: str):
        raise AssertionError("login should not be used")

    monkeypatch.setattr(vs, "login_source_from_encrypted", lambda t: vs.LoginVehicleSource("tok"))
    monkeypatch.setattr(vs, "public_source_from_encrypted", lambda t: vs.PublicVehicleSource("key"))
    monkeypatch.setattr(vs.LoginVehicleSource, "fetch_snapshot", _fail)
    monkeypatch.setattr(vs.PublicVehicleSource, "fetch_snapshot", _ok("public"))
    monkeypatch.setattr(vs.LoginVehicleSource, "close", _close)
    monkeypatch.setattr(vs.PublicVehicleSource, "close", _close)

    snap, kind, err = await vs.fetch_snapshot_auto(
        vin="TESTVIN0000000001",
        preference="public",
        api_key_encrypted="enc_pub",
        login_access_encrypted="enc_login",
    )
    assert kind == "public"
    assert snap is not None


@pytest.mark.asyncio
async def test_no_credentials():
    snap, kind, err = await vs.fetch_snapshot_auto(
        vin="TESTVIN0000000001",
        preference="auto",
        api_key_encrypted=None,
        login_access_encrypted=None,
    )
    assert snap is None and kind is None
    assert err == "no source available"
