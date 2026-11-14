"""Battery Health v2 - multi-method SoH estimation service.

Six independent estimation methods, each with its own confidence level,
plus a combined view that blends them into a single SoH + confidence per
vehicle. Spec from the Aug 4 -> Sep 1, 2026 work captured in
``_local_docs/plans/SOH_SOC_CONSPECT_2026-08-04_to_2026-09-01.md``.

Combined SoH:
  weighted median across methods that returned a value.
  Weights: Tesla 3x, taper 2x, others 1x.

Combined confidence:
  weighted average of method confidence ranks.
  Weights: METHOD_WEIGHTS x low-confidence penalty (x 0.5 for low).
  Thresholds: >= 1.5 high, >= 0.5 medium, else low.

Methods:
  1. tesla_capacity         est_kwh = median(charging.energy_kwh / delta_soc),
                             SoH = est / factory_capacity * 100
  2. charging_curve_taper   DC-only power comparison across SOC buckets
                             over time. Round-3 fix: just exclude AC
                             (power_kw < 22.0), include all DC.
  3. cell_imbalance         monthly trend of imbalance_mv
  4. throughput             total kWh throughput vs expected
  5. fleet_benchmark        similar-age fleet average (model_year peer group)
  6. range_drift_over_time  median range first-half vs second-half
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import (
    BatteryHealth,
    BatteryHealthAnalytics,
    ChargingCurve,
    ChargingSession,
    Drive,
    DriveRangeEstimatedFull,
    ChargingState,
)
from app.models.vehicle import UserVehicle


# ===== Confidence levels =====
CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"
CONF_RANK = {CONF_HIGH: 2, CONF_MEDIUM: 1, CONF_LOW: 0}

# ===== Method weights for combined SoH =====
METHOD_WEIGHTS: Dict[str, float] = {
    "tesla_capacity": 3.0,
    "charging_curve_taper": 2.0,
    "cell_imbalance": 1.0,
    "throughput": 1.0,
    "fleet_benchmark": 1.0,
    "range_drift_over_time": 1.0,
}

# ===== Sample count thresholds for confidence (high_min, medium_min) =====
SAMPLE_THRESHOLDS: Dict[str, Tuple[int, int]] = {
    "tesla_capacity":         (20, 5),
    "charging_curve_taper":   (50, 20),
    "cell_imbalance":         (2000, 500),
    "throughput":             (50, 20),
    "fleet_benchmark":        (5, 2),
    "range_drift_over_time":  (3000, 500),
}

# ===== Domain constants =====
AC_CHARGING_KW_THRESHOLD = 22.0   # max AC charging (3-phase 32A); above is DC
TEMP_REF_CELSIUS = 25.0
TEMP_COEFFICIENT = 0.003         # 0.3% per degree below reference
# Measured charging energy = sum(charge_power_kw x hours) over the charging_states rows of a session.
# Sessions whose energy_kwh is only SoC x nominal capacity carry no information about capacity
# (#218: the estimator returned the configured capacity with HIGH confidence), so only integrated
# power counts, and the integration must cover most of the session and agree roughly with the SoC
# figure. The charger tapers near a full battery and a merged state row carries one power value,
# so charges ending above MAX_END_LEVEL are left out.
MIN_HALF_SPAN_DAYS = 60          # range drift: the two halves of the data must be this far apart
MIN_COVERAGE = 0.8               # share of the session covered by power readings
MIN_DELTA_SOC = 0.15             # at least 15 % added
MAX_END_LEVEL = 90.0             # no taper phase
MIN_SESSION_MINUTES = 30
RATIO_TOLERANCE = 0.30           # |measured / SoC-derived - 1| must be within this
CAPACITY_MAX_CONFIDENCE = "medium"   # the AC loss factor is an assumption, never a measurement
CAPACITY_MIN_SAMPLES = 5
CAPACITY_OVER_NOMINAL_TOLERANCE = 0.03   # a median above nominal + 3 % means the inputs are wrong, not the battery
CAPACITY_MAX_SPREAD_FRACTION = 0.25      # samples spread wider than a quarter of the pack: low confidence
RANGE_RISE_TOLERANCE = 0.02              # range retention above 102 % is season or driving style, not health
AC_LOSS_FACTOR = 0.95            # 5% charging loss for AC
DC_LOSS_FACTOR = 0.98            # 2% charging loss for DC
SOH_CAP_LOWER = 0.0
SOH_CAP_UPPER = 100.0

SOC_BUCKETS = [(40, 50), (50, 60), (60, 70), (70, 80)]


# ===== Data classes =====
@dataclass
class MethodResult:
    method: str
    soh_pct: Optional[float]
    sample_count: int
    confidence: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "soh_pct": self.soh_pct,
            "sample_count": self.sample_count,
            "confidence": self.confidence,
            "reason": self.inputs.get("reason") if self.soh_pct is None else None,
            "inputs": self.inputs,
            "extra": self.extra,
        }


@dataclass
class CombinedAnalytics:
    user_vehicle_id: UUID
    soh_pct: Optional[float]
    confidence: str
    estimated_kwh: Optional[float]
    methods: List[MethodResult]
    anomalies: List[str]
    computed_at: datetime
    lookback_days: int = 365

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_vehicle_id": str(self.user_vehicle_id),
            "soh_pct": self.soh_pct,
            "confidence": self.confidence,
            "estimated_kwh": self.estimated_kwh,
            "methods": [m.to_dict() for m in self.methods],
            "anomalies": self.anomalies,
            "computed_at": self.computed_at.isoformat(),
        }


# ===== Helpers =====
def _confidence_from_samples(method: str, sample_count: int) -> str:
    high_min, med_min = SAMPLE_THRESHOLDS.get(method, (100, 20))
    if sample_count >= high_min:
        return CONF_HIGH
    if sample_count >= med_min:
        return CONF_MEDIUM
    return CONF_LOW


def _clamp_soh(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(max(SOH_CAP_LOWER, min(SOH_CAP_UPPER, value)), 2)


def _taper_soh_adjustment(median_change_pct: float) -> float:
    """Clamp median DC power change (%) to a SoH offset of ±5 points.

    ``median_change_pct`` is (recent − earlier) / earlier × 100, so a power
    drop is negative and must lower SoH — do not invert the sign.
    """
    return max(-5.0, min(5.0, median_change_pct))


def _weighted_median(values_with_weights: List[Tuple[float, float]]) -> Optional[float]:
    if not values_with_weights:
        return None
    sorted_pairs = sorted(values_with_weights, key=lambda x: x[0])
    total_weight = sum(w for _, w in sorted_pairs)
    if total_weight <= 0:
        return None
    half_weight = total_weight / 2
    cum = 0.0
    for value, weight in sorted_pairs:
        cum += weight
        if cum >= half_weight:
            return value
    return sorted_pairs[-1][0]


def _weighted_avg_confidence(methods: List[MethodResult]) -> str:
    if not methods:
        return CONF_LOW
    total_weight = 0.0
    weighted_sum = 0.0
    for m in methods:
        if m.soh_pct is None:
            continue
        method_w = METHOD_WEIGHTS.get(m.method, 1.0)
        rank = CONF_RANK.get(m.confidence, 0)
        if m.confidence == CONF_LOW:
            method_w *= 0.5
        weighted_sum += method_w * rank
        total_weight += method_w
    if total_weight == 0:
        return CONF_LOW
    avg = weighted_sum / total_weight
    if avg >= 1.5:
        return CONF_HIGH
    if avg >= 0.5:
        return CONF_MEDIUM
    return CONF_LOW


async def _get_vehicle(db: AsyncSession, vehicle_id: UUID) -> Optional[UserVehicle]:
    return await db.get(UserVehicle, vehicle_id)


# ===== Method 1: tesla_capacity =====
async def _measured_session_energy(db: AsyncSession, s: ChargingSession) -> Tuple[Optional[float], float]:
    """(kWh integrated from charge_power_kw over the session's charging_states rows, coverage 0..1).
    None when no power reading overlaps the session."""
    if s.session_start is None or s.session_end is None or s.session_end <= s.session_start:
        return None, 0.0
    rows = (await db.execute(
        select(ChargingState.first_date, ChargingState.last_date, ChargingState.charge_power_kw)
        .where(ChargingState.user_vehicle_id == s.user_vehicle_id)
        .where(ChargingState.charge_power_kw > 0)
        .where(ChargingState.first_date < s.session_end)
        .where(ChargingState.last_date > s.session_start)
    )).all()
    if not rows:
        return None, 0.0
    kwh = 0.0
    covered = 0.0
    for first, last, kw in rows:
        a, b = max(first, s.session_start), min(last, s.session_end)
        hours = max((b - a).total_seconds(), 0.0) / 3600.0
        kwh += float(kw) * hours
        covered += hours
    total = (s.session_end - s.session_start).total_seconds() / 3600.0
    return kwh, (min(covered / total, 1.0) if total > 0 else 0.0)


async def estimate_tesla_capacity(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Capacity from charging energy:
        est_kwh = median(measured_kwh x loss / delta_soc)
        SoH = (est_kwh / factory_capacity) * 100
    measured_kwh is integrated from the charger power readings of the session (see MIN_COVERAGE);
    a session's energy_kwh column is SoC x nominal capacity and is never used here. AC charging
    loss 5 %, DC 2 %; cold weather adds 0.3 % per degree below 25 C. Confidence is capped at
    medium because the loss factor is assumed, not measured.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    veh = await _get_vehicle(db, vehicle_id)
    if veh is None or veh.battery_capacity_kwh is None or veh.battery_capacity_kwh <= 0:
        return MethodResult(
            method="tesla_capacity", soh_pct=None, sample_count=0,
            confidence=CONF_LOW,
            inputs={"reason": "vehicle or battery_capacity_kwh missing"},
        )
    factory_kwh = veh.battery_capacity_kwh
    sessions = (await db.execute(
        select(ChargingSession)
        .where(ChargingSession.user_vehicle_id == vehicle_id)
        .where(ChargingSession.session_start >= cutoff)
        .where(ChargingSession.session_end.isnot(None))
        .where(ChargingSession.start_level.isnot(None))
        .where(ChargingSession.end_level.isnot(None))
        .order_by(desc(ChargingSession.session_start))
    )).scalars().all()
    samples: List[float] = []
    skipped = {"no_power_readings": 0, "low_coverage": 0, "small_or_short": 0, "taper": 0, "disagrees_with_soc": 0}
    for s in sessions:
        delta_soc = (s.end_level - s.start_level) / 100.0
        minutes = (s.session_end - s.session_start).total_seconds() / 60.0
        if delta_soc < MIN_DELTA_SOC or minutes < MIN_SESSION_MINUTES:
            skipped["small_or_short"] += 1
            continue
        if s.end_level > MAX_END_LEVEL:
            skipped["taper"] += 1
            continue
        measured, coverage = await _measured_session_energy(db, s)
        if measured is None or measured <= 0:
            skipped["no_power_readings"] += 1
            continue
        if coverage < MIN_COVERAGE:
            skipped["low_coverage"] += 1
            continue
        soc_derived = delta_soc * factory_kwh
        if abs(measured / soc_derived - 1.0) > RATIO_TOLERANCE:
            skipped["disagrees_with_soc"] += 1
            continue
        is_ac = (s.charging_type or "").upper().startswith("AC")
        loss = AC_LOSS_FACTOR if is_ac else DC_LOSS_FACTOR
        est_kwh = (measured * loss) / delta_soc
        if s.avg_temp_celsius is not None and s.avg_temp_celsius < TEMP_REF_CELSIUS:
            temp_delta = TEMP_REF_CELSIUS - s.avg_temp_celsius
            correction = 1.0 - (temp_delta * TEMP_COEFFICIENT)
            est_kwh = est_kwh / max(correction, 0.5)
        samples.append(est_kwh)
    inputs = {"factory_kwh": factory_kwh, "lookback_days": lookback_days,
              "energy_source": "charging power integrated over time (session energy_kwh is SoC x nominal capacity and not used)",
              "sessions_in_window": len(sessions), "skipped": skipped}
    if not samples:
        reason = ("no charging session with usable power readings in lookback"
                  if sessions else "no closed charging sessions in lookback window")
        return MethodResult(
            method="tesla_capacity", soh_pct=None, sample_count=0,
            confidence=CONF_LOW, inputs={"reason": reason, **inputs},
        )
    median_kwh = statistics.median(samples)
    spread = (max(samples) - min(samples)) if len(samples) > 1 else 0.0
    inputs.update({"median_kwh": round(median_kwh, 2), "spread_kwh": round(spread, 2), "samples": len(samples)})
    if median_kwh > factory_kwh * (1.0 + CAPACITY_OVER_NOMINAL_TOLERANCE):
        # A battery cannot take in more than it holds: the power readings overstate the energy for
        # this car (a merged state row carries one power value for its whole span). A clamped
        # "100 %" would be a fiction, so say what happened instead.
        return MethodResult(
            method="tesla_capacity", soh_pct=None, sample_count=len(samples), confidence=CONF_LOW,
            inputs={"reason": f"integrated charging energy implies {median_kwh:.1f} kWh, above the {factory_kwh:.0f} kWh "
                              "nominal capacity: the charger power readings are too coarse for this car", **inputs},
        )
    if len(samples) < CAPACITY_MIN_SAMPLES:
        return MethodResult(
            method="tesla_capacity", soh_pct=None, sample_count=len(samples), confidence=CONF_LOW,
            inputs={"reason": f"only {len(samples)} usable charging sessions; need {CAPACITY_MIN_SAMPLES}", **inputs},
        )
    soh_pct = _clamp_soh((median_kwh / factory_kwh) * 100.0)
    conf = _confidence_from_samples("tesla_capacity", len(samples))
    if CONF_RANK.get(conf, 0) > CONF_RANK.get(CAPACITY_MAX_CONFIDENCE, 0):
        conf = CAPACITY_MAX_CONFIDENCE
    if spread > factory_kwh * CAPACITY_MAX_SPREAD_FRACTION:
        conf = CONF_LOW     # the sessions disagree with each other by more than a quarter of the pack
    return MethodResult(
        method="tesla_capacity",
        soh_pct=soh_pct,
        sample_count=len(samples),
        confidence=conf,
        inputs=inputs,
        extra={"median_kwh": round(median_kwh, 2), "raw_samples_count": len(samples),
               "spread_kwh": round(max(samples) - min(samples), 2) if len(samples) > 1 else 0.0},
    )


# ===== Method 2: charging_curve_taper =====
async def estimate_charging_curve_taper(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Compare DC charging power at same SOC across time.

    Round-3 fix: just exclude AC (power_kw < 22.0), include all DC.
    No charger-capability filter needed. Bucket by SOC, compare recent half
    vs earlier half within the lookback window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    veh = await _get_vehicle(db, vehicle_id)
    if veh is None:
        return MethodResult(method="charging_curve_taper", soh_pct=None,
                            sample_count=0, confidence=CONF_LOW,
                            inputs={"reason": "vehicle missing"})

    rows = (await db.execute(
        select(ChargingCurve)
        .where(ChargingCurve.user_vehicle_id == vehicle_id)
        .where(ChargingCurve.captured_at >= cutoff)
        .where(ChargingCurve.power_kw.isnot(None))
        .where(ChargingCurve.power_kw >= AC_CHARGING_KW_THRESHOLD)
    )).scalars().all()

    if not rows:
        return MethodResult(
            method="charging_curve_taper", soh_pct=None, sample_count=0,
            confidence=CONF_LOW,
            inputs={"reason": "no DC samples (power_kw >= 22.0) in lookback",
                    "lookback_days": lookback_days},
        )

    bucket_powers: Dict[Tuple[int, int], List[Tuple[datetime, float]]] = {
        b: [] for b in SOC_BUCKETS
    }
    for r in rows:
        if r.soc_pct is None:
            continue
        for lo, hi in SOC_BUCKETS:
            if lo <= r.soc_pct < hi:
                bucket_powers[(lo, hi)].append((r.captured_at, r.power_kw))
                break

    bucket_changes: Dict[str, Dict[str, Any]] = {}
    for bucket, samples in bucket_powers.items():
        if len(samples) < 3:
            continue
        samples.sort(key=lambda x: x[0])
        mid = len(samples) // 2
        earlier = [p for _, p in samples[:mid]]
        recent = [p for _, p in samples[mid:]]
        if not earlier or not recent:
            continue
        earlier_med = statistics.median(earlier)
        recent_med = statistics.median(recent)
        if earlier_med <= 0:
            continue
        change_pct = (recent_med - earlier_med) / earlier_med * 100.0
        bucket_changes[f"{bucket[0]}-{bucket[1]}"] = {
            "earlier_median_kw": round(earlier_med, 2),
            "recent_median_kw": round(recent_med, 2),
            "change_pct": round(change_pct, 2),
            "sample_count": len(samples),
        }

    total_samples = len(rows)
    if not bucket_changes:
        return MethodResult(
            method="charging_curve_taper", soh_pct=None,
            sample_count=total_samples, confidence=CONF_LOW,
            inputs={"reason": "no SOC buckets had >= 3 samples"},
            extra={"bucket_changes": bucket_changes},
        )

    median_change = statistics.median(
        [v["change_pct"] for v in bucket_changes.values()]
    )
    soh_adj = _taper_soh_adjustment(median_change)
    soh_pct = _clamp_soh(100.0 + soh_adj)

    return MethodResult(
        method="charging_curve_taper",
        soh_pct=soh_pct,
        sample_count=total_samples,
        confidence=_confidence_from_samples("charging_curve_taper", total_samples),
        inputs={"lookback_days": lookback_days,
                "ac_threshold_kw": AC_CHARGING_KW_THRESHOLD},
        extra={"bucket_changes_pct": bucket_changes,
               "median_change_pct": round(median_change, 2)},
    )


# ===== Method 3: cell_imbalance =====
async def estimate_cell_imbalance(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 180,
) -> MethodResult:
    """
    Monthly trend of imbalance_mv. Higher imbalance = worse battery health.
    Early warning signal for actual cell defects.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    rows = (await db.execute(
        select(BatteryHealth)
        .where(BatteryHealth.user_vehicle_id == vehicle_id)
        .where(BatteryHealth.captured_at >= cutoff)
        .where(BatteryHealth.imbalance_mv.isnot(None))
        .order_by(BatteryHealth.captured_at.asc())
    )).scalars().all()

    if not rows:
        return MethodResult(
            method="cell_imbalance", soh_pct=None, sample_count=0,
            confidence=CONF_LOW,
            inputs={"reason": "no imbalance_mv data in lookback",
                    "lookback_days": lookback_days},
        )

    values = [r.imbalance_mv for r in rows]
    median_imbalance = statistics.median(values)

    monthly: Dict[str, List[float]] = {}
    for r in rows:
        key = r.captured_at.strftime("%Y-%m")
        monthly.setdefault(key, []).append(r.imbalance_mv)
    monthly_data = [
        {"month": m, "median_mv": round(statistics.median(v), 2)}
        for m, v in sorted(monthly.items())
    ]

    soh_pct = _clamp_soh(100.0 - min(median_imbalance / 10.0, 5.0))

    return MethodResult(
        method="cell_imbalance",
        soh_pct=soh_pct,
        sample_count=len(values),
        confidence=_confidence_from_samples("cell_imbalance", len(values)),
        inputs={"lookback_days": lookback_days},
        extra={"median_imbalance_mv": round(median_imbalance, 2),
               "monthly_data": monthly_data},
    )


# ===== Method 4: throughput =====
async def estimate_throughput(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Total kWh throughput vs expected. Rough degradation proxy: ~1% per 100
    full charge cycles. Confidence is low because the heuristic is crude.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    veh = await _get_vehicle(db, vehicle_id)
    if veh is None or veh.battery_capacity_kwh is None or veh.battery_capacity_kwh <= 0:
        return MethodResult(
            method="throughput", soh_pct=None, sample_count=0,
            confidence=CONF_LOW,
            inputs={"reason": "vehicle or battery_capacity_kwh missing"},
        )

    factory_kwh = veh.battery_capacity_kwh

    total_kwh = (await db.execute(
        select(func.coalesce(func.sum(ChargingSession.energy_kwh), 0))
        .where(ChargingSession.user_vehicle_id == vehicle_id)
        .where(ChargingSession.session_start >= cutoff)
        .where(ChargingSession.energy_kwh.isnot(None))
        .where(ChargingSession.energy_kwh > 0)
    )).scalar() or 0

    cycles = total_kwh / factory_kwh if factory_kwh else 0
    if total_kwh <= 0:
        # No charging energy in the window says nothing about the battery; 100 % here would become
        # the combined figure when every other method has no result (#218).
        return MethodResult(
            method="throughput", soh_pct=None, sample_count=0, confidence=CONF_LOW,
            inputs={"reason": "no charging energy recorded in lookback window",
                    "factory_kwh": factory_kwh, "lookback_days": lookback_days},
        )
    degradation_pct = min(cycles / 100.0, 50.0)
    soh_pct = _clamp_soh(100.0 - degradation_pct)

    return MethodResult(
        method="throughput",
        soh_pct=soh_pct,
        sample_count=int(cycles),
        confidence=_confidence_from_samples("throughput", int(cycles)),
        inputs={"factory_kwh": factory_kwh, "lookback_days": lookback_days},
        extra={"total_kwh": round(total_kwh, 2),
               "cycles": round(cycles, 2),
               "degradation_pct": round(degradation_pct, 2)},
    )


# ===== Method 5: fleet_benchmark =====
async def estimate_fleet_benchmark(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Compare against similar-age fleet average (model_year peer group).
    Uses the most recent combined SoH from each peer's
    battery_health_analytics table.
    """
    veh = await _get_vehicle(db, vehicle_id)
    if veh is None or not veh.model_year:
        return MethodResult(
            method="fleet_benchmark", soh_pct=None, sample_count=0,
            confidence=CONF_LOW,
            inputs={"reason": "vehicle or model_year missing"},
        )

    peers = (await db.execute(
        select(UserVehicle)
        .where(UserVehicle.model_year == veh.model_year)
        .where(UserVehicle.id != vehicle_id)
    )).scalars().all()

    if not peers:
        return MethodResult(
            method="fleet_benchmark", soh_pct=None, sample_count=0,
            confidence=CONF_LOW,
            inputs={"reason": f"no peers for model_year={veh.model_year}",
                    "model_year": veh.model_year},
        )

    peer_ids = [p.id for p in peers]
    rows = (await db.execute(
        select(BatteryHealthAnalytics)
        .where(BatteryHealthAnalytics.user_vehicle_id.in_(peer_ids))
        .where(BatteryHealthAnalytics.method == "combined")
        .order_by(BatteryHealthAnalytics.user_vehicle_id,
                  desc(BatteryHealthAnalytics.computed_at))
    )).scalars().all()

    latest_per_peer: Dict[UUID, float] = {}
    for r in rows:
        if r.user_vehicle_id not in latest_per_peer and r.soh_pct is not None:
            latest_per_peer[r.user_vehicle_id] = r.soh_pct

    peer_sohs = list(latest_per_peer.values())
    if not peer_sohs:
        return MethodResult(
            method="fleet_benchmark", soh_pct=None, sample_count=0,
            confidence=CONF_LOW,
            inputs={"reason": "no peer SoH data",
                    "model_year": veh.model_year},
        )

    peer_avg = statistics.median(peer_sohs)
    return MethodResult(
        method="fleet_benchmark",
        soh_pct=_clamp_soh(peer_avg),
        sample_count=len(peer_sohs),
        confidence=_confidence_from_samples("fleet_benchmark", len(peer_sohs)),
        inputs={"model_year": veh.model_year},
        extra={"peer_count": len(peer_sohs),
               "similar_age_avg_soh": round(peer_avg, 2)},
    )


# ===== Method 6: range_drift_over_time =====
async def estimate_range_drift_over_time(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Compare median full-charge range in the earlier half of the recorded data with the later half.
    The split is at the median timestamp of the data itself, not at the middle of the lookback
    window: a car that joined three months ago has all its samples in the "second half" of a
    365-day window (#218: 11,982 samples, "no data in first or second half"). The two halves
    must be at least MIN_HALF_SPAN_DAYS apart to say anything about drift.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    rows = (await db.execute(
        select(DriveRangeEstimatedFull)
        .join(Drive, Drive.id == DriveRangeEstimatedFull.drive_id)
        .where(Drive.user_vehicle_id == vehicle_id)
        .where(DriveRangeEstimatedFull.last_date >= cutoff)
        .where(DriveRangeEstimatedFull.range_estimated_full.isnot(None))
        .where(DriveRangeEstimatedFull.range_estimated_full > 0)
        .order_by(DriveRangeEstimatedFull.last_date.asc())
    )).scalars().all()
    if len(rows) < 10:
        return MethodResult(
            method="range_drift_over_time", soh_pct=None,
            sample_count=len(rows), confidence=CONF_LOW,
            inputs={"reason": "need >= 10 range samples", "lookback_days": lookback_days},
        )
    first_day, last_day = rows[0].last_date, rows[-1].last_date
    span_days = (last_day - first_day).total_seconds() / 86400.0
    mid = rows[len(rows) // 2].last_date
    first_rows = [r for r in rows if r.last_date < mid]
    second_rows = [r for r in rows if r.last_date >= mid]
    halves_apart_days = ((second_rows[len(second_rows) // 2].last_date - first_rows[len(first_rows) // 2].last_date).total_seconds() / 86400.0
                         if first_rows and second_rows else 0.0)
    data_window = {"first_sample": first_day.date().isoformat(), "last_sample": last_day.date().isoformat(),
                   "span_days": round(span_days, 1), "samples_first_half": len(first_rows),
                   "samples_second_half": len(second_rows), "halves_apart_days": round(halves_apart_days, 1),
                   "lookback_days": lookback_days}
    if not first_rows or not second_rows or halves_apart_days < MIN_HALF_SPAN_DAYS:
        return MethodResult(
            method="range_drift_over_time", soh_pct=None,
            sample_count=len(rows), confidence=CONF_LOW,
            inputs={"reason": f"the {len(rows)} samples span only {span_days:.0f} days "
                              f"({first_day.date()} to {last_day.date()}); the two halves need to be "
                              f">= {MIN_HALF_SPAN_DAYS} days apart to measure drift", **data_window},
        )
    first_med = statistics.median([r.range_estimated_full for r in first_rows])
    second_med = statistics.median([r.range_estimated_full for r in second_rows])
    if first_med <= 0:
        return MethodResult(
            method="range_drift_over_time", soh_pct=None,
            sample_count=len(rows), confidence=CONF_LOW,
            inputs={"reason": "first_half median is 0", **data_window},
        )
    retention = second_med / first_med
    if retention > 1.0 + RANGE_RISE_TOLERANCE:
        # Range went UP between the halves (winter vs summer, a change of driving): that is not a
        # health signal, and a clamped 100 % with high confidence would overstate it.
        return MethodResult(
            method="range_drift_over_time", soh_pct=None, sample_count=len(rows), confidence=CONF_LOW,
            inputs={"reason": f"median full-charge range rose from {first_med:.0f} to {second_med:.0f} km "
                              f"({(retention - 1) * 100:.1f} %): season or driving style dominates, no degradation signal",
                    **data_window},
            extra={"first_half_median_km": round(first_med, 1), "second_half_median_km": round(second_med, 1),
                   "retention_pct": round(retention * 100.0, 2)},
        )
    soh_pct = _clamp_soh(retention * 100.0)
    return MethodResult(
        method="range_drift_over_time",
        soh_pct=soh_pct,
        sample_count=len(rows),
        confidence=_confidence_from_samples("range_drift_over_time", len(rows)),
        inputs=data_window,
        extra={"first_half_median_km": round(first_med, 1),
               "second_half_median_km": round(second_med, 1),
               "retention_pct": round(retention * 100.0, 2)},
    )


async def compute_full_analytics(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> CombinedAnalytics:
    """Run all 6 methods and combine them into a single analytics result.

    Methods run sequentially on purpose: AsyncSession/asyncpg is not safe for
    concurrent execute() on one connection. The previous asyncio.gather()
    caused "another operation is in progress", left the connection in a
    half-open transaction, and poisoned the pool so later requests
    (including /auth/login) returned 500.
    """
    results = (
        await estimate_tesla_capacity(db, vehicle_id, lookback_days),
        await estimate_charging_curve_taper(db, vehicle_id, lookback_days),
        await estimate_cell_imbalance(db, vehicle_id, lookback_days),
        await estimate_throughput(db, vehicle_id, lookback_days),
        await estimate_fleet_benchmark(db, vehicle_id, lookback_days),
        await estimate_range_drift_over_time(db, vehicle_id, lookback_days),
    )

    valid = [
        (r.soh_pct, METHOD_WEIGHTS.get(r.method, 1.0))
        for r in results
        if r.soh_pct is not None
    ]
    combined_soh = _clamp_soh(_weighted_median(valid))
    combined_conf = _weighted_avg_confidence(results)

    veh = await _get_vehicle(db, vehicle_id)
    estimated_kwh = None
    if veh and veh.battery_capacity_kwh and combined_soh is not None:
        estimated_kwh = round(veh.battery_capacity_kwh * combined_soh / 100.0, 2)

    anomalies: List[str] = []
    for r in results:
        if r.confidence == CONF_LOW and r.soh_pct is not None:
            anomalies.append(
                f"{r.method}: low confidence - only {r.sample_count} samples"
            )
        if r.soh_pct is None:
            anomalies.append(
                f"{r.method}: no data - {r.inputs.get('reason', 'unknown')}"
            )

    return CombinedAnalytics(
        user_vehicle_id=vehicle_id,
        soh_pct=combined_soh,
        confidence=combined_conf,
        estimated_kwh=estimated_kwh,
        methods=list(results),
        anomalies=anomalies,
        computed_at=datetime.now(timezone.utc),
        lookback_days=lookback_days,
    )


# ===== Persistence =====

def _extract_kwh(m: MethodResult) -> float | None:
    """Pick the closest-to-kWh numeric field from a method's extras for persistence.

    Some methods don't produce a clean kWh number (e.g. cell_imbalance stores
    imbalance_mv, throughput stores cycles). We persist whatever's closest to
    the concept of "estimated capacity" so the v2 cache row isn't NULL.
    """
    if m.method == "tesla_capacity":
        return m.extra.get("median_kwh")
    if m.method == "cell_imbalance":
        return m.extra.get("median_imbalance_mv")
    if m.method == "throughput":
        return m.extra.get("cycles")
    if m.method == "range_drift_over_time":
        return m.extra.get("retention_pct")
    return None


async def persist_analytics(db: AsyncSession, analytics: CombinedAnalytics) -> None:
    """Write one row per method + one 'combined' row to battery_health_analytics."""
    now = datetime.now(timezone.utc)
    for m in analytics.methods:
        row = BatteryHealthAnalytics(
            user_vehicle_id=analytics.user_vehicle_id,
            computed_at=now,
            method=m.method,
            soh_pct=m.soh_pct,                      # NULL = no result; 0 % would read as a dead battery
            estimated_kwh=_extract_kwh(m),
            sample_count=m.sample_count,
            confidence=m.confidence,
            inputs_json=m.inputs,
            extra_json=m.extra,
        )
        db.add(row)
    combined_row = BatteryHealthAnalytics(
        user_vehicle_id=analytics.user_vehicle_id,
        computed_at=now,
        method="combined",
        soh_pct=analytics.soh_pct,
        estimated_kwh=analytics.estimated_kwh,
        sample_count=sum(m.sample_count for m in analytics.methods),
        confidence=analytics.confidence,
        inputs_json=None,
        extra_json={"anomalies": analytics.anomalies, "lookback_days": analytics.lookback_days},
    )
    db.add(combined_row)
    await db.commit()
