"""#218: Battery SoH must not report the configured capacity back as a measurement, must not serve a
months-old result, must store 'no result' as NULL, and must say why a method has no result."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from .conftest import *  # noqa: F401,F403  (fixtures)
from app.api.v1 import analytics as analytics_api
from app.api.v1.battery_health import _cache_is_fresh
from app.models.telemetry import (BatteryHealth, BatteryHealthAnalytics, ChargingCurve, ChargingSession,
                                  ChargingState, Drive, DriveRangeEstimatedFull)
from app.models.vehicle import UserVehicle
from app.services import battery_health_v2 as bh
from app.services import battery_scheduler, battery_soh

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


async def _session(sm, vid, start, hours, s0, s1, kw=None, cover=1.0, ctype="AC", idle_hours=0.0):
    """A closed session with SoC-derived energy (as analytics.py writes it) and, if kw is given,
    charging-state rows carrying that power over `cover` of the charging time. `idle_hours` is the
    cable-still-connected tail analytics.py leaves in session_end (last_soc_change_at marks the
    end of the charge, as it does for a session closed by the flat-SoC timeout)."""
    charge_end = start + timedelta(hours=hours)
    end = charge_end + timedelta(hours=idle_hours)
    async with sm() as s:
        s.add(ChargingSession(user_vehicle_id=vid, session_start=start, session_end=end, start_level=s0, end_level=s1,
                              charging_type=ctype, energy_kwh=(s1 - s0) / 100.0 * 77.0,
                              last_soc_change_at=charge_end if idle_hours else None))
        if kw is not None:
            s.add(ChargingState(user_vehicle_id=vid, first_date=start, last_date=start + timedelta(hours=hours * cover),
                                state="CHARGING", charge_power_kw=kw, battery_pct=s1))
        await s.commit()


@pytest.mark.asyncio
async def test_idle_tail_after_the_charge_does_not_count_against_coverage(replay_sessionmaker, vehicle_id):
    """A charge finished with the cable still in is closed 30 minutes after the SoC went flat, so
    session_end carries an idle half hour with no power. Coverage was measured against the whole
    session: a one-hour 11 kW charge was 67 % covered and skipped, so a car charged in short
    top-ups never got a capacity figure. The charge ends where the SoC last changed."""
    for i in range(8):
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=i + 1), 1, 40, 56, kw=11.0, idle_hours=0.5)
    async with replay_sessionmaker() as s:
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.inputs["skipped"]["low_coverage"] == 0
    assert r.sample_count == 8 and r.soh_pct is not None
    assert abs(r.extra["median_kwh"] - 11.0 * 0.95 / 0.16) < 0.05       # 65.31 kWh, the idle tail added nothing


@pytest.mark.asyncio
async def test_capacity_is_not_derived_from_soc_times_nominal_capacity(replay_sessionmaker, vehicle_id):
    """The reporter's case: 53 sessions, all energy_kwh = SoC x 77, no power readings -> HIGH confidence 97.8 %.
    Now: no result, with the reason, because nothing was measured."""
    for i in range(12):
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=i + 1), 3, 40, 70)
    async with replay_sessionmaker() as s:
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.soh_pct is None and r.sample_count == 0 and r.confidence == "low"
    assert "power readings" in r.inputs["reason"] and r.inputs["skipped"]["no_power_readings"] == 12


@pytest.mark.asyncio
async def test_capacity_comes_from_integrated_charging_power_and_is_capped_at_medium(replay_sessionmaker, vehicle_id):
    """11 kW for 2 h = 22 kWh AC for 30 % added -> 22 x 0.95 / 0.30 = 69.67 kWh -> 90.5 % of 77."""
    for i in range(25):      # 25 samples would be 'high' by count; the loss factor is assumed, so medium at most
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=i + 1), 2, 40, 70, kw=11.0)
    async with replay_sessionmaker() as s:
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.sample_count == 25 and r.confidence == "medium"
    assert abs(r.extra["median_kwh"] - 69.67) < 0.05 and abs(r.soh_pct - 90.48) < 0.1
    assert "integrated" in r.inputs["energy_source"]


@pytest.mark.asyncio
async def test_sessions_that_cannot_be_measured_are_skipped_for_a_named_reason(replay_sessionmaker, vehicle_id):
    base = NOW - timedelta(days=1)
    await _session(replay_sessionmaker, vehicle_id, base, 2, 40, 70, kw=11.0)                        # good
    await _session(replay_sessionmaker, vehicle_id, base - timedelta(days=1), 2, 40, 70, kw=11.0, cover=0.5)   # half covered
    await _session(replay_sessionmaker, vehicle_id, base - timedelta(days=2), 3, 50, 100, kw=11.0)   # to 100 %: taper
    await _session(replay_sessionmaker, vehicle_id, base - timedelta(days=3), 0.2, 60, 70, kw=11.0)  # 12 min
    await _session(replay_sessionmaker, vehicle_id, base - timedelta(days=4), 2, 40, 70, kw=3.0)     # 6 kWh for 30 %: disagrees
    async with replay_sessionmaker() as s:
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.sample_count == 1
    assert r.inputs["skipped"] == {"no_power_readings": 0, "low_coverage": 1, "small_or_short": 1, "taper": 1, "disagrees_with_soc": 1}


async def _ranges(sm, vid, days_ago: list[int], km=400.0):
    async with sm() as s:
        d = Drive(user_vehicle_id=vid, type='electric')
        s.add(d)
        await s.flush()
        for i, n in enumerate(days_ago):          # (drive_id, first_date) is unique: spread same-day samples by minutes
            ts = NOW - timedelta(days=n, minutes=i % 7)
            s.add(DriveRangeEstimatedFull(drive_id=d.id, first_date=ts, last_date=ts, range_estimated_full=km))
        await s.commit()


@pytest.mark.asyncio
async def test_range_drift_explains_a_short_data_span_instead_of_no_data_in_first_or_second_half(replay_sessionmaker, vehicle_id):
    """11,982 samples over 70 days in a 365-day window: all were in the window's second half."""
    await _ranges(replay_sessionmaker, vehicle_id, [n for n in range(1, 71) for _ in range(3)])   # 210 samples, 70 days
    async with replay_sessionmaker() as s:
        r = await bh.estimate_range_drift_over_time(s, vehicle_id, lookback_days=365)
    assert r.soh_pct is None and r.sample_count == 210
    assert "span only 69 days" in r.inputs["reason"] and r.inputs["samples_first_half"] > 0 and r.inputs["samples_second_half"] > 0
    # the reporter asked how the samples fall between the halves: the reason names both counts and median days
    assert "105 in the earlier half" in r.inputs["reason"] and "105 in the later half" in r.inputs["reason"]
    assert r.inputs["first_half_median_date"] < r.inputs["second_half_median_date"]


@pytest.mark.asyncio
async def test_range_drift_splits_the_data_itself_when_it_spans_long_enough(replay_sessionmaker, vehicle_id):
    await _ranges(replay_sessionmaker, vehicle_id, [n for n in range(100, 160) for _ in range(2)], km=420.0)   # earlier: 420 km
    await _ranges(replay_sessionmaker, vehicle_id, [n for n in range(1, 61) for _ in range(2)], km=400.0)      # later: 400 km
    async with replay_sessionmaker() as s:
        r = await bh.estimate_range_drift_over_time(s, vehicle_id, lookback_days=365)
    assert r.soh_pct is not None and abs(r.extra["retention_pct"] - 95.24) < 0.1
    assert r.inputs["halves_apart_days"] >= 60


@pytest.mark.asyncio
async def test_a_method_with_no_result_is_stored_as_null_not_zero(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        analytics = await bh.compute_full_analytics(s, vehicle_id, lookback_days=180)
        await bh.persist_analytics(s, analytics)
        rows = (await s.execute(select(BatteryHealthAnalytics).where(BatteryHealthAnalytics.user_vehicle_id == vehicle_id))).scalars().all()
    by = {r.method: r for r in rows}
    assert by["tesla_capacity"].soh_pct is None and by["combined"].soh_pct is None
    assert by["combined"].extra_json["lookback_days"] == 180
    assert by["tesla_capacity"].inputs_json["reason"]
    assert analytics.methods[0].to_dict()["reason"]        # the API also says why


def test_cached_result_is_reused_only_when_recent_and_for_the_same_window():
    now = NOW
    fresh = SimpleNamespace(computed_at=now - timedelta(hours=3), extra_json={"lookback_days": 365})
    assert _cache_is_fresh(fresh, 365, now) is True
    assert _cache_is_fresh(fresh, 180, now) is False                                   # different window
    old = SimpleNamespace(computed_at=now - timedelta(days=56), extra_json={"lookback_days": 365})
    assert _cache_is_fresh(old, 365, now) is False                                     # September result in November
    legacy = SimpleNamespace(computed_at=now - timedelta(hours=1), extra_json={"anomalies": []})
    assert _cache_is_fresh(legacy, 365, now) is False                                  # written before lookback was recorded


@pytest.mark.asyncio
async def test_capacity_above_nominal_is_no_result_not_a_clamped_100_percent(replay_sessionmaker, vehicle_id):
    """QA vehicle b28fdf22: integrated energy 12 % above the SoC figure -> median 81.6 kWh of 77 -> was '100.00 %'."""
    for i in range(8):
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=i + 1), 2, 40, 70, kw=13.0)   # 26 kWh for 30 %
    async with replay_sessionmaker() as s:
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.soh_pct is None and r.sample_count == 8 and "above the 77 kWh" in r.inputs["reason"]


@pytest.mark.asyncio
async def test_fewer_than_five_usable_sessions_give_no_capacity_result(replay_sessionmaker, vehicle_id):
    for i in range(4):
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=i + 1), 2, 40, 70, kw=11.0)
    async with replay_sessionmaker() as s:
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.soh_pct is None and "need 5" in r.inputs["reason"]


@pytest.mark.asyncio
async def test_widely_disagreeing_sessions_drop_capacity_confidence_to_low(replay_sessionmaker, vehicle_id):
    for i, kw in enumerate([11.0, 11.0, 11.0, 8.8, 8.8, 8.8]):     # 69.7 vs 55.7 kWh: spread 14 kWh < 19.25 -> keep medium
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=i + 1), 2, 40, 70, kw=kw)
    async with replay_sessionmaker() as s:
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.soh_pct is not None and r.confidence == "medium"
    for i, kw in enumerate([12.5, 12.5]):                            # 79.2 kWh samples (ratio 1.08, under nominal + 3 %): spread 23.5 > 19.25 -> low
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=20 + i), 2, 40, 70, kw=kw)
    async with replay_sessionmaker() as s:
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.confidence == "low" and r.inputs["spread_kwh"] > 19.25


@pytest.mark.asyncio
async def test_a_range_rise_between_the_halves_is_not_reported_as_100_percent_health(replay_sessionmaker, vehicle_id):
    """QA vehicle: 559 -> 591 km (+5.7 %) was shown as 100.00 % with HIGH confidence."""
    await _ranges(replay_sessionmaker, vehicle_id, [n for n in range(100, 160) for _ in range(2)], km=559.0)
    await _ranges(replay_sessionmaker, vehicle_id, [n for n in range(1, 61) for _ in range(2)], km=591.0)
    async with replay_sessionmaker() as s:
        r = await bh.estimate_range_drift_over_time(s, vehicle_id, lookback_days=365)
    assert r.soh_pct is None and "rose from 559 to 591 km" in r.inputs["reason"] and r.extra["retention_pct"] > 105


@pytest.mark.asyncio
async def test_capacity_reads_the_power_readings_once_not_once_per_session(replay_sessionmaker, vehicle_id):
    """Review of #221: the power readings were queried per session (N+1). Now: the sessions and
    the readings - two statements whatever the number of sessions (the vehicle is a db.get), and
    the same figures."""
    for i in range(12):
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=i + 1), 2, 40, 70, kw=11.0)
    async with replay_sessionmaker() as s:
        statements = []
        execute = s.execute

        async def counted(stmt, *a, **kw):
            statements.append(str(stmt))
            return await execute(stmt, *a, **kw)

        s.execute = counted
        r = await bh.estimate_tesla_capacity(s, vehicle_id)
    assert r.sample_count == 12 and abs(r.extra["median_kwh"] - 69.67) < 0.05
    assert len(statements) == 2, f"{len(statements)} statements for 12 sessions"
    assert sum("charging_states" in q for q in statements) == 1


@pytest.mark.asyncio
async def test_methods_without_a_data_source_say_which_source_is_missing(replay_sessionmaker, vehicle_id):
    """Taper, cell imbalance and fleet benchmark said "no ... in lookback", which reads as a gap a
    longer window would fill. The Skoda API has no cell voltages, an AC-only car has no DC samples,
    and a one-car server has no peers; the reason now says which."""
    async with replay_sessionmaker() as s:
        for i in range(3):
            s.add(BatteryHealth(user_vehicle_id=vehicle_id, captured_at=NOW - timedelta(hours=i), imbalance_mv=None))
            s.add(ChargingCurve(user_vehicle_id=vehicle_id, captured_at=NOW - timedelta(hours=i), soc_pct=50.0 + i, power_kw=11.0))
        (await s.get(UserVehicle, vehicle_id)).model_year = "2026"
        await s.commit()
    async with replay_sessionmaker() as s:
        taper = await bh.estimate_charging_curve_taper(s, vehicle_id)
        imbalance = await bh.estimate_cell_imbalance(s, vehicle_id)
        fleet = await bh.estimate_fleet_benchmark(s, vehicle_id)
    assert taper.soh_pct is None and "3 charging power samples in lookback, all AC" in taper.inputs["reason"]
    assert imbalance.soh_pct is None and "does not report cell voltages" in imbalance.inputs["reason"]
    assert imbalance.inputs["readings_without_cell_data"] == 3
    assert fleet.soh_pct is None and "only one vehicle" in fleet.inputs["reason"] and fleet.inputs["other_vehicles"] == 0


@pytest.mark.asyncio
async def test_daily_recompute_refreshes_the_rows_the_battery_soh_page_reads(replay_sessionmaker, vehicle_id, monkeypatch):
    """The 03:30 job wrote the ops model only (battery_soh_estimates); the page reads
    battery_health_analytics, so its stored result aged until someone opened the page."""
    now = datetime.now(timezone.utc)
    for i in range(6):
        await _session(replay_sessionmaker, vehicle_id, now - timedelta(hours=6 * (i + 1)), 2, 40, 70, kw=11.0)

    async def _ops_model_stub(db, vid, capacity_kwh, lookback_days):   # the ops tables are raw-SQL migrations, absent from the scratch DB
        return None

    monkeypatch.setattr(battery_scheduler, "compute_and_store_estimate", _ops_model_stub)
    assert await battery_scheduler.job_daily_recompute(session_factory=replay_sessionmaker) == {"recomputed": 1, "failed": 0}
    async with replay_sessionmaker() as s:
        rows = (await s.execute(select(BatteryHealthAnalytics).where(BatteryHealthAnalytics.user_vehicle_id == vehicle_id)
                                .where(BatteryHealthAnalytics.method == "combined"))).scalars().all()
    assert len(rows) == 1 and rows[0].extra_json["lookback_days"] == 365
    assert rows[0].soh_pct is not None and abs(rows[0].soh_pct - 90.48) < 0.1
    assert _cache_is_fresh(rows[0], 365)      # the page will reuse it tomorrow morning instead of recomputing


@pytest.mark.asyncio
async def test_ops_model_capacity_method_no_longer_returns_the_configured_capacity(replay_sessionmaker, vehicle_id):
    """battery_soh.estimate_capacity_based (admin page, monthly Passport) divided energy_kwh = SoC x 77 by
    the SoC delta: any 8 sessions gave 77 x 0.95 -> 95.0 % with HIGH confidence. It now takes the
    measured path: nothing without power readings, the integrated figure with them."""
    for i in range(8):
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=i + 1), 2, 40, 70)
    async with replay_sessionmaker() as s:
        assert await battery_soh.estimate_capacity_based(s, vehicle_id, 77.0) is None
    for i in range(8):
        await _session(replay_sessionmaker, vehicle_id, NOW - timedelta(days=20 + i), 2, 40, 70, kw=11.0)
    async with replay_sessionmaker() as s:
        r = await battery_soh.estimate_capacity_based(s, vehicle_id, 77.0)
    assert r is not None and abs(r.soh_pct - 90.48) < 0.1 and r.confidence == "medium"
    assert abs(r.estimated_kwh - 69.67) < 0.05 and r.sample_count == 8
    assert r.inputs["source"] == "battery_health_v2.estimate_tesla_capacity"


@pytest.mark.asyncio
async def test_legacy_battery_health_endpoint_serves_a_stored_no_result_without_crashing(replay_sessionmaker, vehicle_id):
    """/analytics/battery-health did float(cached.soh_pct) on the stored combined row: once a method-less
    vehicle stores NULL, that was a TypeError (500). It also kept a result for a week, not a day."""
    async with replay_sessionmaker() as s:
        analytics = await bh.compute_full_analytics(s, vehicle_id, lookback_days=365)
        await bh.persist_analytics(s, analytics)
        user_id = (await s.get(UserVehicle, vehicle_id)).user_id
    async with replay_sessionmaker() as s:
        out = await analytics_api.get_battery_health(vehicle_id, db=s, user=SimpleNamespace(id=user_id))
    assert out["derived_soh_pct"] is None and out["derived_capacity_kwh"] is None
    assert out["derived_source"] == "battery_health_analytics" and out["curve"] == []
    # a stored result older than a day is not reused by this endpoint either
    async with replay_sessionmaker() as s:
        row = (await s.execute(select(BatteryHealthAnalytics).where(BatteryHealthAnalytics.method == "combined"))).scalar_one()
        row.computed_at = datetime.now(timezone.utc) - timedelta(days=3)
        await s.commit()
    async with replay_sessionmaker() as s:
        out = await analytics_api.get_battery_health(vehicle_id, db=s, user=SimpleNamespace(id=user_id))
    assert out["derived_source"] == "v2_live_compute"
