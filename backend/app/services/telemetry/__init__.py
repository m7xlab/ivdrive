"""Real-time telemetry ingestion pipeline.

This package provides:
- Pydantic event models for vehicle telemetry (location, speed, battery, HVAC)
- An ingestion pipeline that validates and stores telemetry events in the DB
"""

from app.services.telemetry.events import (
    TelemetryEvent,
    LocationEvent,
    SpeedEvent,
    BatteryEvent,
    HVACEvent,
    ConnectionEvent,
    TripStartEvent,
    TripEndEvent,
    ChargeStartEvent,
    ChargeEndEvent,
)
from app.services.telemetry.pipeline import TelemetryPipeline

__all__ = [
    "TelemetryEvent",
    "LocationEvent",
    "SpeedEvent",
    "BatteryEvent",
    "HVACEvent",
    "ConnectionEvent",
    "TripStartEvent",
    "TripEndEvent",
    "ChargeStartEvent",
    "ChargeEndEvent",
    "TelemetryPipeline",
]
