from datetime import date

from app.services.charging_plans import (
    add_months,
    add_period,
    count_overlapping_periods,
    haversine_m,
    period_containing,
    session_cost_from_remaining,
    validate_plan_fields,
)


def test_add_months_clips_end_of_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)


def test_add_period_yearly():
    assert add_period(date(2026, 3, 1), "yearly") == date(2027, 3, 1)
    assert add_period(date(2026, 3, 1), "monthly") == date(2026, 4, 1)


def test_period_containing_anniversary():
    start = date(2026, 1, 15)
    period = period_containing(start, "monthly", date(2026, 2, 10))
    assert period == (date(2026, 1, 15), date(2026, 2, 15))
    assert period_containing(start, "monthly", date(2025, 12, 1)) is None


def test_count_overlapping_periods_one_month_window():
    # Window 1 Feb–1 Mar overlaps both [15 Jan, 15 Feb) and [15 Feb, 15 Mar).
    count = count_overlapping_periods(
        date(2026, 1, 15),
        "monthly",
        date(2026, 2, 1),
        date(2026, 3, 1),
        today=date(2026, 6, 1),
    )
    assert count == 2


def test_session_cost_within_allotment_is_zero():
    cost, reason = session_cost_from_remaining(40.0, remaining_kwh=50.0, rate=0.31)
    assert cost == 0.0
    assert reason == "within_allotment"


def test_session_cost_overage_bills_excess_only():
    cost, reason = session_cost_from_remaining(40.0, remaining_kwh=10.0, rate=0.31)
    assert cost == 9.3
    assert reason == "overage"


def test_haversine_zero_for_same_point():
    assert haversine_m(48.85, 2.35, 48.85, 2.35) < 1


def test_validate_subscription_requires_allotment_or_rate():
    err = validate_plan_fields(
        "subscription",
        monthly_fee_eur=49,
        kwh_allotment=None,
        price_per_kwh_eur=None,
        subscription_start_date=date(2026, 1, 1),
        periodicity="monthly",
    )
    assert err is not None
    assert validate_plan_fields(
        "home",
        monthly_fee_eur=None,
        kwh_allotment=None,
        price_per_kwh_eur=0.20,
        subscription_start_date=None,
        periodicity=None,
    ) is None
