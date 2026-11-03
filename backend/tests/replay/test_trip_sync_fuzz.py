"""Release gate for the Škoda trip sync (#213): random recorded history against random Škoda legs.

Shapes seen in real histories: exact rows, late starts, fragments, duplicates with a jittered start,
rows merged over two legs, rows without odometer, and rows whose start equals the *next* leg's start
(left behind by earlier sync versions). After the sync: it must not raise, no leg may be counted
twice and no two rows may share a start time.
"""
import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from .conftest import *  # noqa: F401,F403  (fixtures)
from app.models.telemetry import Trip
from app.services.trip_sync import _flush_start_moves, parse_legs, sync_legs

BASE = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
SEEDS = 300


def _scenario(rng):
    legs, rows, odo, t = [], [], 1000, BASE
    for _ in range(rng.randint(3, 12)):
        t += timedelta(minutes=rng.randint(5, 90))
        km = rng.randint(1, 40)
        dur = timedelta(minutes=max(3, km + rng.randint(-2, 8)))
        legs.append((t, t + dur, odo, odo + km))
        odo += km
        t += dur
    for (s, e, so, eo) in legs:
        k, late = rng.random(), timedelta(minutes=rng.randint(0, 25))
        if k < .2:
            continue
        if k < .5:
            rows.append((s, e, so, eo))
        elif k < .7:
            rows.append((s + late, e, so, eo))
        elif k < .85:
            mid, half = (so + eo) // 2, s + (e - s) / 2
            rows += [(s + late, half, so, mid), (half + timedelta(minutes=1), e, mid, eo)]
        else:
            rows += [(s, e, so, eo), (s + timedelta(seconds=rng.randint(1, 600)), e, so, eo)]
    for i in range(len(legs) - 1):          # start == next leg's start, odometer of this leg
        if rng.random() < .25:
            a, b = legs[i], legs[i + 1]
            rows.append((b[0], b[0] + (a[1] - a[0]), a[2], a[3]))
    for (s_, e_, _so, _eo) in legs:         # no odometer at all
        if rng.random() < .15:
            rows.append((s_ + timedelta(seconds=rng.randint(30, 3000)), e_ + timedelta(minutes=rng.randint(0, 20)), None, None))
    if len(legs) > 2 and rng.random() < .5:  # one row over two legs
        a, b = legs[0], legs[1]
        rows.append((a[0] + timedelta(minutes=rng.randint(0, 5)), b[1], a[2], b[3]))
    seen, out = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r)
    return legs, out


def _payload(legs):
    f = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"dailyTrips": [{"trips": [
        {"id": str(i), "startMileageInKm": so, "endMileageInKm": eo, "waypoints": [
            {"coordinates": {"latitude": 47.5, "longitude": 19.0}, "departureStateOfChargeInPercent": 80,
             "departureTime": f(s), "distanceToNextWaypointInKm": eo - so},
            {"coordinates": {"latitude": 47.6, "longitude": 19.1}, "arrivalStateOfChargeInPercent": 78, "arrivalTime": f(e)}]}
        for i, (s, e, so, eo) in enumerate(legs)]}]}


@pytest.mark.asyncio
async def test_fuzz_sync_never_crashes_double_counts_or_collides(replay_sessionmaker, vehicle_id):
    bad = []
    for seed in range(SEEDS):
        legs, rows = _scenario(random.Random(seed))
        async with replay_sessionmaker() as s:
            for (a, b, so, eo) in rows:
                s.add(Trip(user_vehicle_id=vehicle_id, start_date=a, end_date=b, start_odometer=so, end_odometer=eo,
                           distance_km=(eo - so) if so is not None else None))
            await s.commit()
        try:
            async with replay_sessionmaker() as s:
                await sync_legs(s, vehicle_id, parse_legs(_payload(legs)), apply=True)
                await s.commit()
            async with replay_sessionmaker() as s:
                rs = list((await s.execute(select(Trip).where(Trip.user_vehicle_id == vehicle_id))).scalars())
            total, want = sum(r.distance_km or 0 for r in rs), sum(l[3] - l[2] for l in legs)
            if total > want * 1.15 + 2:
                bad.append((seed, "overcount", total, want))
            if len({r.start_date for r in rs}) != len(rs):
                bad.append((seed, "same start"))
        except Exception as ex:  # noqa: BLE001
            bad.append((seed, type(ex).__name__, str(ex).split("DETAIL:")[-1][:100]))
        async with replay_sessionmaker() as s:
            await s.execute(delete(Trip).where(Trip.user_vehicle_id == vehicle_id))
            await s.commit()
    assert not bad, f"{len(bad)} of {SEEDS} scenarios failed, e.g. {bad[:3]}"


@pytest.mark.asyncio
async def test_213_rows_trading_start_times_are_written_in_any_order(replay_sessionmaker, vehicle_id):
    """X takes the start Y gives up. The unique key is checked per statement, so a plain flush fails
    whenever X's UPDATE runs before Y's; the two-step write must not depend on that order."""
    t0 = BASE
    lo, hi = 9_000_001, 9_000_002             # lower id is flushed first
    async with replay_sessionmaker() as s:
        s.add_all([Trip(id=lo, user_vehicle_id=vehicle_id, start_date=t0 + timedelta(hours=2), end_date=t0 + timedelta(hours=3),
                        start_odometer=10, end_odometer=20, distance_km=10),
                   Trip(id=hi, user_vehicle_id=vehicle_id, start_date=t0 + timedelta(hours=1), end_date=t0 + timedelta(hours=1, minutes=30),
                        start_odometer=5, end_odometer=10, distance_km=5)])
        await s.commit()
    async with replay_sessionmaker() as s:
        x, y = await s.get(Trip, lo), await s.get(Trip, hi)
        first = {x.id: x.start_date, y.id: y.start_date}
        x.start_date, y.start_date = first[hi], t0                     # x takes y's start; y moves away
        await _flush_start_moves(s, [x, y], first)
        await s.commit()
    async with replay_sessionmaker() as s:
        starts = sorted(r.start_date for r in (await s.execute(select(Trip).where(Trip.user_vehicle_id == vehicle_id))).scalars())
    assert starts == [t0, t0 + timedelta(hours=1)]
