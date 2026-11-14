"""A remote command Škoda answers with an error can still have been carried out (climate start: BFF 400
and Public 500 while the car heated). The API checks the car before saying 'refused'."""
import httpx
import pytest

from app.api.v1 import commands as cmd
from app.services import skoda_api, skoda_bff_api


class _AC:
    def __init__(self, state): self.state = state


def _login_client(monkeypatch, state):
    class Fake:
        def __init__(self, token): pass
        async def get_air_conditioning(self, vin): return _AC(state)
        async def close(self): pass
    monkeypatch.setattr(skoda_api, "SkodaAPIClient", Fake)


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(cmd, "_READBACK_DELAY_S", 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("state,expected", [("HEATING", "heating is on"), ("COOLING", "cooling is on"), ("VENTILATION", "ventilation is on"),
                                            ("OFF", None), (None, None)])
async def test_start_is_a_success_only_when_the_car_reports_climatisation_on(monkeypatch, state, expected):
    _login_client(monkeypatch, state)
    assert await cmd._observed_state("start_climatization", "VIN", "tok", None) == expected


@pytest.mark.asyncio
async def test_stop_is_a_success_only_when_the_car_reports_off(monkeypatch):
    _login_client(monkeypatch, "OFF")
    assert await cmd._observed_state("stop_climatization", "VIN", "tok", None) == "climatisation is off"
    _login_client(monkeypatch, "HEATING")
    assert await cmd._observed_state("stop_climatization", "VIN", "tok", None) is None


@pytest.mark.asyncio
async def test_other_commands_and_unreadable_state_are_never_turned_into_success(monkeypatch):
    class Broken:
        def __init__(self, token): pass
        async def get_air_conditioning(self, vin): raise RuntimeError("boom")
        async def close(self): pass
    monkeypatch.setattr(skoda_api, "SkodaAPIClient", Broken)
    assert await cmd._observed_state("start_climatization", "VIN", "tok", None) is None
    assert await cmd._observed_state("lock_vehicle", "VIN", "tok", None) is None


@pytest.mark.asyncio
async def test_public_api_snapshot_is_used_when_there_is_no_login_token(monkeypatch):
    from app.services import skoda_public_api as pub

    class Snap:
        air_conditioning = _AC("HEATING")

    class Fake:
        def __init__(self, key): pass
        async def get_vehicle_snapshot(self, vin): return Snap(), None
        async def close(self): pass
    monkeypatch.setattr(pub, "SkodaPublicAPIClient", Fake)
    assert await cmd._observed_state("start_climatization", "VIN", None, "key") == "heating is on"


@pytest.mark.asyncio
async def test_bff_post_error_carries_skodas_reason_without_credentials():
    def handler(req):
        return httpx.Response(400, json={"error": "targetTemperature.unit is not allowed"})
    c = skoda_bff_api.SkodaBFFClient.__new__(skoda_bff_api.SkodaBFFClient)
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://x")
    with pytest.raises(skoda_bff_api.SkodaBFFError) as e:
        await c._post("/api/v2/air-conditioning/VIN/start", {"a": 1})
    assert "HTTP 400" in str(e.value) and "targetTemperature.unit" in str(e.value)
