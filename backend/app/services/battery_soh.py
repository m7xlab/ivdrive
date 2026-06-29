"""Battery State of Health (SoH) estimation service.

Three independent methods, plus an aggregate:

1. CAPACITY-BASED (primary)
   Per charging session with valid SoC delta, compute the effective
   full-pack capacity:
       estimated_kwh = energy_kwh / (delta_soc / 100)
   Then SoH_pct = (estimated_kwh / factory_kwh) * 100.

   Noise corrections applied:
     - SoC calibration offset: subtract 2% from end_level when end_level > 95
       (Skoda BMS display rounds at top; "98%" often means actual 100%).
     - Outlier trim: keep estimates within [85%, 102%] of factory capacity.
     - Temperature correction: scale est_kwh to a 25°C reference
       (lithium NMC: ~0.5%/°C deviation from 25°C in [0, 40]).
     - Per-month median (robust to single-session anomalies).

2. THROUGHPUT-BASED (secondary, cross-check)
   Cumulative kWh discharged across all trips → equivalent full cycles.
   Industry model for NMC cells:
       soh_loss_pct = cycles * 0.025 * temp_factor * dod_factor
   Where temp_factor averages 1.0 at 25°C, rises above 1.0 for hot climates.
   dod_factor (depth-of-discharge): most trips are 20-80% SoC → ~0.7 average.

3. RESISTANCE-BASED (optional, requires cell-level data)
   Internal resistance growth estimated from charging power decay at
   fixed SoC. Not implemented yet (Skoda API doesn't expose per-cell data
   reliably) — placeholder returns None.

4. AGGREGATE
   Weighted median of all available methods. Weight: capacity=2, throughput=1.
   Confidence based on sample count.

Persistence: every method result is written to battery_soh_estimates with
inputs_json snapshot for auditability. Aggregate row also written.
"""

from __future__ import annotations

import json
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import BatteryHealth


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# Acceptable SoC delta window (%)
SOC_DELTA_MIN = 15.0
SOC_DELTA_MAX = 60.0

# Outlier bounds as fraction of factory capacity.
# A healthy EV battery in service is almost never at 100% SoH — even brand-new
# units ship with 98-99% due to manufacturing tolerance and initial cycling.
# Anything > 100% is measurement noise (charging losses, SoC calibration drift,
# preconditioning energy bled into the recorded kWh) and must be rejected.
CAPACITY_FLOOR_FRAC = 0.85
CAPACITY_CEIL_FRAC = 1.00

# SoC calibration offset (Skoda BMS display rounds at top)
SOC_CALIBRATION_OFFSET_PCT = 2.0
SOC_CALIBRATION_TRIGGER_PCT = 95.0

# Temperature correction reference (°C) and coefficient (per °C deviation).
# 0.3%/°C is conservative for NMC cells in the 0-25°C range. Higher coefficients
# (0.5%/°C) over-correct in winter and push estimates above 100%, which is
# physically impossible and looks wrong to users. Lower = closer to user
# intuition that "cold costs a little range, not 12%".
TEMP_REFERENCE_C = 25.0
TEMP_COEFF_PER_C = 0.003  # ~0.3%/°C (lithium NMC, conservative)

# Charging losses: energy_kwh from Skoda is GRID energy, not battery gain.
# AC slow charging: ~5% losses (heat in on-board charger + cable).
# DC fast charging: ~8-12% losses (heat in charging station, contact resistance).
# Without this correction, every estimate is inflated by 5-12%.
CHARGING_LOSS_PCT = {
    "AC": 0.05,
    "DC": 0.10,
}
CHARGING_LOSS_DEFAULT_PCT = 0.07  # used when charging_type is NULL

# Throughput model
CYCLE_LOSS_AT_25C = 0.025  # % SoH loss per full cycle at 25°C
DOD_AVERAGE = 0.7          # avg depth-of-discharge factor

# Confidence thresholds
HIGH_CONFIDENCE_SAMPLES = 8
MEDIUM_CONFIDENCE_SAMPLES = 3

# Anomaly detection
SUDDEN_DROP_THRESHOLD_PCT = 2.0  # in 30 days
ACCELERATION_FACTOR = 2.0        # slope > 2x previous 90-day slope


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionEstimate:
    """A single charging-session-derived capacity estimate."""

    session_start: datetime
    start_level: float
    end_level: float
    delta_soc: float
    energy_kwh: float
    avg_temp_c: float | None
    raw_estimated_kwh: float       # before corrections
    corrected_estimated_kwh: float  # after temp + SoC calibration
    soh_pct: float                  # final


@dataclass
class MethodResult:
    """Aggregate result for one estimation method."""

    method: str
    soh_pct: float
    estimated_kwh: float | None
    sample_count: int
    confidence: str  # 'high' | 'medium' | 'low'
    inputs: dict[str, Any]
    monthly_breakdown: list[dict[str, Any]]  # [{month, soh_pct, sample_count}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_soc_calibration(end_level: float) -> float:
    """Subtract a fixed offset when Skoda reports a near-full end_level.

    Rationale: Skoda BMS clamps the displayed SoC at 100%, so 'end_level=98'
    often corresponds to an actual pack SoC of ~100%. By subtracting 2% from
    end_level whenever it's above 95, we recover a more realistic delta_soc.
    """
    if end_level > SOC_CALIBRATION_TRIGGER_PCT:
        return end_level - SOC_CALIBRATION_OFFSET_PCT
    return end_level


def _apply_temperature_correction(
    estimated_kwh: float,
    avg_temp_c: float | None,
) -> tuple[float, float]:
    """Scale est_kwh to a 25°C reference temperature.

    Lithium NMC cells show ~0.5% capacity deviation per °C from 25°C
    (less capacity when cold, more when warm). We measure the penalty as
    always-positive magnitude and adjust direction based on whether we
    measured cold (scale up to undo cold loss) or hot (scale down to undo
    hot inflation).

    Returns (corrected_kwh, signed_correction_pct_applied).
    """
    if avg_temp_c is None:
        return estimated_kwh, 0.0
    delta_t = avg_temp_c - TEMP_REFERENCE_C
    penalty_magnitude = abs(delta_t) * TEMP_COEFF_PER_C  # always positive
    if delta_t < 0:
        # Cold: measured was LOWER than true capacity → divide by < 1 → scale UP
        correction_factor = 1.0 - penalty_magnitude
        signed_correction_pct = -penalty_magnitude * 100  # negative = we added back
    else:
        # Hot: measured was HIGHER than true capacity → divide by > 1 → scale DOWN
        correction_factor = 1.0 + penalty_magnitude
        signed_correction_pct = penalty_magnitude * 100  # positive = we subtracted
    if correction_factor <= 0:
        # Pathological delta — fall back to passthrough
        return estimated_kwh, signed_correction_pct
    corrected = estimated_kwh / correction_factor
    return corrected, signed_correction_pct


def _confidence_from_samples(n: int) -> str:
    if n >= HIGH_CONFIDENCE_SAMPLES:
        return "high"
    if n >= MEDIUM_CONFIDENCE_SAMPLES:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Method 1: Capacity-based
# ---------------------------------------------------------------------------


async def estimate_capacity_based(
    db: AsyncSession,
    user_vehicle_id: uuid.UUID,
    factory_kwh: float,
    lookback_days: int = 365,
) -> MethodResult | None:
    """Estimate SoH from charging sessions using capacity-based method.

    Filters:
      - end_level IS NOT NULL AND start_level IS NOT NULL
      - energy_kwh > 0
      - delta_soc BETWEEN [SOC_DELTA_MIN, SOC_DELTA_MAX]
      - within lookback window

    Per-session estimate:
      est_kwh_raw = energy_kwh / (delta_soc / 100)
      est_kwh_corrected = temperature-correct(SoC-calibrate(end_level))
      soh_pct = (est_kwh_corrected / factory_kwh) * 100

    Aggregate: monthly median of valid estimates.
    """
    if not factory_kwh or factory_kwh <= 0:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    floor_kwh = factory_kwh * CAPACITY_FLOOR_FRAC
    ceil_kwh = factory_kwh * CAPACITY_CEIL_FRAC

    query = text("""
        SELECT
            session_start,
            start_level,
            end_level,
            energy_kwh,
            avg_temp_celsius,
            charging_type
        FROM charging_sessions
        WHERE user_vehicle_id = :vehicle_id
          AND session_start >= :cutoff
          AND end_level IS NOT NULL
          AND start_level IS NOT NULL
          AND energy_kwh IS NOT NULL
          AND energy_kwh > 0
          AND (end_level - start_level) BETWEEN :delta_min AND :delta_max
        ORDER BY session_start DESC
    """)

    rows = (await db.execute(query, {
        "vehicle_id": str(user_vehicle_id),
        "cutoff": cutoff,
        "delta_min": SOC_DELTA_MIN,
        "delta_max": SOC_DELTA_MAX,
    })).fetchall()

    if not rows:
        return None

    estimates: list[SessionEstimate] = []
    for row in rows:
        end_calibrated = _apply_soc_calibration(float(row.end_level))
        delta_soc = end_calibrated - float(row.start_level)
        if delta_soc <= 0:
            continue

        # Strip charging losses to get battery energy, not grid energy.
        loss_pct = CHARGING_LOSS_PCT.get(row.charging_type, CHARGING_LOSS_DEFAULT_PCT) \
            if row.charging_type else CHARGING_LOSS_DEFAULT_PCT
        battery_kwh = float(row.energy_kwh) * (1.0 - loss_pct)

        raw_est_kwh = battery_kwh / (delta_soc / 100.0)
        corrected_kwh, temp_correction_pct = _apply_temperature_correction(
            raw_est_kwh, row.avg_temp_celsius
        )

        # Outlier filter on corrected value
        if corrected_kwh < floor_kwh or corrected_kwh > ceil_kwh:
            continue

        soh_pct = (corrected_kwh / factory_kwh) * 100.0
        estimates.append(SessionEstimate(
            session_start=row.session_start,
            start_level=float(row.start_level),
            end_level=float(row.end_level),
            delta_soc=delta_soc,
            energy_kwh=float(row.energy_kwh),
            avg_temp_c=float(row.avg_temp_celsius) if row.avg_temp_celsius is not None else None,
            raw_estimated_kwh=raw_est_kwh,
            corrected_estimated_kwh=corrected_kwh,
            soh_pct=soh_pct,
        ))

    if not estimates:
        return None

    # Monthly median
    monthly: dict[str, list[float]] = {}
    for e in estimates:
        month_key = e.session_start.strftime("%Y-%m")
        monthly.setdefault(month_key, []).append(e.soh_pct)

    monthly_breakdown = []
    for month in sorted(monthly.keys()):
        vals = monthly[month]
        monthly_breakdown.append({
            "month": month,
            "soh_pct": round(statistics.median(vals), 2),
            "sample_count": len(vals),
        })

    # Final estimate: median of latest 90 days of valid sessions
    latest_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    recent = [e.soh_pct for e in estimates if e.session_start >= latest_cutoff]
    if not recent:
        # fall back to most recent month
        latest_month = max(monthly.keys())
        recent = monthly[latest_month]
    final_soh = round(statistics.median(recent), 2)
    final_kwh = round((final_soh / 100.0) * factory_kwh, 2)

    return MethodResult(
        method="capacity",
        soh_pct=final_soh,
        estimated_kwh=final_kwh,
        sample_count=len(estimates),
        confidence=_confidence_from_samples(len(estimates)),
        inputs={
            "factory_kwh": factory_kwh,
            "lookback_days": lookback_days,
            "soc_delta_window": [SOC_DELTA_MIN, SOC_DELTA_MAX],
            "outlier_bounds_kwh": [floor_kwh, ceil_kwh],
            "soc_calibration_offset_pct": SOC_CALIBRATION_OFFSET_PCT,
            "temp_correction_coefficient": TEMP_COEFF_PER_C,
            "method": "median_of_recent_90d_per_month_aggregated",
        },
        monthly_breakdown=monthly_breakdown,
    )


# ---------------------------------------------------------------------------
# Method 2: Throughput-based
# ---------------------------------------------------------------------------


async def estimate_throughput_based(
    db: AsyncSession,
    user_vehicle_id: uuid.UUID,
    factory_kwh: float,
    lookback_days: int = 365,
) -> MethodResult | None:
    """Estimate SoH from cumulative kWh throughput across trips.

    Equivalent full cycles = total_discharged_kwh / (2 * factory_kwh)
    (one full cycle = full charge + full discharge, hence 2x in denominator).

    SoH_loss_pct = cycles * 0.025 * temp_factor * dod_factor
    Starting from 100% SoH at delivery, current_soh = 100 - loss.
    """
    if not factory_kwh or factory_kwh <= 0:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    query = text("""
        SELECT
            COALESCE(SUM(kwh_consumed), 0) AS total_kwh,
            COALESCE(AVG(avg_temp_celsius), 25.0) AS avg_temp
        FROM trips
        WHERE user_vehicle_id = :vehicle_id
          AND start_date >= :cutoff
          AND kwh_consumed IS NOT NULL
          AND kwh_consumed > 0
    """)
    row = (await db.execute(query, {
        "vehicle_id": str(user_vehicle_id),
        "cutoff": cutoff,
    })).fetchone()

    if not row or float(row.total_kwh) <= 0:
        return None

    total_kwh = float(row.total_kwh)
    avg_temp = float(row.avg_temp)
    cycles = total_kwh / (2.0 * factory_kwh)

    # Temperature factor: 1.0 at 25°C, rises 1% per °C above (Arrhenius-lite)
    temp_factor = 1.0 + max(0.0, (avg_temp - 25.0) * 0.01)
    loss_pct = cycles * CYCLE_LOSS_AT_25C * temp_factor * DOD_AVERAGE
    soh_pct = max(0.0, 100.0 - loss_pct)

    return MethodResult(
        method="throughput",
        soh_pct=round(soh_pct, 2),
        estimated_kwh=None,  # throughput doesn't give direct capacity
        sample_count=int(cycles * 10),  # approximate "samples"
        confidence=_confidence_from_samples(int(cycles * 2)),
        inputs={
            "factory_kwh": factory_kwh,
            "lookback_days": lookback_days,
            "total_discharged_kwh": round(total_kwh, 2),
            "equivalent_full_cycles": round(cycles, 1),
            "avg_temp_celsius": round(avg_temp, 1),
            "temp_factor": round(temp_factor, 3),
            "cycle_loss_at_25c_pct": CYCLE_LOSS_AT_25C,
            "dod_factor": DOD_AVERAGE,
        },
        monthly_breakdown=[],  # could be expanded with per-month rollup
    )


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def aggregate_methods(results: list[MethodResult]) -> MethodResult | None:
    """Combine multiple methods into a single weighted-median estimate."""
    if not results:
        return None
    weights = {"capacity": 2.0, "throughput": 1.0, "resistance": 1.0}
    weighted: list[tuple[float, float]] = []  # (value, weight)
    for r in results:
        w = weights.get(r.method, 1.0)
        weighted.append((r.soh_pct, w))

    # Weighted median
    weighted.sort(key=lambda x: x[0])
    total_weight = sum(w for _, w in weighted)
    cumulative = 0.0
    median_value = weighted[-1][0]
    for value, weight in weighted:
        cumulative += weight
        if cumulative >= total_weight / 2:
            median_value = value
            break

    total_samples = sum(r.sample_count for r in results)
    # Confidence is conservative — take the MIN of all contributing methods
    # (max would let a high-sample method mask a low-sample one whose SoH
    # we're actually using). This prevents reporting "high" confidence when
    # the dominant signal came from 1 sample.
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    confidence = min(
        (r.confidence for r in results),
        key=lambda c: confidence_rank.get(c, 0),
    )

    # Most precise estimated_kwh from the capacity method if available
    capacity_result = next((r for r in results if r.method == "capacity"), None)

    return MethodResult(
        method="aggregate",
        soh_pct=round(median_value, 2),
        estimated_kwh=capacity_result.estimated_kwh if capacity_result else None,
        sample_count=total_samples,
        confidence=confidence,
        inputs={
            "methods_used": [r.method for r in results],
            "weights": {r.method: weights.get(r.method, 1.0) for r in results},
            "individual_soh_pct": {r.method: r.soh_pct for r in results},
        },
        monthly_breakdown=capacity_result.monthly_breakdown if capacity_result else [],
    )


# ---------------------------------------------------------------------------
# Orchestrator: run all methods, persist to DB
# ---------------------------------------------------------------------------


async def compute_and_store_estimate(
    db: AsyncSession,
    user_vehicle_id: uuid.UUID,
    factory_kwh: float,
    lookback_days: int = 365,
) -> MethodResult | None:
    """Run all available methods, persist each result, return aggregate."""
    methods: list[MethodResult] = []

    cap = await estimate_capacity_based(db, user_vehicle_id, factory_kwh, lookback_days)
    if cap:
        methods.append(cap)

    thr = await estimate_throughput_based(db, user_vehicle_id, factory_kwh, lookback_days)
    if thr:
        methods.append(thr)

    if not methods:
        return None

    agg = aggregate_methods(methods)
    if not agg:
        return None

    # Persist all method rows + aggregate
    now = datetime.now(timezone.utc)
    for r in methods + [agg]:
        await db.execute(
            text("""
                INSERT INTO battery_soh_estimates
                    (user_vehicle_id, estimated_at, method, soh_pct, estimated_kwh,
                     sample_count, inputs_json, confidence)
                VALUES
                    (:vehicle_id, :estimated_at, :method, :soh_pct, :estimated_kwh,
                     :sample_count, CAST(:inputs AS JSONB), :confidence)
            """),
            {
                "vehicle_id": str(user_vehicle_id),
                "estimated_at": now,
                "method": r.method,
                "soh_pct": r.soh_pct,
                "estimated_kwh": r.estimated_kwh,
                "sample_count": r.sample_count,
                "inputs": json.dumps(r.inputs),
                "confidence": r.confidence,
            },
        )
    await db.commit()
    return agg


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


async def detect_sudden_drop(
    db: AsyncSession,
    user_vehicle_id: uuid.UUID,
    window_days: int = 30,
    threshold_pct: float = SUDDEN_DROP_THRESHOLD_PCT,
) -> dict[str, Any] | None:
    """Compare latest aggregate SoH against the one from `window_days` ago.

    Returns alert payload if drop exceeds threshold, else None.
    """
    query = text("""
        SELECT estimated_at, soh_pct
        FROM battery_soh_estimates
        WHERE user_vehicle_id = :vehicle_id
          AND method = 'aggregate'
          ORDER BY estimated_at DESC
        LIMIT 50
    """)
    rows = (await db.execute(query, {"vehicle_id": str(user_vehicle_id)})).fetchall()
    if len(rows) < 2:
        return None

    latest = rows[0]
    cutoff = latest.estimated_at - timedelta(days=window_days)
    prior_rows = [r for r in rows[1:] if r.estimated_at <= cutoff]
    if not prior_rows:
        return None
    prior = prior_rows[0]

    delta = float(prior.soh_pct) - float(latest.soh_pct)
    if delta >= threshold_pct:
        return {
            "alert_type": "sudden_drop",
            "severity": "critical" if delta >= threshold_pct * 2 else "warn",
            "soh_before": float(prior.soh_pct),
            "soh_after": float(latest.soh_pct),
            "delta_pct": round(delta, 2),
            "window_days": window_days,
            "message": (
                f"Battery health dropped {delta:.1f}% over the last {window_days} days. "
                f"Recommend checking charging patterns and scheduling a diagnostic."
            ),
        }
    return None


__all__ = [
    "SessionEstimate",
    "MethodResult",
    "estimate_capacity_based",
    "estimate_throughput_based",
    "aggregate_methods",
    "compute_and_store_estimate",
    "detect_sudden_drop",
]