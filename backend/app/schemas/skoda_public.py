"""Pydantic models for the official MyŠkoda Public API (camelCase JSON).

Spec: https://public.api.connect.skoda-auto.cz/v3/api-docs
Inspired by mobility-lab-vsb/skoda-public-api (MIT) field names.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


def _camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


_CAMEL = ConfigDict(populate_by_name=True, alias_generator=_camel, extra="ignore")


class BatteryStatus(BaseModel):
    model_config = _CAMEL
    remaining_cruising_range_in_meters: int | None = None
    state_of_charge_in_percent: int | None = Field(default=None, alias="stateOfChargeInPercent")


class ChargingStatus(BaseModel):
    model_config = _CAMEL
    charging_rate_in_kilometers_per_hour: float | None = None
    charge_power_in_kw: float | None = None
    remaining_time_to_fully_charged_in_minutes: int | None = None
    fully_charged_at: datetime | None = None
    state: str | None = None
    charge_type: str | None = None
    plug_connection_state: str | None = None  # CONNECTED | DISCONNECTED
    plug_lock_state: str | None = None
    battery: BatteryStatus | None = None


class ChargingSettings(BaseModel):
    model_config = _CAMEL
    target_state_of_charge_in_percent: int | None = None
    battery_care_mode_target_value_in_percent: int | None = None
    preferred_charge_mode: str | None = None
    charging_care_mode: str | None = None
    auto_unlock_plug_when_charged: str | None = None
    max_charge_current_ac: str | None = None
    max_charge_current_ac_ampere: int | None = None


class Charging(BaseModel):
    model_config = _CAMEL
    is_vehicle_in_saved_location: bool | None = None
    status: ChargingStatus | None = None
    settings: ChargingSettings | None = None
    car_captured_timestamp: datetime | None = None


class EngineRange(BaseModel):
    model_config = _CAMEL
    engine_type: str | None = None
    current_soc_in_percent: float | None = Field(default=None, alias="currentSoCInPercent")
    current_fuel_level_in_percent: float | None = Field(
        default=None, alias="currentFuelLevelInPercent"
    )
    remaining_range_in_km: float | None = None


class FuelStatus(BaseModel):
    model_config = _CAMEL
    car_type: str | None = None
    ad_blue_range: float | None = None
    total_range_in_km: float | None = None
    primary_engine_range: EngineRange | None = None
    secondary_engine_range: EngineRange | None = None
    car_captured_timestamp: datetime | None = None


class Odometer(BaseModel):
    model_config = _CAMEL
    mileage_in_km: int | None = None
    car_captured_timestamp: datetime | None = None


class ParkingGps(BaseModel):
    model_config = _CAMEL
    latitude: float | None = None
    longitude: float | None = None


class ParkingPosition(BaseModel):
    model_config = _CAMEL
    state: str | None = None  # PARKED | IN_MOTION
    gps_coordinates: ParkingGps | None = None
    formatted_address: str | None = None


class TargetTemperature(BaseModel):
    model_config = _CAMEL
    value: float | None = None
    unit: str | None = None


class AirConditioning(BaseModel):
    model_config = _CAMEL
    state: str | None = None
    target_temperature: TargetTemperature | None = None
    car_captured_timestamp: datetime | None = None


class OverallVehicleStatus(BaseModel):
    model_config = _CAMEL
    doors_locked: str | None = None
    locked: str | None = None
    doors: str | None = None
    windows: str | None = None
    lights: str | None = None


class VehicleStatus(BaseModel):
    model_config = _CAMEL
    overall: OverallVehicleStatus | None = None
    car_captured_timestamp: datetime | None = None


class VehicleOperation(BaseModel):
    model_config = _CAMEL
    name: str | None = None


class Vehicle(BaseModel):
    model_config = _CAMEL
    vin: str | None = None
    name: str | None = None
    license_plate: str | None = None
    render_url: str | None = None
    status: VehicleStatus | None = None
    fuel_status: FuelStatus | None = None
    odometer: Odometer | None = None
    parking_position: ParkingPosition | None = None
    air_conditioning: AirConditioning | None = None
    charging: Charging | None = None
    operations: list[VehicleOperation] = Field(default_factory=list)


class VehicleError(BaseModel):
    model_config = _CAMEL
    type: str | None = None
    description: str | None = None


class VehicleResponse(BaseModel):
    model_config = _CAMEL
    vehicle: Vehicle | None = None
    errors: list[VehicleError] = Field(default_factory=list)
