"""Unit tests for battery SoH estimation service.

Pure-Python tests for the helper functions (no DB required).
Integration tests against real charging data live in _local_docs/verify_soh.py.
"""

import statistics
from datetime import datetime, timezone

import pytest

from app.services.battery_soh import (
    SOC_DELTA_MIN,
    SOC_DELTA_MAX,
    CAPACITY_FLOOR_FRAC,
    CAPACITY_CEIL_FRAC,
    SOC_CALIBRATION_OFFSET_PCT,
    SOC_CALIBRATION_TRIGGER_PCT,
    _apply_soc_calibration,
    _apply_temperature_correction,
    _confidence_from_samples,
    MethodResult,
    aggregate_methods,
)


# ---------------------------------------------------------------------------
# _apply_soc_calibration
# ---------------------------------------------------------------------------


class TestSocCalibration:
    def test_end_level_above_trigger_gets_offset(self):
        # 98 → 96 (subtract 2%)
        assert _apply_soc_calibration(98.0) == 96.0
        assert _apply_soc_calibration(100.0) == 98.0

    def test_end_level_at_or_below_trigger_unchanged(self):
        assert _apply_soc_calibration(95.0) == 95.0
        assert _apply_soc_calibration(80.0) == 80.0
        assert _apply_soc_calibration(50.0) == 50.0

    def test_end_level_just_above_trigger(self):
        assert _apply_soc_calibration(95.1) == pytest.approx(93.1)


# ---------------------------------------------------------------------------
# _apply_temperature_correction
# ---------------------------------------------------------------------------


class TestTemperatureCorrection:
    def test_none_temp_passthrough(self):
        corrected, pct = _apply_temperature_correction(58.0, None)
        assert corrected == 58.0
        assert pct == 0.0

    def test_25c_reference_no_correction(self):
        corrected, pct = _apply_temperature_correction(58.0, 25.0)
        assert corrected == pytest.approx(58.0, rel=1e-6)
        assert pct == 0.0

    def test_cold_inflates_corrected_capacity(self):
        # 0°C: -25°C delta → +12.5% correction (we add back the cold loss)
        # corrected = raw / (1 - 0.125) = raw / 0.875 → BIGGER than measured
        corrected, pct = _apply_temperature_correction(50.0, 0.0)
        assert pct == pytest.approx(-12.5)  # signed: negative = added back
        assert corrected == pytest.approx(50.0 / 0.875, rel=1e-6)
        assert corrected > 50.0  # CRITICAL: cold should INFLATE, not deflate

    def test_hot_deflates_corrected_capacity(self):
        # 40°C: +15°C delta → +7.5% correction
        # corrected = raw / (1 + 0.075) = raw / 1.075 → SMALLER than measured
        corrected, pct = _apply_temperature_correction(60.0, 40.0)
        assert pct == pytest.approx(7.5)  # signed: positive = we subtracted
        assert corrected == pytest.approx(60.0 / 1.075, rel=1e-6)
        assert corrected < 60.0  # CRITICAL: hot should DEFLATE

    def test_zero_correction_factor_protected(self):
        # Extreme cold where correction factor goes ≤ 0
        # delta_t = -250, correction_pct = -125, factor = 1 - (-1.25) = 2.25 > 0
        # So actually no division-by-zero here, just very large correction.
        corrected, pct = _apply_temperature_correction(58.0, -200.0)
        assert corrected > 0  # never returns non-positive


# ---------------------------------------------------------------------------
# _confidence_from_samples
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_high(self):
        assert _confidence_from_samples(8) == "high"
        assert _confidence_from_samples(50) == "high"

    def test_medium(self):
        assert _confidence_from_samples(3) == "medium"
        assert _confidence_from_samples(7) == "medium"

    def test_low(self):
        assert _confidence_from_samples(0) == "low"
        assert _confidence_from_samples(2) == "low"


# ---------------------------------------------------------------------------
# aggregate_methods
# ---------------------------------------------------------------------------


def _make(method: str, soh: float, samples: int = 10) -> MethodResult:
    return MethodResult(
        method=method,
        soh_pct=soh,
        estimated_kwh=soh * 0.58,  # for factory_kwh=58
        sample_count=samples,
        confidence=_confidence_from_samples(samples),
        inputs={},
        monthly_breakdown=[],
    )


class TestAggregate:
    def test_no_methods_returns_none(self):
        assert aggregate_methods([]) is None

    def test_single_method_returns_same_value(self):
        cap = _make("capacity", 95.0)
        agg = aggregate_methods([cap])
        assert agg.method == "aggregate"
        assert agg.soh_pct == 95.0
        assert agg.estimated_kwh == pytest.approx(55.1)

    def test_weighted_median_capacity_dominates(self):
        # capacity weight 2, throughput weight 1
        # Sorted by SoH: [90, 95, 100]
        # Weights:        [1,  2,  1]
        # Total weight: 4, half = 2
        # Cumulative:     1,  3 → median = 95 (capacity dominates)
        cap = _make("capacity", 95.0)
        thr = _make("throughput", 90.0)
        res = _make("resistance", 100.0)
        agg = aggregate_methods([thr, cap, res])
        assert agg.soh_pct == 95.0

    def test_confidence_uses_min_of_methods(self):
        # Aggregate is conservative — MIN confidence wins.
        # (Previously used max-by-sample-count, which let high-sample
        # throughput mask low-sample capacity. That was misleading.)
        high = _make("capacity", 95.0, samples=20)
        low = _make("throughput", 99.0, samples=2)
        agg = aggregate_methods([high, low])
        assert agg.confidence == "low"

    def test_capacity_kwh_propagated_to_aggregate(self):
        cap = _make("capacity", 95.0)
        thr = _make("throughput", 99.0)
        agg = aggregate_methods([cap, thr])
        assert agg.estimated_kwh == pytest.approx(cap.estimated_kwh)

    def test_throughput_only_aggregate_has_no_kwh(self):
        thr = _make("throughput", 99.0)
        agg = aggregate_methods([thr])
        assert agg.estimated_kwh is None


# ---------------------------------------------------------------------------
# Constants sanity (regression guards against accidental tuning)
# ---------------------------------------------------------------------------


class TestConstants:
    def test_soc_window_sensible(self):
        assert 10 <= SOC_DELTA_MIN <= 20
        assert SOC_DELTA_MAX <= 70
        assert SOC_DELTA_MIN < SOC_DELTA_MAX

    def test_outlier_bounds_sensible(self):
        assert 0.7 <= CAPACITY_FLOOR_FRAC <= 0.9
        assert 1.0 <= CAPACITY_CEIL_FRAC <= 1.1

    def test_soc_calibration_values_sensible(self):
        assert 0 < SOC_CALIBRATION_OFFSET_PCT <= 5
        assert SOC_CALIBRATION_TRIGGER_PCT >= 90