"""Pydantic models for the ABRP (Iternio) Telemetry API and settings DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Telemetry payload ────────────────────────────────────────────────────────


class AbrpTlm(BaseModel):
    """One telemetry datapoint. Metric units. Omit unknown fields entirely."""

    model_config = ConfigDict(extra="allow")

    utc: int
    soc: float | None = None
    power: float | None = None
    speed: float | None = None
    lat: float | None = None
    lon: float | None = None
    is_charging: int | None = None
    is_dcfc: int | None = None
    is_parked: int | None = None
    capacity: float | None = None
    soe: float | None = None
    soh: float | None = None
    heading: float | None = None
    elevation: float | None = None
    ext_temp: float | None = None
    batt_temp: float | None = None
    voltage: float | None = None
    current: float | None = None
    odometer: float | None = None
    est_battery_range: float | None = None
    hvac_power: float | None = None
    hvac_setpoint: float | None = None
    cabin_temp: float | None = None
    car_model: str | None = None


# ── API responses ────────────────────────────────────────────────────────────


class AbrpSendResponse(BaseModel):
    status: str
    result: Any = None
    errors: list[Any] | None = None


class AbrpBulkItem(BaseModel):
    token: str
    tlm_list: list[dict[str, Any]]


class AbrpBulkRequest(BaseModel):
    data: list[AbrpBulkItem]


class AbrpBulkResponse(BaseModel):
    status: str
    result: Any = None
    errors: list[Any] | None = None


class AbrpNextChargeResult(BaseModel):
    next_charge: float | None = None


class AbrpNextChargeResponse(BaseModel):
    status: str
    result: AbrpNextChargeResult | None = None
    errors: list[Any] | None = None


# ── Settings DTOs ────────────────────────────────────────────────────────────


class AbrpConnectionOut(BaseModel):
    vehicle_id: str
    display_name: str | None = None
    enabled: bool
    has_token: bool
    token_hint: str | None = None
    car_model_typecode: str | None = None
    last_sent_at: datetime | None = None
    last_error_text: str | None = None
    consecutive_failures: int = 0
    next_charge_pct: float | None = None
    next_charge_fetched_at: datetime | None = None
    has_api_key: bool = False
    api_key_hint: str | None = None


class AbrpSettingsOut(BaseModel):
    """User-level ABRP settings (API key) + per-vehicle connections."""

    has_api_key: bool
    api_key_hint: str | None = None
    connections: list[AbrpConnectionOut] = Field(default_factory=list)


class AbrpSettingsUpdate(BaseModel):
    api_key: str | None = None  # empty string clears


class AbrpConnectionUpdate(BaseModel):
    enabled: bool | None = None
    token: str | None = None  # empty string clears
    car_model_typecode: str | None = None


class AbrpNextChargeOut(BaseModel):
    vehicle_id: str
    next_charge_pct: float | None = None
    fetched_at: datetime | None = None
    error: str | None = None
