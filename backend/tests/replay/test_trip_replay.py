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
