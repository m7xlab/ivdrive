"""Pydantic event models for vehicle telemetry.

Each event type corresponds to a specific data stream from the vehicle.
Models are designed to be validated at ingestion time and then mapped
to SQLAlchemy ORM models for persistence.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Annotated, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class EventSource(str, Enum):
    """Origin of the telemetry event."""

    CONNECTION_STATUS = "connection_status"
    CHARGING_STATUS = "charging_status"
    VEHICLE_STATUS = "vehicle_status"
    POSITION = "position"
    AIR_CONDITIONING = "air_conditioning"
    MAINTENANCE = "maintenance"
    DRIVING_RANGE = "driving_range"
    MANUAL = "manual"


# ──────────────────────────────────────────────────────────────────────────────
# Base event
# ──────────────────────────────────────────────────────────────────────────────


class TelemetryEvent(BaseModel):
    """Base class for all telemetry events."""

    user_vehicle_id: str = Field(..., description="UUID of the UserVehicle")
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: EventSource = Field(default=EventSource.CONNECTION_STATUS)

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────────────────
# Location
# ──────────────────────────────────────────────────────────────────────────────


class LocationEvent(TelemetryEvent):
    """GPS position event."""

    source: EventSource = EventSource.POSITION
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude_m: float | None = None
    heading_deg: float | None = Field(default=None, ge=0, le=360)
    speed_kmh: float | None = Field(default=None, ge=0)
    accuracy_m: float | None = None
    outside_temp_celsius: float | None = None
    weather_condition: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Speed / Motion
# ──────────────────────────────────────────────────────────────────────────────


class SpeedEvent(TelemetryEvent):
    """Vehicle speed and motion state event."""

    source: EventSource = EventSource.VEHICLE_STATUS
    speed_kmh: float | None = Field(default=None, ge=0)
    odometer_km: float | None = Field(default=None, ge=0)
    in_motion: bool = False
    ignition_on: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Battery
# ──────────────────────────────────────────────────────────────────────────────


class BatteryEvent(TelemetryEvent):
    """High-voltage battery status event."""

    source: EventSource = EventSource.CHARGING_STATUS
    battery_pct: int = Field(..., ge=0, le=100)
    remaining_range_m: int | None = None
    charging: bool = False
    charge_power_kw: float | None = Field(default=None, ge=0)
    charge_rate_km_per_hour: float | None = None
    remaining_time_min: int | None = None
    target_soc_pct: int | None = Field(default=None, ge=0, le=100)
    battery_temp_celsius: float | None = None
    hv_voltage: float | None = None
    hv_current: float | None = None


# ──────────────────────────────────────────────────────────────────────────────
# HVAC
# ──────────────────────────────────────────────────────────────────────────────


class HVACEvent(TelemetryEvent):
    """Heating, ventilation and air conditioning event."""

    source: EventSource = EventSource.AIR_CONDITIONING
    hvac_state: str | None = None  # "ON", "OFF", "HEATING", "COOLING", "VENTILATION"
    target_temp_celsius: float | None = None
    outside_temp_celsius: float | None = None
    seat_heating_front_left: bool | None = None
    seat_heating_front_right: bool | None = None
    window_heating_enabled: bool | None = None
    steering_wheel_position: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Connection / Online state
# ──────────────────────────────────────────────────────────────────────────────


class ConnectionEvent(TelemetryEvent):
    """Vehicle online/offline status event."""

    source: EventSource = EventSource.CONNECTION_STATUS
    is_online: bool = False
    is_charging: bool = False
    is_climatizing: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# State machine events — derived from basic telemetry
# ──────────────────────────────────────────────────────────────────────────────


class TripStartEvent(TelemetryEvent):
    """Emitted when a trip start is detected (motion begins)."""

    source: EventSource = EventSource.VEHICLE_STATUS
    latitude: float | None = None
    longitude: float | None = None
    odometer_km: float | None = None
    soc_pct: int | None = None


class TripEndEvent(TelemetryEvent):
    """Emitted when a trip end is detected (motion stops)."""

    source: EventSource = EventSource.VEHICLE_STATUS
    latitude: float | None = None
    longitude: float | None = None
    odometer_km: float | None = None
    soc_pct: int | None = None
    distance_km: float | None = None
    duration_seconds: int | None = None


class ChargeStartEvent(TelemetryEvent):
    """Emitted when a charging session start is detected."""

    source: EventSource = EventSource.CHARGING_STATUS
    latitude: float | None = None
    longitude: float | None = None
    soc_pct: int | None = None
    charge_type: str | None = None
    charge_power_kw: float | None = None


class ChargeEndEvent(TelemetryEvent):
    """Emitted when a charging session end is detected."""

    source: EventSource = EventSource.CHARGING_STATUS
    latitude: float | None = None
    longitude: float | None = None
    soc_pct: int | None = None
    energy_kwh: float | None = None
    duration_seconds: int | None = None
    cost_eur: float | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Raw ingestion envelope — accepts any validated event as JSON
# ──────────────────────────────────────────────────────────────────────────────


class TelemetryEnvelope(BaseModel):
    """Top-level envelope for raw telemetry ingestion via HTTP/WebSocket."""

    events: list[dict[str, Any]] = Field(..., description="List of raw event dicts")

    @model_validator(mode="after")
    def validate_events(self) -> "TelemetryEnvelope":
        """Parse and validate each raw event dict against the appropriate model."""
        validated = []
        for raw in self.events:
            source = raw.get("source", "connection_status")
            try:
                if source == "position":
                    validated.append(LocationEvent.model_validate(raw))
                elif source in ("charging_status",):
                    validated.append(BatteryEvent.model_validate(raw))
                elif source == "air_conditioning":
                    validated.append(HVACEvent.model_validate(raw))
                elif source == "vehicle_status":
                    validated.append(SpeedEvent.model_validate(raw))
                elif source == "connection_status":
                    validated.append(ConnectionEvent.model_validate(raw))
                else:
                    validated.append(TelemetryEvent.model_validate(raw))
            except Exception as exc:
                raise ValueError(f"Failed to validate event: {raw}") from exc
        self.events = validated  # type: ignore[assignment]
        return self
