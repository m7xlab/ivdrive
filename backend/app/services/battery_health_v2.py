"""
Battery Health v2 — multi-method SoH estimation service.

Six independent estimation methods, each with its own confidence level,
plus a combined view that blends them into a single SoH + confidence per
vehicle. Spec is from the Aug 4 -> Sep 1, 2026 work captured in
``_local_docs/plans/SOH_SOC_CONSPECT_2026-08-04_to_2026-09-01.md``.

Combined confidence (per Aug 5 chat decision):
  - Weighted average of method confidence ranks
  - Weights: METHOD_WEIGHTS_SOH x low-confidence penalty (x 0.5 for low)
  - Threshold: >= 1.5 high, >= 0.5 medium, else low

Combined SoH:
  - Weighted median across methods that returned a value
  - Weights: Tesla 3x, taper 2x, others 1x

Methods:
  1. tesla_capacity         est_kwh = median(charging.energy_kwh / delta_soc),
                             SoH = est / factory_capacity * 100
  2. charging_curve_taper   DC-only power comparison across SOC buckets over
                             time. AC excluded (power_kw < 22.0 is AC).
  3. cell_imbalance         Monthly trend of imbalance_mv (early warning for
                             cell defects).
  4. throughput             Total kWh throughput vs expected (degradation proxy).
  5. range_drift_over_time  Median range first half vs second half of the
                             lookback window (real-world degradation).
  6. fleet_benchmark        Similar-age fleet average (model_year peer group).
"""

from __future__ import annotations

import asyncio
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple, Any
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_vehicle import UserVehicle
from app.models.battery_health import BatteryHealth
from app.models.charging_session import ChargingSession
from app.models.charging_curve import ChargingCurve
from app.models.battery_health_analytics import BatteryHealthAnalytics
from app.models.drive_range import DriveRange


# ===== Confidence =====
CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"

CONF_RANK = {CONF_HIGH: 2, CONF_MEDIUM: 1, CONF_LOW: 0}

# Combined-SoH weights (per Aug 5 decision: Tesla 3x, taper 2x, others 1x)
METHOD_WEIGHTS_SOH: Dict[str, float] = {
    "tesla_capacity": 3.0,
    "charging_curve_taper": 2.0,
    "cell_imbalance": 1.0,
    "throughput": 1.0,
    "range_drift_over_time": 1.0,
    "fleet_benchmark": 1.0,
}

# Sample-count thresholds for confidence assignment (high_min, medium_min)
SAMPLE_THRESHOLDS: Dict[str, Tuple[int, int]] = {
    "tesla_capacity":          (20, 5),
    "charging_curve_taper":    (50, 20),
    "cell_imbalance":          (2000, 500),
    "throughput":              (50, 20),
    "range_drift_over_time":   (3000, 500),
    "fleet_benchmark":         (5, 2),
}

# ===== Domain constants =====
AC_CHARGING_KW_THRESHOLD = 22.0  # max AC charging (3-phase 32A wallbox)
TEMP_REF_CELSIUS = 25.0
TEMP_COEFFICIENT = 0.003        # 0.3% per degree below reference
AC_LOSS_FACTOR = 0.95           # 5% charging loss for AC
DC_LOSS_FACTOR = 0.98           # 2% charging loss for DC
SOH_CAP_LOWER = 0.0
SOH_CAP_UPPER = 100.0
SOH_CAP_FRAC = 1.00             # hard cap to prevent >100% from noise

# SOC buckets for taper (per chat decision)
SOC_BUCKETS = [(40, 50), (50, 60), (60, 70), (70, 80)]


# ===== Data classes =====
@dataclass
class MethodResult:
    method: str
    soh_pct: Optional[float]
    sample_count: int
    confidence: str
    inputs: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "soh_pct": self.soh_pct,
            "sample_count": self.sample_count,
            "confidence": self.confidence,
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

    def to_dict(self) -> dict:
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
    return max(SOH_CAP_LOWER, min(SOH_CAP_UPPER * SOH_CAP_FRAC, value))


def _weighted_median(values_with_weights: List[Tuple[float, float]]) -> Optional[float]:
    """Weighted median. Each (value, weight) pair."""
    if not values_with_weights:
        return None
    sorted_pairs = sorted(values_with_weights, key=lambda x: x[0])
    total_weight = sum(w for _, w in sorted_pairs)
    if total_weight <= 0:
        return None
    half_weight = total_weight / 2
    cum_weight = 0.0
    for value, weight in sorted_pairs:
        cum_weight += weight
        if cum_weight >= half_weight:
            return value
    return sorted_pairs[-1][0]


def _weighted_avg_confidence(methods: List[MethodResult]) -> str:
    """Weighted average of confidence ranks.
    Low-confidence methods x 0.5.
    Threshold: >=1.5 high, >=0.5 medium, else low.
    """
    if not methods:
        return CONF_LOW
    total_weight = 0.0
    weighted_sum = 0.0
    for m in methods:
        if m.soh_pct is None:
            continue
        method_w = METHOD_WEIGHTS_SOH.get(m.method, 1.0)
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
    return (await db.execute(
        select(UserVehicle).where(UserVehicle.id == vehicle_id)
    )).scalar_one_or_none()


# ===== Method 1: tesla_capacity =====
async def estimate_tesla_capacity(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Tesla-style range estimation:
        est_kwh = median(charging.energy_kwh / delta_soc)
        SoH = (est_kwh / factory_capacity) * 100
    AC charging has a 5% loss; DC has 2%. Temperature adjusts for cold-weather
    capacity loss.
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

    rows = (await db.execute(
        select(ChargingSession)
        .where(ChargingSession.user_vehicle_id == vehicle_id)
        .where(ChargingSession.session_start >= cutoff)
        .where(ChargingSession.start_level.isnot(None))
        .where(ChargingSession.end_level.isnot(None))
        .where(ChargingSession.energy_kwh.isnot(None))
        .where(ChargingSession.energy_kwh > 0)
        .order_by(ChargingSession.session_start.desc())
    )).scalars().all()

    samples = []
    for s in rows:
        delta_soc = (s.end_level - s.start_level) / 100.0
        if delta_soc < 0.05 or delta_soc > 0.95:
            continue
        is_ac = (s.charging_type or "").lower().startswith("ac")
        loss = AC_LOSS_FACTOR if is_ac else DC_LOSS_FACTOR
        battery_kwh = s.energy_kwh * loss
        est_kwh = battery_kwh / delta_soc
        if s.avg_temp_celsius is not None:
            temp_delta = TEMP_REF_CELSIUS - s.avg_temp_celsius
            if temp_delta > 0:
                correction = 1.0 - (temp_delta * TEMP_COEFFICIENT)
                est_kwh = est_kwh / max(correction, 0.5)
        samples.append(est_kwh)

    if not samples:
        return MethodResult(
            method="tesla_capacity", soh_pct=None, sample_count=0,
            confidence=CONF_LOW,
            inputs={"reason": "no valid charging sessions in lookback window",
                    "lookback_days": lookback_days},
        )

    median_kwh = statistics.median(samples)
    soh_pct = (median_kwh / factory_kwh) * 100.0
    soh_pct = _clamp_soh(soh_pct)

    return MethodResult(
        method="tesla_capacity",
        soh_pct=soh_pct,
        sample_count=len(samples),
        confidence=_confidence_from_samples("tesla_capacity", len(samples)),
        inputs={"factory_kwh": factory_kwh, "lookback_days": lookback_days},
        extra={
            "median_kwh": round(median_kwh, 2),
            "raw_samples_count": len(samples),
        },
    )


# ===== Method 2: charging_curve_taper =====
async def estimate_charging_curve_taper(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Compare DC charging power at same SOC across time.

    Per Aug 5 chat decision (Round 3 fix): just exclude AC (power_kw < 22.0),
    include all DC. No charger-capability filter needed. Bucket by SOC
    (40-50, 50-60, 60-70, 70-80). Compare recent half vs earlier half within
    the lookback window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    veh = await _get_vehicle(db, vehicle_id)
    if veh is None:
        return MethodResult(method="charging_curve_taper", soh_pct=None, sample_count=0,
                            confidence=CONF_LOW, inputs={"reason": "vehicle missing"})

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
        earlier_median = statistics.median(earlier)
        recent_median = statistics.median(recent)
        if earlier_median <= 0:
            continue
        change_pct = (recent_median - earlier_median) / earlier_median * 100.0
        bucket_changes[f"{bucket[0]}-{bucket[1]}"] = {
            "earlier_median_kw": round(earlier_median, 2),
            "recent_median_kw": round(recent_median, 2),
            "change_pct": round(change_pct, 2),
            "sample_count": len(samples),
        }

    total_samples = len(rows)
    if not bucket_changes:
        return MethodResult(
            method="charging_curve_taper", soh_pct=None, sample_count=total_samples,
            confidence=CONF_LOW,
            inputs={"reason": "no SOC buckets had >= 3 samples"},
            extra={"bucket_changes": bucket_changes},
        )

    median_change = statistics.median([v["change_pct"] for v in bucket_changes.values()])
    # Negative change (power dropped) = degradation. -1% taper = -1% SoH, capped +/-5%.
    soh_adjustment = max(-5.0, min(5.0, -median_change))
    soh_pct = _clamp_soh(100.0 + soh_adjustment)

    return MethodResult(
        method="charging_curve_taper",
        soh_pct=soh_pct,
        sample_count=total_samples,
        confidence=_confidence_from_samples("charging_curve_taper", total_samples),
        inputs={"lookback_days": lookback_days,
                "ac_threshold_kw": AC_CHARGING_KW_THRESHOLD},
        extra={
            "bucket_changes_pct": bucket_changes,
            "median_change_pct": round(median_change, 2),
        },
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
        return MethodResult(method="cell_imbalance", soh_pct=None, sample_count=0,
                            confidence=CONF_LOW,
                            inputs={"reason": "no imbalance_mv data in lookback",
                                    "lookback_days": lookback_days})

    values = [r.imbalance_mv for r in rows]
    median_imbalance = statistics.median(values)

    monthly: Dict[str, List[float]] = {}
    for r in rows:
        m_key = r.captured_at.strftime("%Y-%m")
        monthly.setdefault(m_key, []).append(r.imbalance_mv)
    monthly_medians = {m: statistics.median(vs) for m, vs in monthly.items()}
    monthly_data = [{"month": m, "median_mv": round(v, 2)}
                    for m, v in sorted(monthly_medians.items())]

    # 50 mV median -> -5% SoH, scaled linearly, clamped to [0, 100].
    soh_pct = _clamp_soh(100.0 - min(median_imbalance / 10.0, 5.0))

    return MethodResult(
        method="cell_imbalance",
        soh_pct=soh_pct,
        sample_count=len(values),
        confidence=_confidence_from_samples("cell_imbalance", len(values)),
        inputs={"lookback_days": lookback_days},
        extra={
            "median_imbalance_mv": round(median_imbalance, 2),
            "monthly_data": monthly_data,
        },
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
        return MethodResult(method="throughput", soh_pct=None, sample_count=0,
                            confidence=CONF_LOW,
                            inputs={"reason": "vehicle or battery_capacity_kwh missing"})

    factory_kwh = veh.battery_capacity_kwh

    total_kwh = (await db.execute(
        select(func.coalesce(func.sum(ChargingSession.energy_kwh), 0))
        .where(ChargingSession.user_vehicle_id == vehicle_id)
        .where(ChargingSession.session_start >= cutoff)
        .where(ChargingSession.energy_kwh.isnot(None))
        .where(ChargingSession.energy_kwh > 0)
    )).scalar() or 0

    cycles = total_kwh / factory_kwh if factory_kwh else 0
    degradation_pct = min(cycles / 100.0, 50.0)  # 1% per 100 cycles, capped at 50%
    soh_pct = _clamp_soh(100.0 - degradation_pct)

    return MethodResult(
        method="throughput",
        soh_pct=soh_pct,
        sample_count=int(cycles),
        confidence=_confidence_from_samples("throughput", int(cycles)),
        inputs={"factory_kwh": factory_kwh, "lookback_days": lookback_days},
        extra={
            "total_kwh": round(total_kwh, 2),
            "cycles": round(cycles, 2),
            "degradation_pct": round(degradation_pct, 2),
        },
    )


# ===== Method 5: range_drift_over_time =====
async def estimate_range_drift(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Compare median range in first half vs second half of lookback window.
    Real-world degradation signal: range retention % maps directly to SoH.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    now = datetime.now(timezone.utc)
    mid_cutoff = cutoff + (now - cutoff) / 2

    rows = (await db.execute(
        select(DriveRange)
        .where(DriveRange.user_vehicle_id == vehicle_id)
        .where(DriveRange.captured_at >= cutoff)
        .where(DriveRange.range_km.isnot(None))
        .where(DriveRange.range_km > 0)
        .order_by(DriveRange.captured_at.asc())
    )).scalars().all()

    if len(rows) < 10:
        return MethodResult(
            method="range_drift_over_time", soh_pct=None, sample_count=len(rows),
            confidence=CONF_LOW,
            inputs={"reason": "need >=10 range samples",
                    "lookback_days": lookback_days},
        )

    first_half = [r.range_km for r in rows if r.captured_at < mid_cutoff]
    second_half = [r.range_km for r in rows if r.captured_at >= mid_cutoff]
    if not first_half or not second_half:
        return MethodResult(
            method="range_drift_over_time", soh_pct=None, sample_count=len(rows),
            confidence=CONF_LOW,
            inputs={"reason": "no data in first or second half"},
        )

    first_median = statistics.median(first_half)
    second_median = statistics.median(second_half)
    if first_median <= 0:
        return MethodResult(
            method="range_drift_over_time", soh_pct=None, sample_count=len(rows),
            confidence=CONF_LOW,
            inputs={"reason": "first_median is 0"},
        )

    retention = second_median / first_median
    soh_pct = _clamp_soh(retention * 100.0)

    return MethodResult(
        method="range_drift_over_time",
        soh_pct=soh_pct,
        sample_count=len(rows),
        confidence=_confidence_from_samples("range_drift_over_time", len(rows)),
        inputs={"lookback_days": lookback_days},
        extra={
            "first_half_median_km": round(first_median, 1),
            "second_half_median_km": round(second_median, 1),
            "retention_pct": round(retention * 100.0, 2),
        },
    )


# ===== Method 6: fleet_benchmark =====
async def estimate_fleet_benchmark(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> MethodResult:
    """
    Compare against similar-age fleet average (model_year peer group).
    Uses the most recent combined SoH from each peer's
    battery_health_analytics.
    """
    veh = await _get_vehicle(db, vehicle_id)
    if veh is None or not veh.model_year:
        return MethodResult(method="fleet_benchmark", soh_pct=None, sample_count=0,
                            confidence=CONF_LOW,
                            inputs={"reason": "vehicle or model_year missing"})

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
                  BatteryHealthAnalytics.computed_at.desc())
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

    peer_avg_soh = statistics.median(peer_sohs)
    return MethodResult(
        method="fleet_benchmark",
        soh_pct=peer_avg_soh,
        sample_count=len(peer_sohs),
        confidence=_confidence_from_samples("fleet_benchmark", len(peer_sohs)),
        inputs={"model_year": veh.model_year},
        extra={
            "peer_count": len(peer_sohs),
            "similar_age_avg_soh": round(peer_avg_soh, 2),
        },
    )


# ===== Combined orchestrator =====
async def compute_full_analytics(
    db: AsyncSession,
    vehicle_id: UUID,
    lookback_days: int = 365,
) -> CombinedAnalytics:
    """Run all 6 methods and combine them into a single analytics result."""
    results = await asyncio.gather(
        estimate_tesla_capacity(db, vehicle_id, lookback_days),
        estimate_charging_curve_taper(db, vehicle_id, lookback_days),
        estimate_cell_imbalance(db, vehicle_id, lookback_days),
        estimate_throughput(db, vehicle_id, lookback_days),
        estimate_range_drift(db, vehicle_id, lookback_days),
        estimate_fleet_benchmark(db, vehicle_id, lookback_days),
    )

    valid = [(r.soh_pct, METHOD_WEIGHTS_SOH.get(r.method, 1.0))
             for r in results if r.soh_pct is not None]
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
        methods=results,
        anomalies=anomalies,
        computed_at=datetime.now(timezone.utc),
    )
