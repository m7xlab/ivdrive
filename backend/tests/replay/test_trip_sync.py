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
    assert (res.inserted, res.rewritten) == (1, 1)   # the 15:33 trip is leg 3: Škoda starts it at 42837, not 42836
    got = await trips(replay_sessionmaker, vehicle_id)
    assert [(x.start_odometer, x.distance_km, x.data_quality) for x in got] == [
        (42829, 3, None), (42832, 5, "skoda_history"), (42837, 2, "skoda_history")]
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
async def test_recorded_trip_takes_skodas_soc_energy_and_positions_but_keeps_distance(replay_sessionmaker, vehicle_id):
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
    assert x.start_soc == 70            # Škoda's value replaces the late poll's reading (71)
    assert x.end_soc == 68 and x.kwh_consumed == pytest.approx(0.02 * 77) and x.start_lat == 54.69
    assert x.distance_km == 3 and x.data_quality is None


@pytest.mark.asyncio
async def test_trip_spanning_several_legs_is_split_not_double_counted(replay_sessionmaker, vehicle_id):
    """Polling never saw the stops: one 10 km row for a journey Skoda records as 3 legs."""
    async with replay_sessionmaker() as s:
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("14:51"), end_date=t("15:40"),
                   start_odometer=42829, end_odometer=42839, distance_km=10))
        await s.commit()
    async with replay_sessionmaker() as s:
        res = await sync_legs(s, vehicle_id, parse_legs(_journey()))
        await s.commit()
    got = await trips(replay_sessionmaker, vehicle_id)
    assert (res.rewritten, res.inserted, res.removed) == (1, 2, 0)
    assert [(x.start_odometer, x.end_odometer) for x in got] == [(42829, 42832), (42832, 42837), (42837, 42839)]
    assert sum(x.distance_km for x in got) == 10


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


# ── v1.3.7: no double counting (#210, duplicates in #209/#204) ─────────────────────────

def _drive(dep: str, arr: str, s_odo: int, e_odo: int, day: str = "2026-10-29") -> dict:
    """One Skoda journey with a single leg."""
    return {"id": f"{day}-{dep}", "startMileageInKm": s_odo, "endMileageInKm": e_odo, "waypoints": [
        {"coordinates": {"latitude": 47.5, "longitude": 19.0}, "departureStateOfChargeInPercent": 80,
         "departureTime": f"{day}T{dep}:00Z", "distanceToNextWaypointInKm": e_odo - s_odo},
        {"coordinates": {"latitude": 47.6, "longitude": 19.1}, "arrivalStateOfChargeInPercent": 78,
         "arrivalTime": f"{day}T{arr}:00Z"}]}


def _payload(*drives: dict) -> dict:
    return {"dailyTrips": [{"trips": list(drives)}]}


def _issue_210_payload() -> dict:
    return _payload(_drive("07:45", "07:56", 1000, 1007), _drive("08:06", "08:15", 1007, 1013),
                    _drive("08:24", "08:52", 1013, 1035))


def _tr(vid, start, end, so, eo, quality=None, day="2026-10-29"):
    from datetime import datetime, timezone
    f = lambda hhmm: datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=timezone.utc)
    return Trip(user_vehicle_id=vid, start_date=f(start), end_date=f(end), start_odometer=so,
                end_odometer=eo, distance_km=eo - so, data_quality=quality)


async def _sync(sm, vid, payload, apply=True):
    async with sm() as s:
        res = await sync_legs(s, vid, parse_legs(payload), apply=apply)
        if apply:
            await s.commit()
        else:
            await s.rollback()
    return res


def _summary(rows):
    return [(int(x.start_odometer), int(x.end_odometer)) for x in rows], sum(x.distance_km or 0 for x in rows)


@pytest.mark.asyncio
async def test_210_after_v136_merged_13km_plus_inserted_7km_becomes_three_trips_35km(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        s.add_all([
            _tr(vehicle_id, "07:45", "07:56", 1000, 1007, "skoda_history"),   # inserted by v1.3.6
            _tr(vehicle_id, "08:06", "08:25", 1000, 1013),                    # polled, floor made it 13 km
            _tr(vehicle_id, "08:24", "08:52", 1013, 1035),
        ])
        await s.commit()
    res = await _sync(replay_sessionmaker, vehicle_id, _issue_210_payload())
    rows = await trips(replay_sessionmaker, vehicle_id)
    assert _summary(rows) == ([(1000, 1007), (1007, 1013), (1013, 1035)], 35)
    assert (res.rewritten, res.removed, res.inserted) == (1, 0, 0)


@pytest.mark.asyncio
async def test_210_fresh_install_splits_merged_trip_and_adds_missing_leg(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        s.add_all([_tr(vehicle_id, "08:06", "08:25", 1000, 1013), _tr(vehicle_id, "08:24", "08:52", 1013, 1035)])
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _issue_210_payload())
    assert _summary(await trips(replay_sessionmaker, vehicle_id)) == ([(1000, 1007), (1007, 1013), (1013, 1035)], 35)


@pytest.mark.asyncio
async def test_oct28_duplicate_3km_and_4km_fragment_next_to_21km_are_cleaned(replay_sessionmaker, vehicle_id):
    d = "2026-10-28"
    async with replay_sessionmaker() as s:
        s.add_all([
            _tr(vehicle_id, "08:37", "08:43", 39914, 39917, day=d),                    # polled, late
            _tr(vehicle_id, "08:32", "08:39", 39914, 39917, "skoda_history", day=d),   # v1.3.6 duplicate
            _tr(vehicle_id, "09:31", "09:43", 39934, 39938, day=d),                    # 4 km fragment
            _tr(vehicle_id, "09:06", "09:34", 39917, 39938, "skoda_history", day=d),   # 21 km inserted
        ])
        await s.commit()
    payload = _payload(_drive("08:32", "08:39", 39914, 39917, d), _drive("09:06", "09:34", 39917, 39938, d))
    res = await _sync(replay_sessionmaker, vehicle_id, payload)
    rows = await trips(replay_sessionmaker, vehicle_id)
    assert _summary(rows) == ([(39914, 39917), (39917, 39938)], 24)
    assert res.removed == 2 and all(x.data_quality == "skoda_history" for x in rows)


@pytest.mark.asyncio
async def test_oct28_fresh_state_fragment_is_folded_into_the_leg(replay_sessionmaker, vehicle_id):
    d = "2026-10-28"
    async with replay_sessionmaker() as s:
        s.add(_tr(vehicle_id, "09:31", "09:43", 39934, 39938, day=d))
        await s.commit()
    res = await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("09:06", "09:34", 39917, 39938, d)))
    assert _summary(await trips(replay_sessionmaker, vehicle_id)) == ([(39917, 39938)], 21)
    assert (res.rewritten, res.inserted, res.removed) == (1, 0, 0)


@pytest.mark.asyncio
async def test_second_run_changes_nothing_and_dry_run_writes_nothing(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        s.add_all([_tr(vehicle_id, "08:06", "08:25", 1000, 1013), _tr(vehicle_id, "08:24", "08:52", 1013, 1035)])
        await s.commit()
    before = _summary(await trips(replay_sessionmaker, vehicle_id))
    dry = await _sync(replay_sessionmaker, vehicle_id, _issue_210_payload(), apply=False)
    assert dry.rewritten == 1 and _summary(await trips(replay_sessionmaker, vehicle_id)) == before
    await _sync(replay_sessionmaker, vehicle_id, _issue_210_payload())
    again = await _sync(replay_sessionmaker, vehicle_id, _issue_210_payload())
    assert (again.inserted, again.rewritten, again.removed, again.distance_filled) == (0, 0, 0, 0)
    assert _summary(await trips(replay_sessionmaker, vehicle_id))[1] == 35


@pytest.mark.asyncio
async def test_unrelated_trips_in_and_outside_the_window_are_untouched(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        s.add_all([
            _tr(vehicle_id, "08:06", "08:15", 1007, 1013),                       # same as a leg
            _tr(vehicle_id, "12:00", "12:30", 2000, 2010),                       # same day, other odometer
            _tr(vehicle_id, "08:00", "08:20", 500, 510, day="2026-08-01"),       # months before Skoda's window
        ])
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _issue_210_payload())
    rows = {(int(x.start_odometer), int(x.end_odometer)) for x in await trips(replay_sessionmaker, vehicle_id)}
    assert {(2000, 2010), (500, 510)} <= rows


# ── v1.3.9 (#213): Škoda is authoritative for a matched trip ───────────────────────────

def _legs_213_afternoon() -> dict:
    """Nov 2 afternoon: 21 + 3 + 4 = 28 km, stops at Tófalva and Nádas."""
    return _payload(
        _drive("15:58", "16:16", 2000, 2021, "2026-11-02"),
        _drive("16:38", "16:47", 2021, 2024, "2026-11-02"),
        _drive("18:01", "18:09", 2024, 2028, "2026-11-02"),
    )


@pytest.mark.asyncio
async def test_213_overlong_trip_that_swallowed_the_next_leg_is_cut_back(replay_sessionmaker, vehicle_id):
    """v1.3.8: a polled 24 km trip (21 + the next 3 km leg) counted as 'same' as the 21 km leg."""
    d = "2026-11-02"
    async with replay_sessionmaker() as s:
        s.add_all([
            _tr(vehicle_id, "16:47", "16:50", 2000, 2024, day=d),                    # polled, late, 24 km
            _tr(vehicle_id, "16:38", "16:47", 2021, 2024, "skoda_history", day=d),   # the 3 km leg
            _tr(vehicle_id, "18:01", "18:09", 2024, 2028, day=d),
        ])
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _legs_213_afternoon())
    rows = await trips(replay_sessionmaker, vehicle_id)
    assert _summary(rows) == ([(2000, 2021), (2021, 2024), (2024, 2028)], 28)
    assert rows[0].start_date.strftime("%H:%M") == "15:58"          # Škoda's departure, not the late poll


@pytest.mark.asyncio
async def test_213_matched_trip_takes_skoda_times_and_positions(replay_sessionmaker, vehicle_id):
    d = "2026-11-02"
    async with replay_sessionmaker() as s:
        m = _tr(vehicle_id, "23:41", "23:52", 3000, 3038, day=d)       # detected 25 min late
        m.start_lat, m.start_lon, m.end_lat, m.end_lon = 47.1, 19.9, 47.2, 19.8      # stale 'parked' position
        s.add(m)
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("23:16", "23:47", 3000, 3038, d)))
    (row,) = await trips(replay_sessionmaker, vehicle_id)
    assert row.start_date.strftime("%H:%M") == "23:16" and row.end_date.strftime("%H:%M") == "23:47"
    assert (row.start_lat, row.start_lon) == (47.5, 19.0) and (row.end_lat, row.end_lon) == (47.6, 19.1)
    assert row.data_quality == "skoda_history"


def _journey_with_energy() -> dict:
    """38 + 2 km, 8.0 kWh in total; SoC only moves in whole percent (80 -> 72 -> 71)."""
    return {"dailyTrips": [{"trips": [{
        "id": "j", "startMileageInKm": 3000, "endMileageInKm": 3040, "mileageInKm": 40, "electricConsumption": 8.0,
        "waypoints": [
            {"coordinates": {"latitude": 47.5, "longitude": 19.0}, "departureStateOfChargeInPercent": 80,
             "departureTime": "2026-11-02T23:16:00Z", "distanceToNextWaypointInKm": 38},
            {"coordinates": {"latitude": 47.4, "longitude": 19.2}, "arrivalStateOfChargeInPercent": 72,
             "arrivalTime": "2026-11-02T23:47:00Z", "departureStateOfChargeInPercent": 72,
             "departureTime": "2026-11-03T00:08:00Z", "distanceToNextWaypointInKm": 2},
            {"coordinates": {"latitude": 47.4, "longitude": 19.3}, "arrivalStateOfChargeInPercent": 71,
             "arrivalTime": "2026-11-03T00:12:00Z"}]}]}]}


@pytest.mark.asyncio
async def test_213_short_leg_energy_is_not_one_whole_percent(replay_sessionmaker, vehicle_id):
    """2 km at '1 % = 0.77 kWh' showed 38.5 kWh/100km; use the journey's own energy for short legs."""
    await _sync(replay_sessionmaker, vehicle_id, _journey_with_energy())
    long_leg, short_leg = await trips(replay_sessionmaker, vehicle_id)
    assert long_leg.kwh_consumed == pytest.approx(0.08 * 77)                 # 8 points of SoC: usable
    assert short_leg.kwh_consumed == pytest.approx(8.0 * 2 / 40)            # 0.4 kWh = 20 kWh/100km


def test_213_start_collision_leaves_the_row_alone_instead_of_rewriting_onto_it(vehicle_id):
    """Another row already starts at the leg's start and the odometer also differs: rewriting would hit
    the (vehicle, start_date) unique key, so the row is left as it is and nothing is taken."""
    from app.services.trip_sync import _apply_authoritative, parse_legs
    (leg,) = parse_legs(_payload(_drive("23:16", "23:47", 3000, 3038, "2026-11-02")))
    row = _tr(vehicle_id, "23:41", "23:52", 3002, 3040, day="2026-11-02")
    before = (row.start_date, row.start_odometer)
    assert _apply_authoritative(row, leg, 75.0, {leg.start}, True) == "conflict"
    assert (row.start_date, row.start_odometer) == before


@pytest.mark.asyncio
async def test_213_same_odometer_span_at_another_time_is_the_same_drive(replay_sessionmaker, vehicle_id):
    """A row with exactly the leg's odometer range counts as that leg even when its time is hours off."""
    d = "2026-11-02"
    async with replay_sessionmaker() as s:
        s.add(_tr(vehicle_id, "13:00", "13:31", 3000, 3038, day=d))      # stale duplicate, 2 h away
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("11:00", "11:31", 3000, 3038, d)))
    rows = await trips(replay_sessionmaker, vehicle_id)
    assert len(rows) == 1 and sum(r.distance_km for r in rows) == 38


@pytest.mark.asyncio
async def test_213_km_added_counts_a_corrected_trips_extra_distance(replay_sessionmaker, vehicle_id):
    """The report ('+N km') must include the distance a matched trip gains, also when written."""
    d = "2026-11-02"
    async with replay_sessionmaker() as s:
        s.add(_tr(vehicle_id, "23:41", "23:52", 3002, 3038, day=d))      # recorded 36 km of a 38 km leg
        await s.commit()
    res = await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("23:16", "23:47", 3000, 3038, d)))
    assert res.rewritten == 1 and res.km_added == 2


# ── v1.3.11: Škoda legs with bad times (#213, production data of Nov 5) ─────────────────────

def _readings(vid, day, pairs):
    from datetime import datetime, timezone
    from app.models.telemetry import OdometerReading
    return [OdometerReading(user_vehicle_id=vid, mileage_in_km=odo,
                            captured_at=datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=timezone.utc))
            for hhmm, odo in pairs]


def _two_leg_journey(first_dist, second_dist=0, d="2026-11-05") -> dict:
    """Journey 40610 -> 40648 (38 km) whose first leg may carry no distance."""
    return {"dailyTrips": [{"trips": [{"id": "j", "startMileageInKm": 40610, "endMileageInKm": 40648, "mileageInKm": 38,
        "waypoints": [
            {"coordinates": {"latitude": 47.5, "longitude": 19.0}, "departureStateOfChargeInPercent": 80,
             "departureTime": f"{d}T15:49:00Z", "distanceToNextWaypointInKm": first_dist},
            {"coordinates": {"latitude": 47.4, "longitude": 19.2}, "arrivalStateOfChargeInPercent": 75,
             "arrivalTime": f"{d}T16:01:00Z", "departureStateOfChargeInPercent": 75,
             "departureTime": f"{d}T20:13:00Z", "distanceToNextWaypointInKm": second_dist},
            {"coordinates": {"latitude": 47.6, "longitude": 19.1}, "arrivalStateOfChargeInPercent": 60,
             "arrivalTime": f"{d}T20:33:00Z"}]}]}]}


def test_213_journey_whose_legs_do_not_add_up_is_skipped_not_dumped_on_the_last_leg():
    """Legs with no distance made the last leg absorb the whole 38 km in its own 20-minute window."""
    assert parse_legs(_two_leg_journey(first_dist=0)) == []
    assert len(parse_legs(_two_leg_journey(first_dist=17, second_dist=21))) == 2      # 17 + 21 = 38: consistent, kept


@pytest.mark.asyncio
async def test_213_rows_inside_a_leg_are_folded_in_whatever_their_time(replay_sessionmaker, vehicle_id):
    """Nov 5: a 38 km leg at 20:13 covered the odometer span of live trips recorded at 15:49 and 17:19."""
    d = "2026-11-05"
    async with replay_sessionmaker() as s:
        s.add_all([_tr(vehicle_id, "15:49", "16:01", 40610, 40614, day=d), _tr(vehicle_id, "17:19", "17:31", 40624, 40631, day=d)])
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("20:13", "20:33", 40610, 40648, d)))
    rows = await trips(replay_sessionmaker, vehicle_id)
    assert len(rows) == 1 and rows[0].distance_km == 38


@pytest.mark.asyncio
async def test_213_leg_with_impossible_speed_gets_the_window_our_odometer_readings_give(replay_sessionmaker, vehicle_id):
    """22 km in 63 s at 10:36 UTC, while our readings show 40514 at 07:27 and 40536 from 07:55."""
    d = "2026-11-05"
    async with replay_sessionmaker() as s:
        s.add_all(_readings(vehicle_id, d, [("07:27:18", 40514), ("07:55:37", 40536), ("08:25:38", 40536), ("10:37:38", 40536)]))
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("10:36", "10:37", 40514, 40536, d)))
    (row,) = await trips(replay_sessionmaker, vehicle_id)
    assert row.start_date.strftime("%H:%M") == "07:33" and row.end_date.strftime("%H:%M") == "07:55"
    assert row.distance_km == 22 and row.data_quality == "estimated_times"


@pytest.mark.asyncio
async def test_213_leg_with_bad_times_and_no_readings_is_not_guessed(replay_sessionmaker, vehicle_id):
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("10:36", "10:37", 40514, 40536, "2026-11-05")))
    assert await trips(replay_sessionmaker, vehicle_id) == []


@pytest.mark.asyncio
async def test_213_a_stored_row_with_the_bad_times_is_corrected_on_the_next_sync(replay_sessionmaker, vehicle_id):
    """Row 12159 on hosted: written by v1.3.10 with the impossible times; the next sync repairs it."""
    d = "2026-11-05"
    async with replay_sessionmaker() as s:
        s.add(_tr(vehicle_id, "10:36", "10:37", 40514, 40536, quality="skoda_history", day=d))
        s.add_all(_readings(vehicle_id, d, [("07:27:18", 40514), ("07:55:37", 40536), ("10:37:38", 40536)]))
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("10:36", "10:37", 40514, 40536, d)))
    (row,) = await trips(replay_sessionmaker, vehicle_id)
    assert row.start_date.strftime("%H:%M") == "07:33" and row.data_quality == "estimated_times"


@pytest.mark.asyncio
async def test_213_a_live_trip_with_sound_times_keeps_them_when_the_leg_is_untrusted(replay_sessionmaker, vehicle_id):
    d = "2026-11-05"
    async with replay_sessionmaker() as s:
        s.add(_tr(vehicle_id, "07:36", "07:54", 40514, 40536, day=d))
        s.add_all(_readings(vehicle_id, d, [("07:27:18", 40514), ("07:55:37", 40536)]))
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("10:36", "10:37", 40514, 40536, d)))
    (row,) = await trips(replay_sessionmaker, vehicle_id)
    assert row.start_date.strftime("%H:%M") == "07:36" and row.end_date.strftime("%H:%M") == "07:54"


@pytest.mark.asyncio
async def test_213_normal_leg_is_trusted_even_when_the_odometer_reading_lags(replay_sessionmaker, vehicle_id):
    """Nov 4: the Public API odometer updates late; a plausible leg must keep Škoda's times."""
    d = "2026-11-04"
    async with replay_sessionmaker() as s:
        s.add_all(_readings(vehicle_id, d, [("13:50:00", 40000), ("14:20:00", 40000), ("14:26:30", 40011)]))
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("14:07", "14:26", 40000, 40011, d)))
    (row,) = await trips(replay_sessionmaker, vehicle_id)
    assert row.start_date.strftime("%H:%M") == "14:07" and row.data_quality == "skoda_history"


@pytest.mark.asyncio
async def test_213_dump_prints_waypoints_without_places_and_writes_nothing(replay_sessionmaker, vehicle_id, monkeypatch, capsys):
    await _login_vehicle(replay_sessionmaker, vehicle_id)
    sync, _ = _runner_env(monkeypatch, replay_sessionmaker, _issue_210_payload())
    await sync.run_trip_sync(pause_s=0, dump=True)
    out = capsys.readouterr().out
    assert "journey 1000 -> 1007" in out and "dep=2026-10-29T07:45:00Z" in out
    assert "latitude" not in out and "47.5" not in out
    assert await trips(replay_sessionmaker, vehicle_id) == []


@pytest.mark.asyncio
async def test_213_a_skipped_vehicle_and_ignored_journeys_are_reported_as_a_warning(replay_sessionmaker, vehicle_id, monkeypatch, caplog):
    import logging
    sync, _ = _runner_env(monkeypatch, replay_sessionmaker, _two_leg_journey(first_dist=0))
    # no ConnectorSession at all: the vehicle is skipped, and it must be said so
    with caplog.at_level(logging.INFO, logger="app.services.trip_sync"):
        await sync.run_trip_sync(pause_s=0)
    warn = [r for r in caplog.records if r.levelno == logging.WARNING and "trip sync run" in r.getMessage()]
    assert warn and "no usable MyŠkoda Login session" in warn[0].getMessage()
    caplog.clear()
    await _login_vehicle(replay_sessionmaker, vehicle_id)
    sync._failures.clear()
    with caplog.at_level(logging.INFO, logger="app.services.trip_sync"):
        await sync.run_trip_sync(pause_s=0)
    warn = [r for r in caplog.records if r.levelno == logging.WARNING and "trip sync run" in r.getMessage()]
    assert warn and "1 journeys ignored" in warn[0].getMessage()


# ── v1.3.12: an untrusted leg gets battery, energy and places from our own records (#213) ───

def _reporter_journey() -> dict:
    """The reporter's real Nov 5 journey: first leg 22 km in 63 s at 68 % -> 68 %, 13.09 kWh for 96 km."""
    def wp(arr, dep, soc_a, soc_d, km, lat):
        w = {"coordinates": {"latitude": lat, "longitude": 19.2}}
        if arr: w["arrivalTime"] = arr
        if dep: w["departureTime"] = dep
        if soc_a is not None: w["arrivalStateOfChargeInPercent"] = soc_a
        if soc_d is not None: w["departureStateOfChargeInPercent"] = soc_d
        if km is not None: w["distanceToNextWaypointInKm"] = km
        return w
    return {"dailyTrips": [{"trips": [{"id": "r", "startMileageInKm": 40514, "endMileageInKm": 40610, "mileageInKm": 96,
        "electricConsumption": 13.09, "waypoints": [
            wp(None, "2026-11-05T10:36:23.096Z", None, 68, 22, 47.60),
            wp("2026-11-05T10:37:26.329Z", "2026-11-05T10:39:30.339Z", 68, 65, 45, 47.60),
            wp("2026-11-05T11:17:22.283Z", "2026-11-05T12:39:39.962Z", 59, 58, 25, 47.50),
            wp("2026-11-05T13:15:07.748Z", "2026-11-05T13:25:29.505Z", 52, 52, 0, 47.51),
            wp("2026-11-05T13:29:30.616Z", "2026-11-05T14:12:00.284Z", 52, 52, 4, 47.52),
            wp("2026-11-05T14:19:07.429Z", None, 51, None, None, 47.53)]}]}]}


async def _reporter_telemetry(sm, vid, with_sessions=True, with_positions=True):
    from datetime import datetime, timezone
    from app.models.telemetry import ChargingSession, VehiclePosition
    f = lambda hhmm: datetime.fromisoformat(f"2026-11-05T{hhmm}").replace(tzinfo=timezone.utc)
    async with sm() as s:
        s.add_all(_readings(vid, "2026-11-05", [("07:27:18", 40514), ("07:55:37", 40536), ("10:31:38", 40536), ("10:43:38", 40537), ("11:17:00", 40581)]))
        if with_sessions:
            s.add_all([ChargingSession(user_vehicle_id=vid, session_start=f("02:49:00"), session_end=f("07:55:00"), start_level=16, end_level=60),
                       ChargingSession(user_vehicle_id=vid, session_start=f("07:55:00"), session_end=f("10:31:00"), start_level=54, end_level=68)])
        if with_positions:
            s.add_all([VehiclePosition(user_vehicle_id=vid, captured_at=f("07:27:00"), latitude=47.56, longitude=19.14),   # home
                       VehiclePosition(user_vehicle_id=vid, captured_at=f("07:57:00"), latitude=47.52, longitude=19.28)])  # Nagytarcsa
        await s.commit()


@pytest.mark.asyncio
async def test_213_untrusted_leg_takes_battery_energy_and_places_from_our_own_records(replay_sessionmaker, vehicle_id):
    await _reporter_telemetry(replay_sessionmaker, vehicle_id)
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    rows = await trips(replay_sessionmaker, vehicle_id)
    first = next(r for r in rows if r.start_odometer == 40514)
    assert first.start_date.strftime("%H:%M") == "07:33" and first.end_date.strftime("%H:%M") == "07:55"
    assert (first.start_soc, first.end_soc) == (60, 54)                       # not Škoda's 68 -> 68
    assert abs(first.kwh_consumed - 4.62) < 0.01                              # 6 % of 77 kWh, TRONITY: 4.62
    assert (round(first.start_lat, 2), round(first.end_lat, 2)) == (47.56, 47.52)   # home -> Nagytarcsa, not Škoda's waypoint
    assert first.data_quality == "estimated_times"
    others = [r for r in rows if r is not first]
    assert [(r.start_odometer, r.end_odometer) for r in others] == [(40536, 40581), (40581, 40606), (40606, 40610)]      # the 0 km leg is not inserted
    assert sum(r.distance_km for r in rows) == 96


@pytest.mark.asyncio
async def test_213_untrusted_leg_without_own_records_leaves_battery_energy_and_places_empty(replay_sessionmaker, vehicle_id):
    await _reporter_telemetry(replay_sessionmaker, vehicle_id, with_sessions=False, with_positions=False)
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    first = next(r for r in await trips(replay_sessionmaker, vehicle_id) if r.start_odometer == 40514)
    assert (first.start_soc, first.end_soc, first.kwh_consumed, first.start_lat, first.end_lat) == (None, None, None, None, None)
    assert first.distance_km == 22


@pytest.mark.asyncio
async def test_213_a_row_written_by_v1310_with_skodas_battery_is_repaired(replay_sessionmaker, vehicle_id):
    """Hosted row 12159: 10:36-10:37, battery 68 -> 68, 3.0 kWh."""
    await _reporter_telemetry(replay_sessionmaker, vehicle_id)
    async with replay_sessionmaker() as s:
        t = _tr(vehicle_id, "10:36", "10:37", 40514, 40536, quality="skoda_history", day="2026-11-05")
        t.start_soc, t.end_soc, t.kwh_consumed = 68, 68, 3.0
        s.add(t)
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    row = next(r for r in await trips(replay_sessionmaker, vehicle_id) if r.start_odometer == 40514)
    assert (row.start_soc, row.end_soc, row.data_quality) == (60, 54, "estimated_times")
    assert abs(row.kwh_consumed - 4.62) < 0.01 and row.start_date.strftime("%H:%M") == "07:33"


@pytest.mark.asyncio
async def test_213_a_live_row_with_sound_times_keeps_its_own_measured_values(replay_sessionmaker, vehicle_id):
    await _reporter_telemetry(replay_sessionmaker, vehicle_id)
    async with replay_sessionmaker() as s:
        t = _tr(vehicle_id, "07:36", "07:54", 40514, 40536, day="2026-11-05")
        t.start_soc, t.end_soc, t.kwh_consumed, t.start_lat, t.end_lat = 59, 54, 4.5, 47.55, 47.53
        s.add(t)
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    row = next(r for r in await trips(replay_sessionmaker, vehicle_id) if r.start_odometer == 40514)
    assert (row.start_soc, row.end_soc, row.kwh_consumed, row.start_lat, row.end_lat) == (59, 54, 4.5, 47.55, 47.53)
    assert row.start_date.strftime("%H:%M") == "07:36"


@pytest.mark.asyncio
async def test_213_a_charging_session_that_started_inside_the_drive_window_is_not_the_level_before_it(replay_sessionmaker, vehicle_id):
    """The 'level before the drive' must come from a session that started before the drive, not from one
    that began during the estimated window (review finding on #217)."""
    from datetime import datetime, timezone
    from app.models.telemetry import ChargingSession
    await _reporter_telemetry(replay_sessionmaker, vehicle_id)
    f = lambda hhmm: datetime.fromisoformat(f"2026-11-05T{hhmm}").replace(tzinfo=timezone.utc)
    async with replay_sessionmaker() as s:
        s.add(ChargingSession(user_vehicle_id=vehicle_id, session_start=f("07:40:00"), session_end=f("07:58:00"), start_level=70, end_level=80))
        await s.commit()
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    first = next(r for r in await trips(replay_sessionmaker, vehicle_id) if r.start_odometer == 40514)
    assert (first.start_soc, first.end_soc) == (60, 54)          # not 80 from the mid-window session


# ── v1.3.13: start-time clashes between stored rows that move in the same run ────────────────

@pytest.mark.asyncio
async def test_213_a_blocked_row_is_retried_after_the_row_in_its_way_has_moved(replay_sessionmaker, vehicle_id):
    """Ra must move to 08:00, where Rd sits; Rd itself moves to 11:00 later in the same run."""
    d = "2026-11-05"
    async with replay_sessionmaker() as s:
        s.add_all([_tr(vehicle_id, "10:00", "10:20", 1000, 1010, day=d),      # Ra: leg 1's drive, recorded at 10:00
                   _tr(vehicle_id, "08:00", "08:20", 1030, 1040, day=d)])     # Rd: leg 4's drive, sitting on leg 1's start
        await s.commit()
    res = await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("08:00", "08:20", 1000, 1010, d), _drive("11:00", "11:20", 1030, 1040, d)))
    got = sorted((r.start_date.strftime("%H:%M"), r.start_odometer) for r in await trips(replay_sessionmaker, vehicle_id))
    assert got == [("08:00", 1000), ("11:00", 1030)] and res.conflicts == 0


@pytest.mark.asyncio
async def test_213_two_rows_that_would_need_each_others_start_are_left_alone_safely(replay_sessionmaker, vehicle_id):
    """A true swap cannot be applied row by row; the safe outcome is: nothing written wrongly, no crash,
    no duplicate start, distance not changed, and the clash is reported."""
    d = "2026-11-05"
    async with replay_sessionmaker() as s:
        s.add_all([_tr(vehicle_id, "09:00", "09:20", 1000, 1010, day=d), _tr(vehicle_id, "08:00", "08:20", 1010, 1020, day=d)])
        await s.commit()
    res = await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("08:00", "08:20", 1000, 1010, d), _drive("09:00", "09:20", 1010, 1020, d)))
    rows = await trips(replay_sessionmaker, vehicle_id)
    assert len({r.start_date for r in rows}) == len(rows) == 2 and sum(r.distance_km for r in rows) == 20
    assert res.conflicts == 2


# ── v1.3.13: rows already stored by earlier versions, in every shape the sync can meet ───────

async def _stored_row(sm, vid, **kw):
    """The reporter's phantom-leg row as stored by an earlier version; kw overrides."""
    from datetime import datetime, timezone
    vals = dict(start="06:21:16", end="07:57:17", quality="estimated_times", soc=(68, 68), kwh=2.999791666666667,
                lat0=47.60, lon0=19.2, lat1=47.60, lon1=19.2)
    vals.update(kw)
    f = lambda hms: datetime.fromisoformat(f"2026-11-05T{hms}").replace(tzinfo=timezone.utc)
    async with sm() as s:
        t = _tr(vid, "00:00", "00:01", 40514, 40536, day="2026-11-05")
        t.start_date, t.end_date, t.data_quality = f(vals["start"]), f(vals["end"]), vals["quality"]
        t.start_soc, t.end_soc, t.kwh_consumed = vals["soc"][0], vals["soc"][1], vals["kwh"]
        t.start_lat, t.start_lon, t.end_lat, t.end_lon = vals["lat0"], vals["lon0"], vals["lat1"], vals["lon1"]
        s.add(t)
        await s.commit()


async def _first(sm, vid):
    return next(r for r in await trips(sm, vid) if r.start_odometer == 40514)


@pytest.mark.asyncio
async def test_213_row_repaired_by_v1311_but_still_carrying_skodas_battery_is_refreshed(replay_sessionmaker, vehicle_id):
    """The reporter's trip 2328 after v1.3.12: estimated_times, battery 68 -> 68, 2.9998 kWh. v1.3.12 left it
    alone because its times had become plausible. Our own records say 60 -> 54, 4.62 kWh."""
    await _reporter_telemetry(replay_sessionmaker, vehicle_id)
    await _stored_row(replay_sessionmaker, vehicle_id)
    res = await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    row = await _first(replay_sessionmaker, vehicle_id)
    assert (row.start_soc, row.end_soc) == (60, 54) and abs(row.kwh_consumed - 4.62) < 0.01
    assert (round(row.start_lat, 2), round(row.end_lat, 2)) == (47.56, 47.52)            # home -> Nagytarcsa, not Škoda's waypoint
    assert row.data_quality == "estimated_times" and res.rewritten >= 1
    # the drive is placed at the end of the window: 22 km at 60 km/h before the first reading showing 40536
    assert (row.start_date.strftime("%H:%M"), row.end_date.strftime("%H:%M")) == ("07:33", "07:55")


@pytest.mark.asyncio
async def test_213_the_same_row_without_own_records_loses_the_phantom_values_and_gets_no_new_ones(replay_sessionmaker, vehicle_id):
    from app.models.telemetry import OdometerReading  # noqa: F401
    await _reporter_telemetry(replay_sessionmaker, vehicle_id, with_sessions=False, with_positions=False)
    await _stored_row(replay_sessionmaker, vehicle_id)
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    row = await _first(replay_sessionmaker, vehicle_id)
    assert (row.start_soc, row.end_soc, row.kwh_consumed) == (None, None, None)
    assert (row.start_lat, row.start_lon, row.end_lat, row.end_lon) == (None, None, None, None)
    assert row.distance_km == 22


@pytest.mark.asyncio
async def test_213_a_second_sync_changes_nothing(replay_sessionmaker, vehicle_id):
    """The 6-hourly sync must not keep rewriting the same row."""
    await _reporter_telemetry(replay_sessionmaker, vehicle_id)
    await _stored_row(replay_sessionmaker, vehicle_id)
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    before = await _first(replay_sessionmaker, vehicle_id)
    snap = (before.start_date, before.end_date, before.start_soc, before.end_soc, before.kwh_consumed, before.start_lat, before.data_quality)
    for _ in range(2):
        res = await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
        assert (res.rewritten, res.inserted, res.removed) == (0, 0, 0)
    after = await _first(replay_sessionmaker, vehicle_id)
    assert (after.start_date, after.end_date, after.start_soc, after.end_soc, after.kwh_consumed, after.start_lat, after.data_quality) == snap


@pytest.mark.asyncio
async def test_213_values_we_derived_earlier_survive_when_our_own_records_are_gone(replay_sessionmaker, vehicle_id):
    """Positions can be pruned. A row that already carries good values of its own (not Škoda's) keeps them."""
    await _reporter_telemetry(replay_sessionmaker, vehicle_id, with_sessions=False, with_positions=False)
    await _stored_row(replay_sessionmaker, vehicle_id, soc=(60, 54), kwh=4.62, lat0=47.56, lon0=19.14, lat1=47.52, lon1=19.28)
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    row = await _first(replay_sessionmaker, vehicle_id)
    assert (row.start_soc, row.end_soc, row.kwh_consumed) == (60, 54, 4.62)
    assert (row.start_lat, row.end_lat) == (47.56, 47.52)


@pytest.mark.asyncio
async def test_213_a_stored_skoda_row_with_plausible_times_gets_our_battery_but_keeps_its_times(replay_sessionmaker, vehicle_id):
    await _reporter_telemetry(replay_sessionmaker, vehicle_id)
    await _stored_row(replay_sessionmaker, vehicle_id, start="07:36:00", end="07:54:00", quality="skoda_history")
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    row = await _first(replay_sessionmaker, vehicle_id)
    assert (row.start_soc, row.end_soc) == (60, 54) and abs(row.kwh_consumed - 4.62) < 0.01
    assert (row.start_date.strftime("%H:%M"), row.end_date.strftime("%H:%M"), row.data_quality) == ("07:36", "07:54", "skoda_history")


@pytest.mark.asyncio
@pytest.mark.parametrize("quality", [None, "estimated_start", "estimated_end", "reconstructed"])
async def test_213_rows_we_measured_or_rebuilt_ourselves_are_never_overwritten(replay_sessionmaker, vehicle_id, quality):
    await _reporter_telemetry(replay_sessionmaker, vehicle_id)
    await _stored_row(replay_sessionmaker, vehicle_id, start="07:36:00", end="07:54:00", quality=quality, soc=(59, 54), kwh=4.5,
                      lat0=47.55, lon0=19.1, lat1=47.53, lon1=19.3)
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    row = await _first(replay_sessionmaker, vehicle_id)
    assert (row.start_soc, row.end_soc, row.kwh_consumed, row.start_lat, row.end_lat) == (59, 54, 4.5, 47.55, 47.53)
    assert row.data_quality == quality


@pytest.mark.asyncio
async def test_213_a_half_complete_own_record_never_falls_back_to_skodas_battery(replay_sessionmaker, vehicle_id):
    """Only the session before the drive exists (the next charge has not started yet): not enough for a pair."""
    from datetime import datetime, timezone
    from app.models.telemetry import ChargingSession
    await _reporter_telemetry(replay_sessionmaker, vehicle_id, with_sessions=False)
    f = lambda hhmm: datetime.fromisoformat(f"2026-11-05T{hhmm}").replace(tzinfo=timezone.utc)
    async with replay_sessionmaker() as s:
        s.add(ChargingSession(user_vehicle_id=vehicle_id, session_start=f("02:49:00"), session_end=f("07:55:00"), start_level=16, end_level=60))
        await s.commit()
    await _stored_row(replay_sessionmaker, vehicle_id)
    await _sync(replay_sessionmaker, vehicle_id, _reporter_journey())
    row = await _first(replay_sessionmaker, vehicle_id)
    assert (row.start_soc, row.end_soc, row.kwh_consumed) == (None, None, None)
