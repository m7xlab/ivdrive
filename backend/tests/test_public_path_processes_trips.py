"""#204: a successful Public API snapshot must trigger trip/charge processing."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import collector as collector_mod


@pytest.mark.asyncio
async def test_public_snapshot_schedules_trip_processing(monkeypatch):
    dc = collector_mod.DataCollector()
    vid = uuid.uuid4()
    vehicle = SimpleNamespace(
        id=vid, connector_config_encrypted=None, telemetry_source="public", vin_encrypted="v",
        user=SimpleNamespace(skoda_public_api_key_encrypted="k", skoda_public_key_expires_at=None,
                             skoda_public_last_error=None),
    )
    monkeypatch.setattr(collector_mod, "decrypt_field", lambda v: "x")

    client = MagicMock()
    client.get_vehicle_snapshot = AsyncMock(return_value=({}, SimpleNamespace(rate_limit_remaining=1)))
    client.close = AsyncMock()
    monkeypatch.setattr(collector_mod, "SkodaPublicAPIClient", lambda key: client)
    monkeypatch.setattr(
        "app.services.skoda_normalize.snapshot_from_public",
        lambda resp, now, vin: SimpleNamespace(soc=50, is_moving=False),
    )
    monkeypatch.setattr(collector_mod, "parse_expires_at", lambda meta: None)
    monkeypatch.setattr(dc, "_persist_public_snapshot", AsyncMock())

    calls: list[uuid.UUID] = []

    async def fake_process(v):
        calls.append(v)

    monkeypatch.setattr(collector_mod, "process_completed_trips_and_charges", fake_process)
    session = MagicMock()
    session.commit = AsyncMock()

    assert await dc._try_collect_public(session, vehicle) is True
    await asyncio.sleep(0)  # let the background task run
    await asyncio.gather(*list(dc._background_tasks))
    assert calls == [vid]


@pytest.mark.asyncio
async def test_failed_persist_does_not_schedule_processing(monkeypatch):
    dc = collector_mod.DataCollector()
    vehicle = SimpleNamespace(
        id=uuid.uuid4(), connector_config_encrypted=None, telemetry_source="public", vin_encrypted="v",
        user=SimpleNamespace(skoda_public_api_key_encrypted="k", skoda_public_key_expires_at=None,
                             skoda_public_last_error=None),
    )
    monkeypatch.setattr(collector_mod, "decrypt_field", lambda v: "x")
    client = MagicMock()
    client.get_vehicle_snapshot = AsyncMock(return_value=({}, SimpleNamespace(rate_limit_remaining=1)))
    client.close = AsyncMock()
    monkeypatch.setattr(collector_mod, "SkodaPublicAPIClient", lambda key: client)
    monkeypatch.setattr("app.services.skoda_normalize.snapshot_from_public", lambda r, now, vin: SimpleNamespace(soc=1, is_moving=False))
    monkeypatch.setattr(dc, "_persist_public_snapshot", AsyncMock(side_effect=RuntimeError("db")))
    called = []
    monkeypatch.setattr(collector_mod, "process_completed_trips_and_charges", AsyncMock(side_effect=lambda v: called.append(v)))
    session = MagicMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    await dc._try_collect_public(session, vehicle)
    await asyncio.sleep(0)
    assert called == [] and not dc._background_tasks
