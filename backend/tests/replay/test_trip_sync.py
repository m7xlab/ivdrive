"""MyŠkoda single-trips -> missing iVDrive trips (synthetic payload shaped like the real API)."""

import pytest

from .conftest import *  # noqa: F401,F403  (fixtures)
from .replay import t, trips
from app.models.telemetry import Trip
from app.services.trip_sync import parse_legs, sync_legs


def _journey():
    """Oct 27 case: one Skoda journey, 3 legs (3 + 5 + 2 km), 42829 -> 42839."""
    return {"dailyTrips": [{"date": "2026-10-28", "trips": [{
        "id": "x", "startMileageInKm": 42829, "endMileageInKm": 42839, "mileageInKm": 10,
        "waypoints": [
            {"coordinates": {"latitude": 54.69, "longitude": 25.26}, "departureStateOfChargeInPercent": 70,
             "departureTime": "2026-10-28T14:51:49Z", "distanceToNextWaypointInKm": 3},
            {"coordinates": {"latitude": 54.68, "longitude": 25.25}, "arrivalStateOfChargeInPercent": 68,
             "arrivalTime": "2026-10-28T15:09:16Z", "departureStateOfChargeInPercent": 68,
             "departureTime": "2026-10-28T15:19:12Z", "distanceToNextWaypointInKm": 5},
            {"coordinates": {"latitude": 54.65, "longitude": 25.27}, "arrivalStateOfChargeInPercent": 65,
             "arrivalTime": "2026-10-28T15:34:54Z", "departureStateOfChargeInPercent": 65,
             "departureTime": "2026-10-28T15:35:35Z", "distanceToNextWaypointInKm": 2},
            {"coordinates": {"latitude": 54.64, "longitude": 25.25}, "arrivalStateOfChargeInPercent": 64,
             "arrivalTime": "2026-10-28T15:40:09Z"},
        ]}]}]}


def test_parse_legs_splits_journey_at_stops_and_absorbs_rounding():
    legs = parse_legs(_journey())
    assert [(l.start_odometer, l.end_odometer) for l in legs] == [(42829, 42832), (42832, 42837), (42837, 42839)]
    assert legs[0].start_soc == 70 and legs[0].end_soc == 68 and legs[1].start.minute == 19


def test_parse_skips_malformed_journeys():
    bad = {"dailyTrips": [{"trips": [{"startMileageInKm": 1, "endMileageInKm": 2, "waypoints": [{"departureTime": "x"}]},
                                      {"startMileageInKm": 1, "waypoints": []}]}]}
    assert parse_legs(bad) == []


@pytest.mark.asyncio
async def test_missing_middle_leg_is_inserted_and_recorded_trips_untouched(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("14:51"), end_date=t("15:09"),
                   start_odometer=42829, end_odometer=42832, distance_km=3))
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("15:33"), end_date=t("15:42"),
                   start_odometer=42836, end_odometer=42839, distance_km=3))
        await s.commit()
    async with replay_sessionmaker() as s:
        res = await sync_legs(s, vehicle_id, parse_legs(_journey()))
        await s.commit()
    assert (res.inserted, res.skipped_covered, res.km_added) == (1, 2, 5.0)
    got = await trips(replay_sessionmaker, vehicle_id)
    assert [(x.start_odometer, x.distance_km, x.data_quality) for x in got] == [
        (42829, 3, None), (42832, 5, "skoda_history"), (42836, 3, None)]
    assert got[1].kwh_consumed == pytest.approx(0.03 * 77)  # 68 -> 65 %


@pytest.mark.asyncio
async def test_sync_is_idempotent_and_dry_run_writes_nothing(replay_sessionmaker, vehicle_id):
    legs = parse_legs(_journey())
    async with replay_sessionmaker() as s:
        res = await sync_legs(s, vehicle_id, legs, apply=False)
        await s.rollback()
    assert res.inserted == 3 and await trips(replay_sessionmaker, vehicle_id) == []
    for _ in range(2):
        async with replay_sessionmaker() as s:
            await sync_legs(s, vehicle_id, legs)
            await s.commit()
    assert len(await trips(replay_sessionmaker, vehicle_id)) == 3


@pytest.mark.asyncio
async def test_zero_km_trip_gets_distance_from_matching_leg(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("15:19"), end_date=t("15:34"),
                   start_odometer=42832, end_odometer=42832, distance_km=0))
        await s.commit()
    async with replay_sessionmaker() as s:
        res = await sync_legs(s, vehicle_id, parse_legs(_journey()))
        await s.commit()
    got = {x.start_odometer: x for x in await trips(replay_sessionmaker, vehicle_id)}
    assert res.distance_filled == 1 and got[42832].distance_km == 5 and got[42832].end_odometer == 42837


@pytest.mark.asyncio
async def test_recorded_trip_is_enriched_only_where_values_are_missing(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("14:51"), end_date=t("15:09"),
                   start_odometer=42829, end_odometer=42832, distance_km=3,
                   start_soc=71, end_soc=None, kwh_consumed=None, start_lat=None))
        await s.commit()
    async with replay_sessionmaker() as s:
        res = await sync_legs(s, vehicle_id, parse_legs(_journey())[:1])
        await s.commit()
    (x,) = await trips(replay_sessionmaker, vehicle_id)
    assert res.enriched == 1
    assert x.start_soc == 71            # measured value kept (Skoda says 70)
    assert x.end_soc == 68 and x.kwh_consumed == pytest.approx(0.02 * 77) and x.start_lat == 54.69
    assert x.distance_km == 3 and x.data_quality is None


@pytest.mark.asyncio
async def test_trip_spanning_several_legs_is_not_enriched(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("14:51"), end_date=t("15:40"),
                   start_odometer=42829, end_odometer=42839, distance_km=10, kwh_consumed=None))
        await s.commit()
    async with replay_sessionmaker() as s:
        res = await sync_legs(s, vehicle_id, parse_legs(_journey()))
        await s.commit()
    assert res.enriched == 0 and (await trips(replay_sessionmaker, vehicle_id))[0].kwh_consumed is None


def _runner_env(monkeypatch, replay_sessionmaker, payload_or_exc):
    """Wire run_trip_sync to the scratch DB with a fake Skoda client."""
    import app.database as dbmod
    from app.services import trip_sync, skoda_lifecycle, skoda_api, crypto

    monkeypatch.setattr(dbmod, "async_session", replay_sessionmaker)
    monkeypatch.setattr(crypto, "decrypt_field", lambda v: "VIN")

    class FakeLifecycle:
        def __init__(self, s): pass
        async def ensure_valid_token(self, cs, u, p=None, **kw): return "tok"

    class FakeClient:
        calls = 0
        def __init__(self, token): pass
        async def get_single_trips(self, vin):
            FakeClient.calls += 1
            if isinstance(payload_or_exc, Exception):
                raise payload_or_exc
            return payload_or_exc
        async def close(self): pass

    monkeypatch.setattr(skoda_lifecycle, "SkodaTokenLifecycle", FakeLifecycle)
    monkeypatch.setattr(skoda_api, "SkodaAPIClient", FakeClient)
    trip_sync._failures.clear()
    return trip_sync, FakeClient


async def _login_vehicle(replay_sessionmaker, vehicle_id):
    from app.models.vehicle import ConnectorSession
    async with replay_sessionmaker() as s:
        s.add(ConnectorSession(user_vehicle_id=vehicle_id, status="ok"))
        await s.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [RuntimeError("HTTP 404"), {"unexpected": "shape"}, ["not", "a", "dict"]])
async def test_skoda_api_disabled_or_changed_backs_off_and_leaves_data_alone(
    replay_sessionmaker, vehicle_id, monkeypatch, bad
):
    await _login_vehicle(replay_sessionmaker, vehicle_id)
    sync, Fake = _runner_env(monkeypatch, replay_sessionmaker, bad)
    out = await sync.run_trip_sync(pause_s=0)
    assert out == {} and vehicle_id in sync._failures and await trips(replay_sessionmaker, vehicle_id) == []
    assert Fake.calls == 1
    await sync.run_trip_sync(pause_s=0)          # inside the back-off window: no second request
    assert Fake.calls == 1


@pytest.mark.asyncio
async def test_sync_recovers_by_itself_when_skoda_answers_again(replay_sessionmaker, vehicle_id, monkeypatch):
    from datetime import datetime, timedelta, timezone
    await _login_vehicle(replay_sessionmaker, vehicle_id)
    sync, Fake = _runner_env(monkeypatch, replay_sessionmaker, _journey())
    sync._failures[vehicle_id] = (3, datetime.now(timezone.utc) - timedelta(minutes=1))  # back-off expired
    out = await sync.run_trip_sync(pause_s=0)
    assert out[str(vehicle_id)].inserted == 3 and vehicle_id not in sync._failures
