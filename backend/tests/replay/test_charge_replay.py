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


# ── v1.3.8: driving ends a charging session ─────────────────────────────────────────────

def _charge_then_idle_cable() -> list[Poll]:
    """08:00-09:00 charging 60 -> 80 %, then the car idles in CONNECT_CABLE (Skoda's idle state)."""
    polls = []
    for i, p in enumerate(every("08:00", "09:00", 5, charge_state="CHARGING", power_kw=7.0, odometer=1000)):
        p.soc = 60 + min(20, i * 2)
        polls.append(p)
    polls += every("09:05", "09:10", 5, charge_state="CONNECT_CABLE", power_kw=0.0, soc=80, odometer=1000)
    return polls


@pytest.mark.asyncio
async def test_driving_away_closes_the_session_at_once_with_the_charging_level(replay_sessionmaker, vehicle_id):
    polls = _charge_then_idle_cable() + [
        Poll(t("09:15"), moving=True, charge_state="CONNECT_CABLE", power_kw=0.0, soc=79, odometer=1003),
        Poll(t("09:20"), moving=True, charge_state="CONNECT_CABLE", power_kw=0.0, soc=77, odometer=1008),
        Poll(t("09:25"), moving=False, charge_state="CONNECT_CABLE", power_kw=0.0, soc=76, odometer=1010),
    ]
    await replay(replay_sessionmaker, vehicle_id, polls[:-3])
    await replay(replay_sessionmaker, vehicle_id, polls[-3:-2])
    (s1,) = await sessions(replay_sessionmaker, vehicle_id)
    assert s1.session_end is not None, "still open after the car started driving"   # closed on the first moving poll
    await replay(replay_sessionmaker, vehicle_id, polls[-2:])
    (s,) = await sessions(replay_sessionmaker, vehicle_id)
    assert (s.start_level, s.end_level) == (60, 80)      # not dragged down by the drive (79, 77, 76)
    assert s.session_end <= t("09:15")


@pytest.mark.asyncio
async def test_drive_missed_by_the_poller_still_closes_via_odometer(replay_sessionmaker, vehicle_id):
    """Parked polls are 30 min apart; the trip can start and end between two of them."""
    polls = _charge_then_idle_cable() + [
        Poll(t("09:25"), moving=False, charge_state="CONNECT_CABLE", power_kw=0.0, soc=74, odometer=1012),
    ]
    await replay(replay_sessionmaker, vehicle_id, polls)
    (s,) = await sessions(replay_sessionmaker, vehicle_id)
    assert s.session_end is not None and s.end_level == 80


@pytest.mark.asyncio
async def test_a_moving_flicker_during_real_charging_does_not_split_the_session(replay_sessionmaker, vehicle_id):
    polls = []
    for i, p in enumerate(every("08:00", "09:00", 5, charge_state="CHARGING", power_kw=7.0, odometer=1000)):
        p.soc = 60 + min(20, i * 2)
        p.moving = (i == 5)            # one spurious "moving" flag while the car is charging
        polls.append(p)
    await replay(replay_sessionmaker, vehicle_id, polls)
    got = await sessions(replay_sessionmaker, vehicle_id)
    assert len(got) == 1 and got[0].end_level == 80


@pytest.mark.asyncio
async def test_a_new_charge_after_the_drive_is_a_new_session(replay_sessionmaker, vehicle_id):
    polls = _charge_then_idle_cable() + [
        Poll(t("09:15"), moving=True, charge_state="CONNECT_CABLE", power_kw=0.0, soc=79, odometer=1003),
        Poll(t("09:25"), moving=False, charge_state="CONNECT_CABLE", power_kw=0.0, soc=77, odometer=1010),
    ]
    for i, p in enumerate(every("18:00", "18:40", 5, charge_state="CHARGING", power_kw=7.0, odometer=1010)):
        p.soc = 70 + i * 2
        polls.append(p)
    await replay(replay_sessionmaker, vehicle_id, polls)
    got = await sessions(replay_sessionmaker, vehicle_id)
    assert len(got) == 2 and got[0].end_level == 80 and got[1].start_level == 70


@pytest.mark.asyncio
async def test_stale_charging_row_while_driving_does_not_keep_the_session_open(replay_sessionmaker, vehicle_id):
    """Skoda sends no charging state while the car drives: the last 'CHARGING' row just goes stale."""
    polls = []
    for i, p in enumerate(every("08:00", "09:00", 5, charge_state="CHARGING", power_kw=7.0, odometer=1000)):
        p.soc = 60 + min(20, i * 2)
        polls.append(p)
    polls += [Poll(t("09:30"), moving=True, charge_state=None, odometer=1004),
              Poll(t("09:35"), moving=True, charge_state=None, odometer=1010)]
    await replay(replay_sessionmaker, vehicle_id, polls)
    (s,) = await sessions(replay_sessionmaker, vehicle_id)
    assert s.session_end is not None and s.end_level == 80
