import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VehicleCreate(BaseModel):
    vin: str
    display_name: str | None = None
    skoda_username: str
    skoda_password: str
    skoda_spin: str | None = None
    active_interval_seconds: int = Field(default=300, ge=60, le=86400)
    parked_interval_seconds: int = Field(default=1800, ge=60, le=86400)


class VehicleResponse(BaseModel):
    id: uuid.UUID
    display_name: str | None
    manufacturer: str | None
    model: str | None
    model_year: str | None
    collection_enabled: bool
    active_interval_seconds: int
    parked_interval_seconds: int
    image_url: str | None = None
    body_type: str | None = None
    trim_level: str | None = None
    exterior_colour: str | None = None
    battery_capacity_kwh: float | None = None
    max_charging_power_kw: float | None = None
    engine_power_kw: float | None = None
    software_version: str | None = None
    capabilities: list[dict] | None = None
    specifications: dict | None = None
    warning_lights: list[dict] | None = None
    connector_status: str | None = None
    last_fetch_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VehicleUpdate(BaseModel):
    display_name: str | None = None
    collection_enabled: bool | None = None
    active_interval_seconds: int | None = Field(default=None, ge=60, le=86400)
    parked_interval_seconds: int | None = Field(default=None, ge=60, le=86400)


class VehicleStatusResponse(BaseModel):
    vin_last4: str
    display_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    model_year: str | None = None
    image_url: str | None = None
    battery_capacity_kwh: float | None = None

    latest_battery_level: float | None = None
    latest_range_km: float | None = None
    latest_charging_state: str | None = None
    latest_vehicle_state: str | None = None
    latest_position: dict | None = None
    last_updated: datetime | None = None

    charging_power_kw: float | None = None
    remaining_charge_time_min: int | None = None
    target_soc: int | None = None
    charge_type: str | None = None

    doors_locked: str | None = None
    doors_open: str | None = None
    windows_open: str | None = None
    lights_on: str | None = None
    trunk_open: bool | None = None
    bonnet_open: bool | None = None

    climate_state: str | None = None
    target_temp: float | None = None
    outside_temp: float | None = None

    odometer_km: int | None = None
    inspection_due_days: int | None = None

    is_online: bool | None = None
    is_in_motion: bool | None = None

    connector_status: str | None = None
