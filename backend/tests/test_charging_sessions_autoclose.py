"""Auto-close rules for open charging sessions — long AC must stay open."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.analytics import should_close_open_session

UTC = timezone.utc


def test_keeps_open_while_actively_charging_low_power():
    # 1–2 kW overnight AC must NOT auto-close
    assert should_close_open_session(
        state="CONNECT_CABLE",
        charge_power_kw=1.5,
        last_soc=62.0,
        new_soc=63.0,
        last_activity_at=datetime(2026, 10, 24, 22, 0, tzinfo=UTC),
        now=datetime(2026, 10, 25, 12, 0, tzinfo=UTC),
    ) is False


def test_closes_when_unplugged():
    assert should_close_open_session(
        state="DISCONNECTED",
        charge_power_kw=None,
        last_soc=80.0,
        new_soc=80.0,
        last_activity_at=datetime(2026, 10, 24, 22, 0, tzinfo=UTC),
        now=datetime(2026, 10, 24, 23, 0, tzinfo=UTC),
    ) is True


def test_closes_when_finished_but_cable_still_in():
    # CONNECT_CABLE + 0 kW + SoC flat for > 30 min = charge done
    assert should_close_open_session(
        state="CONNECT_CABLE",
        charge_power_kw=0.0,
        last_soc=100.0,
        new_soc=100.0,
        last_activity_at=datetime(2026, 10, 24, 23, 0, tzinfo=UTC),
        now=datetime(2026, 10, 25, 8, 0, tzinfo=UTC),
    ) is True


def test_does_not_close_on_time_alone_if_power_flowing():
    assert should_close_open_session(
        state="CHARGING",
        charge_power_kw=2.0,
        last_soc=40.0,
        new_soc=55.0,
        last_activity_at=datetime(2026, 10, 24, 20, 0, tzinfo=UTC),
        now=datetime(2026, 10, 25, 10, 0, tzinfo=UTC),
    ) is False


def test_new_charge_after_gap_closes_old():
    # helper returns True → caller closes old and opens new
    assert should_close_open_session(
        state="CHARGING",
        charge_power_kw=7.0,
        last_soc=80.0,
        new_soc=20.0,
        last_activity_at=datetime(2026, 10, 23, 22, 0, tzinfo=UTC),
        now=datetime(2026, 10, 25, 18, 0, tzinfo=UTC),
    ) is True


def test_zero_soc_is_valid_last_level():
    # 0% must not be treated as missing
    assert should_close_open_session(
        state="DISCONNECTED",
        charge_power_kw=None,
        last_soc=0.0,
        new_soc=0.0,
        last_activity_at=datetime(2026, 10, 24, 22, 0, tzinfo=UTC),
        now=datetime(2026, 10, 24, 23, 0, tzinfo=UTC),
    ) is True


def test_naive_db_timestamp_with_aware_now_does_not_crash():
    # DB may return naive datetimes; comparison must not raise TypeError
    assert should_close_open_session(
        state="CONNECT_CABLE",
        charge_power_kw=0.0,
        last_soc=100.0,
        new_soc=100.0,
        last_activity_at=datetime(2026, 10, 24, 23, 0),  # naive
        now=datetime(2026, 10, 25, 8, 0, tzinfo=UTC),  # aware
    ) is True


from app.services.analytics import should_start_session


def test_cable_only_at_zero_kw_does_not_start_session():
    for state in ("CONNECT_CABLE", "CONSERVING", "READY_FOR_CHARGING", "CHARGING_INTERRUPTED"):
        assert should_start_session(
            state=state, charge_power_kw=0.0, new_soc=97.0, prev_soc=97.0
        ) is False


def test_parked_after_drive_with_lower_soc_does_not_start():
    assert should_start_session(
        state="CONNECT_CABLE", charge_power_kw=0.0, new_soc=90.0, prev_soc=97.0
    ) is False


def test_active_charging_starts_session():
    assert should_start_session(
        state="CHARGING", charge_power_kw=22.0, new_soc=40.0, prev_soc=40.0
    ) is True
    assert should_start_session(
        state="CONNECT_CABLE", charge_power_kw=1.4, new_soc=40.0, prev_soc=None
    ) is True


def test_home_ac_zero_kw_with_rising_soc_starts_session():
    assert should_start_session(
        state="CONNECT_CABLE", charge_power_kw=0.0, new_soc=63.0, prev_soc=62.0
    ) is True


def test_unplugged_never_starts():
    assert should_start_session(
        state="DISCONNECTED", charge_power_kw=5.0, new_soc=60.0, prev_soc=50.0
    ) is False
