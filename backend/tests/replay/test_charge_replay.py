"""#205 / #198 - one charge = one ChargingSession, whatever the post-target state looks like."""

import pytest

from .conftest import *  # noqa: F401,F403  (fixtures)
from .replay import Poll, every, replay, sessions, t


def _charge_32_to_80() -> list[Poll]:
    """08:14 -> 17:30, SoC 32 -> 80 at 7 kW, 5-min active polls."""
    polls, soc = [], 32.0
    cur = t("08:14")
    polls.append(Poll(cur, charge_state="READY_FOR_CHARGING", power_kw=0, soc=32, odometer=1000))
    for p in every("08:19", "17:30", 5, charge_state="CHARGING", power_kw=7.0, odometer=1000):
        soc = min(80.0, soc + 48.0 / 110)
        p.soc = int(soc)
        polls.append(p)
    polls[-1].soc = 79  # SoC ticks to 80 only on the first post-charge poll (state change)
    return polls


@pytest.mark.asyncio
@pytest.mark.parametrize("after_state,power", [
    ("CONNECT_CABLE", 0.0),
    ("CONSERVING", 0.0),
    ("CHARGING", 0.0),        # some firmwares keep CHARGING at 0 kW
    ("READY_FOR_CHARGING", 0.0),
])
async def test_205_target_reached_cable_still_in_is_single_session(
    replay_sessionmaker, vehicle_id, after_state, power
):
    polls = _charge_32_to_80()
    polls += every("17:35", "19:15", 5, charge_state=after_state, power_kw=power, soc=80, odometer=1000)
    polls += every("19:20", "19:40", 5, charge_state="DISCONNECTED", power_kw=None, soc=80, odometer=1000)
    await replay(replay_sessionmaker, vehicle_id, polls)
    got = await sessions(replay_sessionmaker, vehicle_id)
    assert len(got) == 1, [(s.session_start, s.session_end, s.start_level, s.end_level) for s in got]
    assert got[0].session_end is not None
    assert (got[0].start_level, got[0].end_level) == (32, 80)


@pytest.mark.asyncio
async def test_home_ac_reports_cable_at_zero_kw_while_soc_rises_stays_one_session(
    replay_sessionmaker, vehicle_id
):
    """Skoda home AC: CONNECT_CABLE, 0 kW for hours while SoC climbs ~1 %/15 min."""
    polls = [Poll(t("19:50"), charge_state="DISCONNECTED", soc=40)]
    for i, p in enumerate(every("20:00", "23:55", 5, charge_state="CONNECT_CABLE", power_kw=0.0)):
        p.soc = 40 + i // 3  # +1 % every 15 min
        polls.append(p)
    polls += every("00:00", "00:10", 5, charge_state="DISCONNECTED", soc=polls[-1].soc)
    polls = [p for p in polls]
    await replay(replay_sessionmaker, vehicle_id, polls)
    got = await sessions(replay_sessionmaker, vehicle_id)
    assert len(got) == 1, [(s.session_start, s.session_end, s.start_level, s.end_level) for s in got]
    assert got[0].end_level == polls[-1].soc  # live updates must not be rolled back


@pytest.mark.asyncio
async def test_no_flat_sessions_created_while_plugged_in_idle(replay_sessionmaker, vehicle_id):
    polls = every("08:00", "12:00", 5, charge_state="CONNECT_CABLE", power_kw=0.0, soc=80)
    await replay(replay_sessionmaker, vehicle_id, polls)
    assert await sessions(replay_sessionmaker, vehicle_id) == []


@pytest.mark.asyncio
async def test_next_zero_kw_home_charge_after_a_drive_is_a_new_session(replay_sessionmaker, vehicle_id):
    """Skoda has no DISCONNECTED state: an idle car sits in CONNECT_CABLE. The guard must
    not swallow the next 0 kW home charge just because a session already exists."""
    polls = [
        Poll(t("19:45"), charge_state="CHARGING_INTERRUPTED", power_kw=0.0, soc=40, odometer=500),
        Poll(t("19:50"), charge_state="CONNECT_CABLE", power_kw=0.0, soc=40, odometer=500),
    ]
    for i, p in enumerate(every("20:00", "21:55", 5, charge_state="CONNECT_CABLE", power_kw=0.0, odometer=500)):
        p.soc = 40 + i // 3
        polls.append(p)
    # next morning: drive (SoC falls), then evening charge again at 0 kW
    polls += [
        Poll(t("07:00", "2026-10-29"), moving=False, odometer=500, charge_state="CONNECT_CABLE", power_kw=0.0, soc=47),
        Poll(t("07:05", "2026-10-29"), moving=True, odometer=505, charge_state="CONNECT_CABLE", power_kw=0.0, soc=46),
        Poll(t("07:10", "2026-10-29"), moving=False, odometer=520, charge_state="CONNECT_CABLE", power_kw=0.0, soc=40),
    ]
    for i, p in enumerate(every("20:00", "21:55", 5, day="2026-10-29", charge_state="CONNECT_CABLE", power_kw=0.0, odometer=520)):
        p.soc = 40 + i // 3
        polls.append(p)
    await replay(replay_sessionmaker, vehicle_id, polls)
    got = await sessions(replay_sessionmaker, vehicle_id)
    assert len(got) == 2, [(s.session_start, s.start_level, s.end_level) for s in got]
