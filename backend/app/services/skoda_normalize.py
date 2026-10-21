"""Normalize legacy (myskoda) and official public API payloads into one snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.schemas.skoda_public import VehicleResponse

SourceKind = Literal["legacy", "public", "login"]


@dataclass
class NormalizedSnapshot:
    captured_at: datetime
    source: SourceKind
    vin: str | None = None

    soc: float | None = None
    charge_power_kw: float | None = None  # positive while charging (persist convention)
    charge_state: str | None = None
    charge_type: str | None = None
    plug_connected: bool | None = None
    target_soc: float | None = None
    remaining_range_m: float | None = None
    range_km: float | None = None

    odometer_km: float | None = None

    lat: float | None = None
    lon: float | None = None
    is_moving: bool | None = None
    is_online: bool | None = None
    is_parked: bool | None = None

    outside_temp_c: float | None = None
    hvac_state: str | None = None
    hvac_setpoint_c: float | None = None

    extra: dict[str, Any] = field(default_factory=dict)


def snapshot_from_public(
    resp: VehicleResponse,
    *,
    now: datetime,
    vin: str | None = None,
) -> NormalizedSnapshot:
    """Map official GET /vehicles/{vin} body → NormalizedSnapshot."""
    v = resp.vehicle
    snap = NormalizedSnapshot(
        captured_at=now,
        source="public",
        vin=(vin or (v.vin if v else None)),
    )
    if v is None:
        return snap

    charging = v.charging
    st = charging.status if charging else None
    if st:
        snap.charge_state = st.state
        snap.charge_type = st.charge_type
        snap.charge_power_kw = st.charge_power_in_kw
        if st.battery:
            if st.battery.state_of_charge_in_percent is not None:
                snap.soc = float(st.battery.state_of_charge_in_percent)
            if st.battery.remaining_cruising_range_in_meters is not None:
                snap.remaining_range_m = float(st.battery.remaining_cruising_range_in_meters)
        if st.plug_connection_state:
            snap.plug_connected = st.plug_connection_state.upper() == "CONNECTED"
    if charging and charging.settings and charging.settings.target_state_of_charge_in_percent is not None:
        snap.target_soc = float(charging.settings.target_state_of_charge_in_percent)

    # Hybrid/combustion SoC fallback
    if snap.soc is None and v.fuel_status and v.fuel_status.primary_engine_range:
        eng = v.fuel_status.primary_engine_range
        if eng.current_soc_in_percent is not None:
            snap.soc = float(eng.current_soc_in_percent)
        if v.fuel_status.total_range_in_km is not None:
            snap.range_km = float(v.fuel_status.total_range_in_km)

    if v.odometer and v.odometer.mileage_in_km is not None:
        snap.odometer_km = float(v.odometer.mileage_in_km)

    park = v.parking_position
    if park:
        snap.is_moving = park.state == "IN_MOTION"
        snap.is_parked = park.state == "PARKED"
        if park.gps_coordinates and park.gps_coordinates.latitude is not None:
            snap.lat = park.gps_coordinates.latitude
            snap.lon = park.gps_coordinates.longitude

    if v.air_conditioning:
        snap.hvac_state = v.air_conditioning.state
        if v.air_conditioning.target_temperature:
            snap.hvac_setpoint_c = v.air_conditioning.target_temperature.value

    # Online heuristic: we got a payload
    snap.is_online = True
    return snap


def snapshot_from_legacy(
    *,
    now: datetime,
    vin: str | None = None,
    soc: float | None = None,
    charge_power_kw: float | None = None,
    charge_state: str | None = None,
    charge_type: str | None = None,
    target_soc: float | None = None,
    remaining_range_m: float | None = None,
    range_km: float | None = None,
    odometer_km: float | None = None,
    lat: float | None = None,
    lon: float | None = None,
    is_moving: bool | None = None,
    is_online: bool | None = None,
    is_parked: bool | None = None,
    outside_temp_c: float | None = None,
    hvac_state: str | None = None,
    hvac_setpoint_c: float | None = None,
) -> NormalizedSnapshot:
    """Build a snapshot from already-fetched legacy (myskoda) values."""
    return NormalizedSnapshot(
        captured_at=now,
        source="legacy",
        vin=vin,
        soc=soc,
        charge_power_kw=charge_power_kw,
        charge_state=charge_state,
        charge_type=charge_type,
        target_soc=target_soc,
        remaining_range_m=remaining_range_m,
        range_km=range_km,
        odometer_km=odometer_km,
        lat=lat,
        lon=lon,
        is_moving=is_moving,
        is_online=is_online,
        is_parked=is_parked,
        outside_temp_c=outside_temp_c,
        hvac_state=hvac_state,
        hvac_setpoint_c=hvac_setpoint_c,
    )


def snapshot_from_bff(
    *,
    charging: dict,
    vehicle_status: dict,
    parking: dict,
    driving_range: dict | None = None,
    readiness: dict | None = None,
    now: datetime,
    vin: str | None = None,
) -> NormalizedSnapshot:
    """Map mysmob BFF payloads → NormalizedSnapshot (same contract as public)."""
    snap = NormalizedSnapshot(captured_at=now, source="login", vin=vin)
    st = (charging or {}).get("status") or {}
    batt = st.get("battery") or {}
    if batt.get("stateOfChargeInPercent") is not None:
        snap.soc = float(batt["stateOfChargeInPercent"])
    if batt.get("remainingCruisingRangeInMeters") is not None:
        snap.remaining_range_m = float(batt["remainingCruisingRangeInMeters"])
    if st.get("chargePowerInKw") is not None:
        snap.charge_power_kw = float(st["chargePowerInKw"])
    snap.charge_state = st.get("state")
    snap.charge_type = st.get("chargeType")
    settings = (charging or {}).get("settings") or {}
    if settings.get("targetStateOfChargeInPercent") is not None:
        snap.target_soc = float(settings["targetStateOfChargeInPercent"])

    if snap.soc is None and driving_range:
        eng = driving_range.get("primaryEngineRange") or {}
        if eng.get("currentSoCInPercent") is not None:
            snap.soc = float(eng["currentSoCInPercent"])
        if eng.get("remainingRangeInKm") is not None:
            snap.range_km = float(eng["remainingRangeInKm"])

    park = (parking or {}).get("parkingPosition") or {}
    gps = park.get("gpsCoordinates") or {}
    if gps.get("latitude") is not None:
        snap.lat = float(gps["latitude"])
        snap.lon = float(gps.get("longitude") or 0)
    if readiness is not None:
        snap.is_online = not bool(readiness.get("unreachable"))
        snap.is_moving = bool(readiness.get("inMotion"))
        snap.is_parked = not snap.is_moving
    else:
        snap.is_online = True

    vs = (vehicle_status or {}).get("overall") or {}
    snap.extra["doors_locked"] = vs.get("doorsLocked") or vs.get("locked")
    snap.extra["doors"] = vs.get("doors")
    snap.extra["windows"] = vs.get("windows")
    return snap
