"""#209: edit and delete single trips; the Škoda sync and the repair tools must respect both."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from .conftest import *  # noqa: F401,F403  (fixtures)
from .replay import trips
from app.api.v1.vehicles import delete_trip, edit_trip
from app.models.telemetry import DeletedTrip, OdometerReading, Trip
from app.models.user import User
from app.models.vehicle import UserVehicle
from app.schemas.telemetry import TripEdit
from app.services.trip_reconcile import find_phantom_trips, find_uncovered_gaps, reconcile_zero_distance_trips
from app.services.trip_sync import parse_legs, sync_legs

from .test_trip_sync import _drive, _payload, _sync, _tr


async def _owner(sm, vehicle_id) -> User:
    async with sm() as s:
        return (await s.execute(select(User).join(UserVehicle, UserVehicle.user_id == User.id)
                                .where(UserVehicle.id == vehicle_id))).scalar_one()


async def _stranger(sm) -> User:
    import uuid
    async with sm() as s:
        u = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@x.local", password_hash="x")
        s.add(u)
        await s.commit()
        return u


async def _add(sm, trip: Trip) -> int:
    async with sm() as s:
        s.add(trip)
        await s.commit()
        return trip.id


@pytest.mark.asyncio
async def test_edit_changes_values_keeps_history_and_marks_the_trip(replay_sessionmaker, vehicle_id):
    tid = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:30", 1000, 1022, day="2026-11-05"))
    user = await _owner(replay_sessionmaker, vehicle_id)
    async with replay_sessionmaker() as s:
        out = await edit_trip(vehicle_id, tid, TripEdit(distance_km=20.0, kwh_consumed=4.6), user, s)
    assert (out.distance_km, out.kwh_consumed, out.manually_edited, out.data_quality) == (20.0, 4.6, True, "manually_corrected")
    async with replay_sessionmaker() as s:
        t = await s.get(Trip, tid)
        assert t.end_odometer == 1020.0                                   # odometer span follows the distance
        assert t.edit_history[0]["changes"]["distance_km"] == [22.0, 20.0]


@pytest.mark.asyncio
async def test_edit_can_move_the_times(replay_sessionmaker, vehicle_id):
    tid = await _add(replay_sessionmaker, _tr(vehicle_id, "10:36", "10:37", 1000, 1022, day="2026-11-05"))
    user = await _owner(replay_sessionmaker, vehicle_id)
    new_s, new_e = datetime(2026, 11, 5, 7, 36, tzinfo=timezone.utc), datetime(2026, 11, 5, 7, 54, tzinfo=timezone.utc)
    async with replay_sessionmaker() as s:
        out = await edit_trip(vehicle_id, tid, TripEdit(start_date=new_s, end_date=new_e), user, s)
    assert out.start_date == new_s and out.end_date == new_e


@pytest.mark.asyncio
async def test_edit_rejects_bad_input_and_other_peoples_trips(replay_sessionmaker, vehicle_id):
    a = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:30", 1000, 1010, day="2026-11-05"))
    await _add(replay_sessionmaker, _tr(vehicle_id, "09:00", "09:30", 1010, 1020, day="2026-11-05"))
    user = await _owner(replay_sessionmaker, vehicle_id)
    day = datetime(2026, 11, 5, tzinfo=timezone.utc)

    async def call(body, who=user, tid=a):
        async with replay_sessionmaker() as s:
            return await edit_trip(vehicle_id, tid, body, who, s)

    for body, code in [
        (TripEdit(end_date=day + timedelta(hours=7)), 422),                                   # ends before it starts
        (TripEdit(end_date=day + timedelta(days=4)), 422),                                    # longer than 48 h
        (TripEdit(start_date=day + timedelta(hours=9), end_date=day + timedelta(hours=9, minutes=20)), 409),   # another trip starts there
    ]:
        with pytest.raises(HTTPException) as e:
            await call(body)
        assert e.value.status_code == code
    with pytest.raises(HTTPException) as e:
        await call(TripEdit(distance_km=5.0), who=await _stranger(replay_sessionmaker))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        await call(TripEdit(distance_km=5.0), tid=999999)
    assert e.value.status_code == 404
    with pytest.raises(Exception):
        TripEdit(distance_km=-1.0)                                                              # negative distance
    async with replay_sessionmaker() as s:                                                      # nothing was written
        assert (await s.get(Trip, a)).manually_edited is False


@pytest.mark.asyncio
async def test_edit_without_a_change_leaves_no_trace_and_open_trips_are_refused(replay_sessionmaker, vehicle_id):
    tid = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:30", 1000, 1010, day="2026-11-05"))
    open_id = await _add(replay_sessionmaker, Trip(user_vehicle_id=vehicle_id, start_date=datetime(2026, 11, 5, 12, tzinfo=timezone.utc)))
    user = await _owner(replay_sessionmaker, vehicle_id)
    async with replay_sessionmaker() as s:
        out = await edit_trip(vehicle_id, tid, TripEdit(distance_km=10.0), user, s)
    assert out.manually_edited is False and out.data_quality is None
    async with replay_sessionmaker() as s:
        with pytest.raises(HTTPException) as e:
            await edit_trip(vehicle_id, open_id, TripEdit(distance_km=3.0), user, s)
        assert e.value.status_code == 409
        with pytest.raises(HTTPException) as e:
            await delete_trip(vehicle_id, open_id, user, s)
        assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_removes_the_trip_and_remembers_its_odometer_span(replay_sessionmaker, vehicle_id):
    tid = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:30", 1000, 1022, day="2026-11-05"))
    keep = await _add(replay_sessionmaker, _tr(vehicle_id, "09:00", "09:30", 1022, 1030, day="2026-11-05"))
    user = await _owner(replay_sessionmaker, vehicle_id)
    with pytest.raises(HTTPException) as e:
        async with replay_sessionmaker() as s:
            await delete_trip(vehicle_id, tid, await _stranger(replay_sessionmaker), s)
    assert e.value.status_code == 404
    async with replay_sessionmaker() as s:
        await delete_trip(vehicle_id, tid, user, s)
    assert [t.id for t in await trips(replay_sessionmaker, vehicle_id)] == [keep]
    async with replay_sessionmaker() as s:
        (d,) = (await s.execute(select(DeletedTrip))).scalars().all()
        assert (d.start_odometer, d.end_odometer) == (1000.0, 1022.0)


# ── the sync and the repair tools respect edits and deletes ─────────────────────────────────

@pytest.mark.asyncio
async def test_sync_does_not_recreate_a_deleted_trip_even_at_another_time(replay_sessionmaker, vehicle_id):
    d = "2026-11-05"
    tid = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:30", 40514, 40536, day=d))
    async with replay_sessionmaker() as s:
        await delete_trip(vehicle_id, tid, await _owner(replay_sessionmaker, vehicle_id), s)
    res = await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("11:00", "11:25", 40514, 40536, d)))
    assert await trips(replay_sessionmaker, vehicle_id) == [] and res.left_alone == 1


@pytest.mark.asyncio
async def test_sync_never_rewrites_or_duplicates_an_edited_trip(replay_sessionmaker, vehicle_id):
    d = "2026-11-05"
    tid = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:30", 40514, 40536, day=d))
    async with replay_sessionmaker() as s:
        await edit_trip(vehicle_id, tid, TripEdit(distance_km=20.0, kwh_consumed=4.0), await _owner(replay_sessionmaker, vehicle_id), s)
    res = await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("08:05", "08:35", 40514, 40536, d)))
    (row,) = await trips(replay_sessionmaker, vehicle_id)
    assert (row.id, row.distance_km, row.end_odometer, row.kwh_consumed, row.start_date.strftime("%H:%M")) == (tid, 20.0, 40534.0, 4.0, "08:00")
    assert row.manually_edited and res.left_alone == 1 and res.inserted == 0 and res.rewritten == 0


@pytest.mark.asyncio
async def test_sync_does_not_delete_an_edited_trip_as_a_duplicate(replay_sessionmaker, vehicle_id):
    d = "2026-11-05"
    tid = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:30", 40514, 40536, day=d))
    await _add(replay_sessionmaker, _tr(vehicle_id, "08:01", "08:30", 40514, 40536, day=d, quality="skoda_history"))  # looks "better"
    async with replay_sessionmaker() as s:
        await edit_trip(vehicle_id, tid, TripEdit(distance_km=21.0), await _owner(replay_sessionmaker, vehicle_id), s)
    await _sync(replay_sessionmaker, vehicle_id, _payload(_drive("08:00", "08:30", 40514, 40536, d)))
    ids = {t.id for t in await trips(replay_sessionmaker, vehicle_id)}
    assert tid in ids                                    # the user's trip survives; the leg was not applied on top of it


@pytest.mark.asyncio
async def test_repair_tools_leave_edited_trips_alone_and_do_not_refill_deleted_spans(replay_sessionmaker, vehicle_id):
    d = "2026-11-05"
    zero = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:10", 100, 100, day=d))
    async with replay_sessionmaker() as s:
        await edit_trip(vehicle_id, zero, TripEdit(distance_km=0.0, kwh_consumed=0.5), await _owner(replay_sessionmaker, vehicle_id), s)
        s.add_all([OdometerReading(user_vehicle_id=vehicle_id, mileage_in_km=100, captured_at=datetime(2026, 11, 5, 7, 50, tzinfo=timezone.utc)),
                   OdometerReading(user_vehicle_id=vehicle_id, mileage_in_km=108, captured_at=datetime(2026, 11, 5, 8, 20, tzinfo=timezone.utc))])
        await s.commit()
    async with replay_sessionmaker() as s:
        assert await reconcile_zero_distance_trips(s, vehicle_id, apply=True) == []           # edited: not "fixed"
        assert await find_phantom_trips(s, vehicle_id) == []                                  # edited: not a phantom
    # a gap 100 -> 108 exists; once the user deleted a trip covering it, it is no longer a gap
    async with replay_sessionmaker() as s:
        s.add(DeletedTrip(user_vehicle_id=vehicle_id, start_date=datetime(2026, 11, 5, 8, tzinfo=timezone.utc),
                          start_odometer=100.0, end_odometer=108.0))
        await s.commit()
    async with replay_sessionmaker() as s:
        assert await find_uncovered_gaps(s, vehicle_id) == []


@pytest.mark.asyncio
async def test_edit_and_delete_drop_the_cached_statistics_of_that_vehicle(replay_sessionmaker, vehicle_id, monkeypatch):
    """The API caches GET responses per vehicle: without this, an edited or deleted trip keeps showing."""
    import app.api.v1.vehicles as api
    dropped = []

    async def fake_invalidate(vid):
        dropped.append(vid)
    monkeypatch.setattr(api, "invalidate_vehicle_cache", fake_invalidate)
    tid = await _add(replay_sessionmaker, _tr(vehicle_id, "08:00", "08:30", 1000, 1010, day="2026-11-05"))
    user = await _owner(replay_sessionmaker, vehicle_id)
    async with replay_sessionmaker() as s:
        await edit_trip(vehicle_id, tid, TripEdit(distance_km=10.0), user, s)           # no change: nothing to drop
        assert dropped == []
        await edit_trip(vehicle_id, tid, TripEdit(distance_km=9.0), user, s)
        assert dropped == [str(vehicle_id)]
        await delete_trip(vehicle_id, tid, user, s)
    assert dropped == [str(vehicle_id)] * 2
