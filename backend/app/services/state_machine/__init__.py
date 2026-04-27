"""Vehicle state machine for trip and charge detection.

Drives the logic that interprets raw telemetry events (from the TelemetryPipeline)
and emits high-level state machine events:
  - TripStartEvent / TripEndEvent
  - ChargeStartEvent / ChargeEndEvent

Edge cases handled:
  - Short trips (< 30 s / < 500 m) → silently discarded
  - Partial charges (< 5 min) → flagged but still stored
  - Spurious ignition-on blips → debounced via STABLE_TRIP_THRESHOLD_S
  - Charging while driving → separate charge session tracked independently
"""

from app.services.telemetry.events import (
    TelemetryEvent,
    LocationEvent,
    SpeedEvent,
    BatteryEvent,
    ConnectionEvent,
    TripStartEvent,
    TripEndEvent,
    ChargeStartEvent,
    ChargeEndEvent,
)

__all__ = [
    "VehicleStateMachine",
    "VehicleState",
]
