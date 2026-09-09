from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services.charging_plans import (
    add_months,
    add_period,
    charger_payable_eur,
    count_overlapping_periods,
    haversine_m,
    included_allotment_kwh,
    kwh_before_session,
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


def test_eborn_session_allocates_period_fee():
    cost, reason = session_cost_from_remaining(
        22.92, remaining_kwh=300.0, overage_rate=0.59, included_rate=100 / 300
    )
    assert cost == 7.64
    assert reason == "within_allotment"
    assert charger_payable_eur(22.92, 300.0, 0.59) == 0.0


def test_session_cost_mixed_allotment_and_overage():
    cost, reason = session_cost_from_remaining(
        40.0, remaining_kwh=10.0, overage_rate=0.31, included_rate=0.33
    )
    assert cost == round(10 * 0.33 + 30 * 0.31, 2)
    assert reason == "mixed"
    assert charger_payable_eur(40.0, 10.0, 0.31) == 9.3


def test_session_cost_full_overage():
    cost, reason = session_cost_from_remaining(
        40.0, remaining_kwh=0.0, overage_rate=0.59, included_rate=100 / 300
    )
    assert cost == 23.6
    assert reason == "overage"


def test_extra_kwh_falls_back_to_included_rate_without_walk_up():
    cost, reason = session_cost_from_remaining(
        40.0, remaining_kwh=10.0, overage_rate=None, included_rate=0.33
    )
    assert cost == round(10 * 0.33 + 30 * 0.33, 2)
    assert reason == "mixed"


def test_kwh_before_ignores_later_sessions():
    early = SimpleNamespace(
        id=1, session_start=datetime(2026, 9, 4, tzinfo=timezone.utc), energy_kwh=22.92
    )
    late = SimpleNamespace(
        id=2, session_start=datetime(2026, 9, 8, tzinfo=timezone.utc), energy_kwh=280.0
    )
    assert kwh_before_session([early, late], early) == 0.0
    assert kwh_before_session([early, late], late) == 22.92


def test_included_allotment_treats_zero_as_missing():
    assert included_allotment_kwh(SimpleNamespace(kwh_allotment=0)) is None
    assert included_allotment_kwh(SimpleNamespace(kwh_allotment=300)) == 300.0


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
