"""Unit tests for trip-gap vampire drain (no DB)."""

from datetime import datetime, timedelta, timezone

from app.services.vampire_drain import (
    ChargeWindow,
    TripEndpoint,
    compute_vampire_drain,
)

UTC = timezone.utc
T0 = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)


def _trip(
    start_hours: float,
    duration_hours: float,
    start_soc: float,
    end_soc: float,
    start_odo: float,
    end_odo: float,
) -> TripEndpoint:
    start = T0 + timedelta(hours=start_hours)
    return TripEndpoint(
        start=start,
        end=start + timedelta(hours=duration_hours),
        start_soc=start_soc,
        end_soc=end_soc,
        start_odometer=start_odo,
        end_odometer=end_odo,
    )


def test_no_trips_is_unknown():
    stats = compute_vampire_drain([])
    assert stats.has_data is False
    assert stats.sample_count == 0
    assert stats.avg_drain_pct_per_day == 0.0


def test_hour_weighted_includes_zero_drop_nights():
    trips = [
        _trip(0, 1, 85, 80, 1000, 1010),
        _trip(15, 1, 80, 75, 1010, 1020),  # 14 h parked, 80→80
        _trip(26, 1, 74, 70, 1020, 1030),  # 10 h parked, 75→74
    ]
    stats = compute_vampire_drain(trips)
    assert stats.has_data is True
    assert stats.sample_count == 2
    assert stats.zero_drop_count == 1
    # (0*14 + 1*10) / 24 h parked * 24 = 1.0%/day
    assert stats.avg_drain_pct_per_day == 1.0
    assert stats.parked_hours == 24.0


def test_odo_movement_excluded():
    trips = [
        _trip(0, 1, 80, 70, 1000, 1010),
        _trip(15, 1, 69, 60, 1018, 1030),  # +8 km while "parked"
    ]
    stats = compute_vampire_drain(trips)
    assert stats.has_data is False


def test_charging_overlap_excluded():
    trips = [
        _trip(0, 1, 40, 35, 1000, 1010),
        _trip(15, 1, 80, 70, 1010, 1020),
    ]
    charges = [
        ChargeWindow(
            start=T0 + timedelta(hours=2),
            end=T0 + timedelta(hours=5),
        )
    ]
    stats = compute_vampire_drain(trips, charges)
    assert stats.has_data is False


def test_open_ended_charge_started_just_before_park_excluded():
    trips = [
        _trip(0, 1, 40, 35, 1000, 1010),
        _trip(15, 1, 80, 70, 1010, 1020),
    ]
    # Unclosed session that started during the previous trip
    charges = [ChargeWindow(start=T0 + timedelta(minutes=30), end=None)]
    stats = compute_vampire_drain(trips, charges)
    assert stats.has_data is False


def test_open_ended_charge_during_park_excluded():
    trips = [
        _trip(0, 1, 40, 35, 1000, 1010),
        _trip(15, 1, 80, 70, 1010, 1020),
    ]
    charges = [ChargeWindow(start=T0 + timedelta(hours=3), end=None)]
    stats = compute_vampire_drain(trips, charges)
    assert stats.has_data is False


def test_short_park_below_minimum_excluded():
    trips = [
        _trip(0, 1, 80, 70, 1000, 1010),
        _trip(1.5, 1, 69, 60, 1010, 1020),  # 0.5 h parked
    ]
    stats = compute_vampire_drain(trips)
    assert stats.has_data is False


def test_integer_soc_tick_while_stationary_is_kept():
    # 1% over 2 h with no odometer change is SoC granularity, not a missed drive.
    trips = [
        _trip(0, 1, 80, 70, 1000, 1010),
        _trip(3, 1, 69, 60, 1010, 1020),
    ]
    stats = compute_vampire_drain(trips)
    assert stats.has_data is True
    assert stats.sample_count == 1
    assert stats.avg_drain_pct_per_day == 12.0  # 1% / 2 h * 24


def test_missing_odometer_excluded():
    trips = [
        TripEndpoint(
            start=T0,
            end=T0 + timedelta(hours=1),
            start_soc=80,
            end_soc=70,
            start_odometer=1000,
            end_odometer=None,
        ),
        TripEndpoint(
            start=T0 + timedelta(hours=15),
            end=T0 + timedelta(hours=16),
            start_soc=70,
            end_soc=60,
            start_odometer=1000,
            end_odometer=1010,
        ),
    ]
    stats = compute_vampire_drain(trips)
    assert stats.has_data is False


def test_bms_rounding_gain_does_not_poison_rate():
    trips = [
        _trip(0, 1, 80, 70, 1000, 1010),
        _trip(15, 1, 71, 60, 1010, 1020),  # -1% "gain" over 13 h
    ]
    stats = compute_vampire_drain(trips)
    assert stats.has_data is True
    assert stats.avg_drain_pct_per_day == 0.0  # clamped, not negative
