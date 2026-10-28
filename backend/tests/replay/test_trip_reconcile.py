"""Zero-distance trips caused by a lagging odometer are repaired from later readings."""

import pytest

from .conftest import *  # noqa: F401,F403  (fixtures)
from .replay import Poll, replay, t, trips
from app.services.trip_reconcile import (
    create_reconstructed_trips, find_uncovered_gaps, reconcile_zero_distance_trips,
)


def _stale_odometer_polls():
    return [
        Poll(t("08:00"), moving=False, odometer=100),
        Poll(t("08:05"), moving=True, odometer=100),   # odometer not updated yet
        Poll(t("08:10"), moving=False, odometer=100),  # still stale at trip end
        Poll(t("08:40"), moving=False, odometer=110),  # Skoda catches up
    ]


@pytest.mark.asyncio
async def test_live_pass_attributes_late_odometer_to_trip(replay_sessionmaker, vehicle_id):
    await replay(replay_sessionmaker, vehicle_id, _stale_odometer_polls())
    (trip,) = await trips(replay_sessionmaker, vehicle_id)
    assert trip.distance_km == 10.0 and trip.end_odometer == 110
    assert trip.data_quality == "estimated_end"


@pytest.mark.asyncio
async def test_backfill_dry_run_does_not_write_and_apply_is_idempotent(replay_sessionmaker, vehicle_id):
    from app.models.telemetry import Trip
    from datetime import timedelta
    async with replay_sessionmaker() as s:
        from app.models.telemetry import OdometerReading
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("08:05"), end_date=t("08:10"),
                   start_odometer=100, end_odometer=100, distance_km=0))
        s.add(OdometerReading(user_vehicle_id=vehicle_id, captured_at=t("08:40"), mileage_in_km=110))
        await s.commit()
    async with replay_sessionmaker() as s:
        fixes = await reconcile_zero_distance_trips(s, vehicle_id, apply=False)
        await s.rollback()
    assert [f.new_distance for f in fixes] == [10.0]
    assert (await trips(replay_sessionmaker, vehicle_id))[0].distance_km == 0
    async with replay_sessionmaker() as s:
        await reconcile_zero_distance_trips(s, vehicle_id, apply=True)
        await s.commit()
    async with replay_sessionmaker() as s:
        assert await reconcile_zero_distance_trips(s, vehicle_id, apply=True) == []
    assert (await trips(replay_sessionmaker, vehicle_id))[0].distance_km == 10.0


@pytest.mark.asyncio
async def test_following_trip_that_double_counted_is_trimmed(replay_sessionmaker, vehicle_id):
    from app.models.telemetry import OdometerReading, Trip
    async with replay_sessionmaker() as s:
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("08:05"), end_date=t("08:10"),
                   start_odometer=100, end_odometer=100, distance_km=0))
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("08:30"), end_date=t("08:50"),
                   start_odometer=100, end_odometer=118, distance_km=18))
        s.add(OdometerReading(user_vehicle_id=vehicle_id, captured_at=t("08:20"), mileage_in_km=110))
        await s.commit()
    async with replay_sessionmaker() as s:
        await reconcile_zero_distance_trips(s, vehicle_id, apply=True)
        await s.commit()
    a, b = await trips(replay_sessionmaker, vehicle_id)
    assert (a.distance_km, b.start_odometer, b.distance_km) == (10.0, 110, 8.0)


@pytest.mark.asyncio
async def test_uncovered_gap_report_and_reconstruction(replay_sessionmaker, vehicle_id):
    from app.models.telemetry import OdometerReading, Trip
    async with replay_sessionmaker() as s:
        for hh, odo in (("07:00", 100), ("07:30", 100), ("08:00", 125), ("08:30", 125)):
            s.add(OdometerReading(user_vehicle_id=vehicle_id, captured_at=t(hh), mileage_in_km=odo))
        await s.commit()
    async with replay_sessionmaker() as s:
        gaps = await find_uncovered_gaps(s, vehicle_id)
        assert [(g.start_odometer, g.end_odometer) for g in gaps] == [(100, 125)]
        assert await create_reconstructed_trips(s, vehicle_id, gaps) == 1
        assert await create_reconstructed_trips(s, vehicle_id, gaps) == 0  # idempotent
        await s.commit()
    async with replay_sessionmaker() as s:
        assert await find_uncovered_gaps(s, vehicle_id) == []  # now covered
    (trip,) = await trips(replay_sessionmaker, vehicle_id)
    assert trip.data_quality == "reconstructed" and trip.distance_km == 25


@pytest.mark.asyncio
async def test_phantom_trip_detection_spares_trips_with_odometer_evidence(replay_sessionmaker, vehicle_id):
    from app.models.telemetry import OdometerReading, Trip
    from app.services.trip_reconcile import find_phantom_trips
    async with replay_sessionmaker() as s:
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("08:00"), end_date=t("08:05"),
                   start_odometer=100, end_odometer=100, distance_km=0))   # flicker
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("12:00"), end_date=t("12:05"),
                   start_odometer=100, end_odometer=100, distance_km=0))   # odometer catches up
        s.add(OdometerReading(user_vehicle_id=vehicle_id, captured_at=t("12:30"), mileage_in_km=104))
        s.add(Trip(user_vehicle_id=vehicle_id, start_date=t("15:00"), end_date=t("16:00"),
                   start_odometer=104, end_odometer=104, distance_km=0))   # too long to be a flicker
        await s.commit()
    async with replay_sessionmaker() as s:
        found = await find_phantom_trips(s, vehicle_id)
    assert [x.start_date for x in found] == [t("08:00")]
