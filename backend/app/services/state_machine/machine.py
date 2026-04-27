"""Vehicle state machine — trip and charge detection.

Drives the logic that interprets raw telemetry events and emits high-level
state machine events (TripStart, TripEnd, ChargeStart, ChargeEnd).

State model
────────────
Each vehicle is always in exactly one of these states:

  IDLE          — vehicle is parked and not charging
  DRIVING       — in_motion == True (or ignition_on for > DEBOUNCE_THRESHOLD_S)
  CHARGING      — charging == True
  DRIVING_CHARGING — charging while driving (e.g. PHEV on engine charge)

Transitions are derived from TelemetryEvent objects consumed via process_event().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from enum import Enum
from typing import Any
from uuid import UUID

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
from app.services.telemetry.pipeline import pipeline

logger = logging.getLogger(__name__)


# ─── Tuning constants ────────────────────────────────────────────────────────

# Short trip threshold — trips shorter than this (or shorter than MIN_DISTANCE_M)
# are discarded without creating a Trip record.
MIN_TRIP_DURATION_S = 30
MIN_DISTANCE_M = 500

# Spurious ignition blip debounce — ignition_on for < DEBOUNCE_THRESHOLD_S
# after being IDLE is treated as noise and does NOT start a trip.
DEBOUNCE_THRESHOLD_S = 15

# Minimum charge duration — sessions shorter than this are flagged as "partial"
# (and stored normally, but tagged so analytics can filter them).
MIN_CHARGE_DURATION_S = 5 * 60  # 5 minutes


# ─── State enum ──────────────────────────────────────────────────────────────


class VehicleState(str, Enum):
    IDLE = "IDLE"
    DRIVING = "DRIVING"
    CHARGING = "CHARGING"
    DRIVING_CHARGING = "DRIVING_CHARGING"


# ─── Per-vehicle context ─────────────────────────────────────────────────────


@dataclass
class _VehicleCtx:
    """Mutable context for one vehicle's state machine."""

    vehicle_id: UUID
    state: VehicleState = VehicleState.IDLE

    # Trip tracking
    trip_started_at: datetime | None = None
    trip_start_lat: float | None = None
    trip_start_lon: float | None = None
    trip_start_odometer: float | None = None
    trip_start_soc: int | None = None
    trip_ignition_on_at: datetime | None = None  # For debounce

    # Charge tracking
    charge_started_at: datetime | None = None
    charge_start_lat: float | None = None
    charge_start_lon: float | None = None
    charge_start_soc: int | None = None
    charge_start_power_kw: float | None = None

    # Snapshot of last known values (to build end events)
    last_lat: float | None = None
    last_lon: float | None = None
    last_odometer_km: float | None = None
    last_soc: int | None = None


# ─── State machine ─────────────────────────────────────────────────────────────


class VehicleStateMachine:
    """Per-vehicle state machine for trip and charge detection.

    Instantiate one instance per vehicle (held by DataCollector or a dict).

    Usage::

        sm = VehicleStateMachine(vehicle_id=user_vehicle_id)
        for event in raw_events:
            derived = sm.process_event(event)
            for de in derived:
                await pipeline.ingest(de)
    """

    def __init__(self, vehicle_id: UUID) -> None:
        self._ctx = _VehicleCtx(vehicle_id=vehicle_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def process_event(self, event: TelemetryEvent) -> list[TelemetryEvent]:
        """Process a raw telemetry event and return any derived high-level events.

        Derived events are emitted but NOT automatically stored — the caller
        is responsible for ingesting them via TelemetryPipeline.
        """
        derived: list[TelemetryEvent] = []

        # Always snapshot last-known values for building end events
        self._update_snapshot(event)

        if isinstance(event, ConnectionEvent):
            derived = self._on_connection(event)
        elif isinstance(event, SpeedEvent):
            derived = self._on_speed(event)
        elif isinstance(event, BatteryEvent):
            derived = self._on_battery(event)
        elif isinstance(event, LocationEvent):
            derived = self._on_location(event)
        else:
            logger.debug("StateMachine %s: unhandled event %s", self._ctx.vehicle_id, type(event).__name__)

        return derived

    def current_state(self) -> VehicleState:
        """Return the current vehicle state."""
        return self._ctx.state

    def pending_trip(self) -> bool:
        """Return True if a trip start has been detected but not yet closed."""
        return self._ctx.trip_started_at is not None

    def pending_charge(self) -> bool:
        """Return True if a charge start has been detected but not yet closed."""
        return self._ctx.charge_started_at is not None

    def flush(self) -> list[TelemetryEvent]:
        """Force-close any open trip or charge session using current timestamps.

        Call this when the vehicle goes offline or collection stops.
        Returns any end events that were emitted.
        """
        derived: list[TelemetryEvent] = []
        now = datetime.now(UTC)

        if self._ctx.trip_started_at:
            trip_end = self._close_trip(now, partial=True)
            if trip_end:
                derived.append(trip_end)

        if self._ctx.charge_started_at:
            charge_end = self._close_charge(now, partial=True)
            if charge_end:
                derived.append(charge_end)

        return derived

    # ─────────────────────────────────────────────────────────────────────────
    # Snapshot helper
    # ─────────────────────────────────────────────────────────────────────────

    def _update_snapshot(self, event: TelemetryEvent) -> None:
        """Maintain last-known values for building end events."""
        ctx = self._ctx
        if isinstance(event, LocationEvent):
            ctx.last_lat = event.latitude
            ctx.last_lon = event.longitude
        elif isinstance(event, SpeedEvent):
            ctx.last_odometer_km = event.odometer_km
            ctx.last_soc = event.soc_pct
        elif isinstance(event, BatteryEvent):
            ctx.last_soc = event.battery_pct

    # ─────────────────────────────────────────────────────────────────────────
    # Connection events
    # ─────────────────────────────────────────────────────────────────────────

    def _on_connection(self, event: ConnectionEvent) -> list[TelemetryEvent]:
        """Handle connection state changes."""
        derived: list[TelemetryEvent] = []
        ctx = self._ctx

        if not event.is_online:
            # Vehicle went offline — flush any open sessions
            if ctx.trip_started_at:
                trip_end = self._close_trip(event.captured_at, partial=True)
                if trip_end:
                    derived.append(trip_end)
            if ctx.charge_started_at:
                charge_end = self._close_charge(event.captured_at, partial=True)
                if charge_end:
                    derived.append(charge_end)
            ctx.state = VehicleState.IDLE

        return derived

    # ─────────────────────────────────────────────────────────────────────────
    # Speed / motion events
    # ─────────────────────────────────────────────────────────────────────────

    def _on_speed(self, event: SpeedEvent) -> list[TelemetryEvent]:
        """Handle motion start/stop."""
        derived: list[TelemetryEvent] = []
        ctx = self._ctx
        now = event.captured_at

        # ── DRIVING transition ────────────────────────────────────────────
        if event.in_motion:
            # TripStart: first motion after being IDLE
            if ctx.state == VehicleState.IDLE and ctx.trip_started_at is None:
                trip_start = self._start_trip(event)
                if trip_start:
                    derived.append(trip_start)
                    ctx.state = VehicleState.DRIVING
                    logger.info(
                        "StateMachine[%s]: TripStart detected at %s",
                        ctx.vehicle_id, now.isoformat(),
                    )

            # DRIVING_CHARGING: motion while charging
            elif ctx.state == VehicleState.CHARGING:
                ctx.state = VehicleState.DRIVING_CHARGING
                logger.info(
                    "StateMachine[%s]: Driving while charging detected",
                    ctx.vehicle_id,
                )

            # IDLE → DRIVING via ignition_on debounce
            elif ctx.state == VehicleState.IDLE and event.ignition_on:
                if ctx.trip_ignition_on_at is None:
                    ctx.trip_ignition_on_at = now
                elif (now - ctx.trip_ignition_on_at).total_seconds() >= DEBOUNCE_THRESHOLD_S:
                    # Treat as motion (debounce passed)
                    if ctx.trip_started_at is None:
                        trip_start = self._start_trip(event)
                        if trip_start:
                            derived.append(trip_start)
                            ctx.state = VehicleState.DRIVING
                            logger.info(
                                "StateMachine[%s]: TripStart via ignition debounce at %s",
                                ctx.vehicle_id, now.isoformat(),
                            )
                    ctx.trip_ignition_on_at = None

        # ── IDLE transition ────────────────────────────────────────────────
        else:
            ctx.trip_ignition_on_at = None
            if ctx.state in (VehicleState.DRIVING, VehicleState.DRIVING_CHARGING):
                # Motion stopped — close the trip
                trip_end = self._close_trip(now)
                if trip_end:
                    derived.append(trip_end)
                    logger.info(
                        "StateMachine[%s]: TripEnd detected at %s (duration=%.0fs)",
                        ctx.vehicle_id, now.isoformat(),
                        (now - ctx.trip_started_at).total_seconds() if ctx.trip_started_at else 0,
                    )
                ctx.state = VehicleState.IDLE

        return derived

    # ─────────────────────────────────────────────────────────────────────────
    # Battery / charging events
    # ─────────────────────────────────────────────────────────────────────────

    def _on_battery(self, event: BatteryEvent) -> list[TelemetryEvent]:
        """Handle charging state changes."""
        derived: list[TelemetryEvent] = []
        ctx = self._ctx
        now = event.captured_at

        if event.charging:
            if ctx.state == VehicleState.IDLE and ctx.charge_started_at is None:
                # ChargeStart: first charging event after being IDLE
                charge_start = self._start_charge(event)
                if charge_start:
                    derived.append(charge_start)
                    ctx.state = VehicleState.CHARGING
                    logger.info(
                        "StateMachine[%s]: ChargeStart detected (soc=%s%%) at %s",
                        ctx.vehicle_id, event.battery_pct, now.isoformat(),
                    )
            elif ctx.state == VehicleState.DRIVING:
                ctx.state = VehicleState.DRIVING_CHARGING
                logger.info(
                    "StateMachine[%s]: Charging while driving detected",
                    ctx.vehicle_id,
                )

        else:
            if ctx.state in (VehicleState.CHARGING, VehicleState.DRIVING_CHARGING):
                # Charging stopped — close the charge session
                charge_end = self._close_charge(now)
                if charge_end:
                    derived.append(charge_end)
                    logger.info(
                        "StateMachine[%s]: ChargeEnd detected at %s (soc=%s%%)",
                        ctx.vehicle_id, now.isoformat(), event.battery_pct,
                    )
                if ctx.state == VehicleState.DRIVING_CHARGING:
                    ctx.state = VehicleState.DRIVING
                else:
                    ctx.state = VehicleState.IDLE

        return derived

    # ─────────────────────────────────────────────────────────────────────────
    # Location events
    # ──────────────────────────────────────────────────────────────────────────────

    def _on_location(self, event: LocationEvent) -> list[TelemetryEvent]:
        """Handle GPS position updates (currently snapshot only — no state transitions)."""
        # Location events update last-known position but don't drive transitions.
        # Trip/charge boundaries are driven by SpeedEvent and BatteryEvent.
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # Trip helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _start_trip(self, event: TelemetryEvent) -> TripStartEvent | None:
        """Create a TripStartEvent from the current context and event."""
        ctx = self._ctx
        lat = ctx.last_lat if isinstance(event, SpeedEvent) else None
        lon = ctx.last_lon if isinstance(event, SpeedEvent) else None
        odo = ctx.last_odometer_km if isinstance(event, SpeedEvent) else None
        soc = ctx.last_soc if isinstance(event, SpeedEvent) else None
        if isinstance(event, LocationEvent):
            lat = event.latitude
            lon = event.longitude

        ctx.trip_started_at = event.captured_at
        ctx.trip_start_lat = lat
        ctx.trip_start_lon = lon
        ctx.trip_start_odometer = odo
        ctx.trip_start_soc = soc

        return TripStartEvent(
            user_vehicle_id=str(ctx.vehicle_id),
            captured_at=event.captured_at,
            latitude=lat,
            longitude=lon,
            odometer_km=odo,
            soc_pct=soc,
        )

    def _close_trip(self, now: datetime, partial: bool = False) -> TripEndEvent | None:
        """Create a TripEndEvent, applying edge-case filtering."""
        ctx = self._ctx
        if ctx.trip_started_at is None:
            return None

        duration_s = int((now - ctx.trip_started_at).total_seconds())
        distance_km: float | None = None
        if (
            ctx.trip_start_odometer is not None
            and ctx.last_odometer_km is not None
        ):
            distance_km = ctx.last_odometer_km - ctx.trip_start_odometer

        # ── Edge case: short trip ──────────────────────────────────────────
        short_duration = duration_s < MIN_TRIP_DURATION_S
        short_distance = (
            distance_km is not None
            and distance_km * 1000 < MIN_DISTANCE_M
        )
        if (short_duration or short_distance) and not partial:
            logger.info(
                "StateMachine[%s]: Trip discarded (short trip: %ds, %.0fm) < thresholds",
                ctx.vehicle_id, duration_s,
                distance_km * 1000 if distance_km else 0,
            )
            ctx.trip_started_at = None
            return None

        ctx.trip_started_at = None

        return TripEndEvent(
            user_vehicle_id=str(ctx.vehicle_id),
            captured_at=now,
            latitude=ctx.last_lat,
            longitude=ctx.last_lon,
            odometer_km=ctx.last_odometer_km,
            soc_pct=ctx.last_soc,
            distance_km=distance_km,
            duration_seconds=duration_s,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Charge helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _start_charge(self, event: BatteryEvent) -> ChargeStartEvent | None:
        """Create a ChargeStartEvent from the current context and event."""
        ctx = self._ctx
        ctx.charge_started_at = event.captured_at
        ctx.charge_start_lat = ctx.last_lat
        ctx.charge_start_lon = ctx.last_lon
        ctx.charge_start_soc = event.battery_pct
        ctx.charge_start_power_kw = event.charge_power_kw

        return ChargeStartEvent(
            user_vehicle_id=str(ctx.vehicle_id),
            captured_at=event.captured_at,
            latitude=ctx.last_lat,
            longitude=ctx.last_lon,
            soc_pct=event.battery_pct,
            charge_type=None,
            charge_power_kw=event.charge_power_kw,
        )

    def _close_charge(self, now: datetime, partial: bool = False) -> ChargeEndEvent | None:
        """Create a ChargeEndEvent, applying edge-case filtering."""
        ctx = self._ctx
        if ctx.charge_started_at is None:
            return None

        duration_s = int((now - ctx.charge_started_at).total_seconds())

        # ── Edge case: partial charge (< 5 min) ────────────────────────────
        if duration_s < MIN_CHARGE_DURATION_S and not partial:
            logger.info(
                "StateMachine[%s]: Partial charge detected (%ds < %ds min). "
                "Stored but flagged.",
                ctx.vehicle_id, duration_s, MIN_CHARGE_DURATION_S // 60,
            )
            # Still close the session — we just log the flag

        ctx.charge_started_at = None

        # Energy estimation: avg power * duration
        energy_kwh: float | None = None
        if ctx.charge_start_power_kw is not None:
            energy_kwh = ctx.charge_start_power_kw * (duration_s / 3600)

        return ChargeEndEvent(
            user_vehicle_id=str(ctx.vehicle_id),
            captured_at=now,
            latitude=ctx.last_lat,
            longitude=ctx.last_lon,
            soc_pct=ctx.last_soc,
            energy_kwh=energy_kwh,
            duration_seconds=duration_s,
            cost_eur=None,  # Cost calculated in analytics layer
        )


# ─── Global registry ──────────────────────────────────────────────────────────
# DataCollector holds one VehicleStateMachine per active vehicle.


def build_state_machine(vehicle_id: UUID) -> VehicleStateMachine:
    """Factory for per-vehicle state machines (used by DataCollector)."""
    return VehicleStateMachine(vehicle_id)
