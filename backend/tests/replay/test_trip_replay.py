"""#204 - trips must not silently lose distance between polls."""

import pytest

from .conftest import *  # noqa: F401,F403  (fixtures)
from .replay import Poll, replay, t, trips


def _readme_204_polls() -> list[Poll]:
    """Rows from the reporter's evidence (2026-10-28, local time, odometer km).

    Parked polls are 30 min apart; the 09:06 departure is first seen at 09:31.
    Ground truth (MySkoda): 08:32-08:39 3 km, 09:06-09:34 21 km, 09:45-10:19 18 km.
    """
    return [
        Poll(t("08:37"), moving=True, odometer=39914),
        Poll(t("08:43"), moving=False, odometer=39917),
        Poll(t("08:49"), moving=False, odometer=39917),
        Poll(t("08:55"), moving=False, odometer=39917),
        Poll(t("09:31"), moving=True, odometer=39934),
        Poll(t("09:37"), moving=False, ignition=True, odometer=39938),
        Poll(t("09:43"), moving=False, odometer=39938),
        Poll(t("09:49"), moving=True, odometer=39938),
        Poll(t("09:55"), moving=True, odometer=39938),
        Poll(t("10:01"), moving=True, odometer=39941),
        Poll(t("10:07"), moving=True, odometer=39947),
        Poll(t("10:13"), moving=True, odometer=39947),
        Poll(t("10:19"), moving=False, ignition=True, odometer=39956),
        Poll(t("10:25"), moving=False, odometer=39956),
    ]


@pytest.mark.asyncio
async def test_204_no_odometer_distance_is_lost(replay_sessionmaker, vehicle_id):
    await replay(replay_sessionmaker, vehicle_id, _readme_204_polls())
    got = await trips(replay_sessionmaker, vehicle_id)
    total = sum(x.distance_km or 0 for x in got)
    # 39914 -> 39956 = 42 km of driven odometer, all of it must be in trips.
    assert total == pytest.approx(42.0), [(x.start_odometer, x.end_odometer, x.distance_km) for x in got]


@pytest.mark.asyncio
async def test_204_late_detected_trip_starts_at_last_parked_odometer(replay_sessionmaker, vehicle_id):
    await replay(replay_sessionmaker, vehicle_id, _readme_204_polls())
    got = await trips(replay_sessionmaker, vehicle_id)
    starts = {x.start_odometer for x in got}
    assert 39917 in starts, starts  # 17 km before first moving poll must not be discarded


@pytest.mark.asyncio
async def test_trip_end_uses_telemetry_time_not_processing_time(replay_sessionmaker, vehicle_id):
    polls = [
        Poll(t("08:00"), moving=False, odometer=100),
        Poll(t("08:05"), moving=True, odometer=101),
        Poll(t("08:10"), moving=False, odometer=105),
    ]
    await replay(replay_sessionmaker, vehicle_id, polls)
    (trip,) = await trips(replay_sessionmaker, vehicle_id)
    assert trip.end_date == t("08:10")
    assert trip.distance_km == 5.0


# ── v1.3.9 (#213): a trip must not stay open across a collector outage ───────────────────

@pytest.mark.asyncio
async def test_213_trip_open_during_outage_ends_at_its_last_moving_poll(replay_sessionmaker, vehicle_id):
    """Airport return 00:35, collector down (re-auth) until 09:50. The 7 km morning drive happened
    in the gap; it must not be glued onto the night trip (47 km, 8 h 36 min in the issue)."""
    polls = [
        Poll(t("00:20"), moving=False, odometer=1000),
        Poll(t("00:35"), moving=True, odometer=1000),
        Poll(t("00:50"), moving=True, odometer=1020),
        Poll(t("09:50"), moving=False, odometer=1047),   # first poll after re-authentication
    ]
    await replay(replay_sessionmaker, vehicle_id, polls)
    (trip,) = await trips(replay_sessionmaker, vehicle_id)
    assert trip.end_date == t("00:50"), trip.end_date
    assert trip.end_odometer == 1020 and trip.distance_km == 20


@pytest.mark.asyncio
async def test_213_drive_after_an_outage_is_a_new_trip_and_does_not_absorb_the_gap(replay_sessionmaker, vehicle_id):
    polls = [
        Poll(t("00:20"), moving=False, odometer=1000),
        Poll(t("00:35"), moving=True, odometer=1000),
        Poll(t("00:50"), moving=True, odometer=1020),
        Poll(t("08:20"), moving=True, odometer=1042),    # next drive, seen after the outage
        Poll(t("08:30"), moving=True, odometer=1045),
        Poll(t("08:40"), moving=False, odometer=1047),
    ]
    await replay(replay_sessionmaker, vehicle_id, polls)
    first, second = await trips(replay_sessionmaker, vehicle_id)
    assert first.end_date == t("00:50") and first.distance_km == 20
    assert second.start_date == t("08:20")
    assert second.start_odometer == 1042 and second.distance_km == 5   # not 27: the gap is unknown, not ours


@pytest.mark.asyncio
async def test_213_normal_trip_with_regular_polls_is_unchanged(replay_sessionmaker, vehicle_id):
    polls = [
        Poll(t("08:00"), moving=False, odometer=100),
        Poll(t("08:05"), moving=True, odometer=101),
        Poll(t("08:10"), moving=True, odometer=105),
        Poll(t("08:15"), moving=False, odometer=108),
    ]
    await replay(replay_sessionmaker, vehicle_id, polls)
    (trip,) = await trips(replay_sessionmaker, vehicle_id)
    assert trip.end_date == t("08:15") and trip.distance_km == 8
