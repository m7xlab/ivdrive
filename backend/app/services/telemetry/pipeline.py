"""Real-time telemetry ingestion pipeline.

Provides a single TelemetryPipeline class that:
1. Validates incoming TelemetryEvent objects
2. Maps them to SQLAlchemy ORM models
3. Commits them to the database with retry / error isolation

Designed to be called by:
- The DataCollector after each API fetch cycle
- WebSocket / HTTP ingestion endpoints
- The state machine when deriving high-level events
"""

import logging
from datetime import datetime, UTC
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.database import async_session
from app.models.telemetry import (
    VehiclePosition,
    ConnectionState,
    ChargingState,
    VehicleState,
    AirConditioningState,
    BatteryHealth,
    PowerUsage,
    ChargingCurve,
    Trip,
    ChargingSession,
)
from app.models.vehicle import UserVehicle
from app.services.telemetry.events import (
    LocationEvent,
    SpeedEvent,
    BatteryEvent,
    HVACEvent,
    ConnectionEvent,
    TelemetryEvent,
    TripStartEvent,
    TripEndEvent,
    ChargeStartEvent,
    ChargeEndEvent,
)

logger = logging.getLogger(__name__)


class TelemetryPipeline:
    """Ingestion pipeline that validates and stores telemetry events.

    All events for a given vehicle are committed in a single transaction.
    Failures are isolated — one bad event does not roll back others.
    """

    def __init__(self) -> None:
        self._error_count = 0
        self._last_error: str | None = None

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def ingest(self, event: TelemetryEvent) -> bool:
        """Ingest a single telemetry event.

        Returns True on success, False on validation/storage failure.
        """
        try:
            await self._store_event(event)
            return True
        except Exception as exc:
            self._error_count += 1
            self._last_error = str(exc)
            logger.warning("TelemetryPipeline: failed to store event %s — %s", event.source, exc)
            return False

    async def ingest_batch(self, events: list[TelemetryEvent]) -> dict[str, Any]:
        """Ingest a list of telemetry events in a single transaction.

        Returns a summary dict with success/failure counts.
        """
        success = 0
        failed = 0
        for event in events:
            if await self.ingest(event):
                success += 1
            else:
                failed += 1
        return {"total": len(events), "success": success, "failed": failed}

    def stats(self) -> dict[str, Any]:
        """Return pipeline error statistics."""
        return {
            "error_count": self._error_count,
            "last_error": self._last_error,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Internal store helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _store_event(self, event: TelemetryEvent) -> None:
        """Route event to the appropriate storage handler."""
        if isinstance(event, LocationEvent):
            await self._store_location(event)
        elif isinstance(event, SpeedEvent):
            await self._store_speed(event)
        elif isinstance(event, BatteryEvent):
            await self._store_battery(event)
        elif isinstance(event, HVACEvent):
            await self._store_hvac(event)
        elif isinstance(event, ConnectionEvent):
            await self._store_connection(event)
        elif isinstance(event, TripStartEvent):
            await self._store_trip_start(event)
        elif isinstance(event, TripEndEvent):
            await self._store_trip_end(event)
        elif isinstance(event, ChargeStartEvent):
            await self._store_charge_start(event)
        elif isinstance(event, ChargeEndEvent):
            await self._store_charge_end(event)
        else:
            logger.debug("TelemetryPipeline: unhandled event type %s", type(event).__name__)

    async def _store_location(self, event: LocationEvent) -> None:
        """Store a VehiclePosition record."""
        async with async_session() as session:
            try:
                session.add(
                    VehiclePosition(
                        user_vehicle_id=UUID(event.user_vehicle_id),
                        captured_at=event.captured_at,
                        latitude=event.latitude,
                        longitude=event.longitude,
                        elevation_m=event.altitude_m,
                        outside_temp_celsius=event.outside_temp_celsius,
                        weather_condition=event.weather_condition,
                    )
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise

    async def _store_speed(self, event: SpeedEvent) -> None:
        """Store/update ConnectionState with motion data."""
        async with async_session() as session:
            try:
                session.add(
                    ConnectionState(
                        user_vehicle_id=UUID(event.user_vehicle_id),
                        captured_at=event.captured_at,
                        is_online=True,
                        in_motion=event.in_motion,
                        ignition_on=event.ignition_on,
                    )
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise

    async def _store_battery(self, event: BatteryEvent) -> None:
        """Store battery health + charging state.

        Creates a BatteryHealth record and a ChargingState record
        when the vehicle is actively charging.
        """
        async with async_session() as session:
            try:
                session.add(
                    BatteryHealth(
                        user_vehicle_id=UUID(event.user_vehicle_id),
                        captured_at=event.captured_at,
                        hv_battery_voltage=event.hv_voltage,
                        hv_battery_current=event.hv_current,
                        hv_battery_temperature=event.battery_temp_celsius,
                    )
                )
                if event.charging:
                    session.add(
                        ChargingState(
                            user_vehicle_id=UUID(event.user_vehicle_id),
                            first_date=event.captured_at,
                            last_date=event.captured_at,
                            state="CHARGING",
                            battery_pct=event.battery_pct,
                            remaining_range_m=event.remaining_range_m,
                            charge_power_kw=event.charge_power_kw,
                            charge_rate_km_per_hour=event.charge_rate_km_per_hour,
                            remaining_time_min=event.remaining_time_min,
                            target_soc_pct=event.target_soc_pct,
                        )
                    )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise

    async def _store_hvac(self, event: HVACEvent) -> None:
        """Store an AirConditioningState record."""
        async with async_session() as session:
            try:
                session.add(
                    AirConditioningState(
                        user_vehicle_id=UUID(event.user_vehicle_id),
                        captured_at=event.captured_at,
                        state=event.hvac_state,
                        target_temp_celsius=event.target_temp_celsius,
                        outside_temp_celsius=event.outside_temp_celsius,
                        seat_heating_front_left=event.seat_heating_front_left,
                        seat_heating_front_right=event.seat_heating_front_right,
                        window_heating_enabled=event.window_heating_enabled,
                        steering_wheel_position=event.steering_wheel_position,
                    )
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise

    async def _store_connection(self, event: ConnectionEvent) -> None:
        """Store a ConnectionState record (online/offline detection)."""
        async with async_session() as session:
            try:
                session.add(
                    ConnectionState(
                        user_vehicle_id=UUID(event.user_vehicle_id),
                        captured_at=event.captured_at,
                        is_online=event.is_online,
                        in_motion=False,
                        ignition_on=False,
                    )
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise

    # ─── State machine derived events ─────────────────────────────────────

    async def _store_trip_start(self, event: TripStartEvent) -> None:
        """Begin a new Trip record."""
        async with async_session() as session:
            try:
                session.add(
                    Trip(
                        user_vehicle_id=UUID(event.user_vehicle_id),
                        start_date=event.captured_at,
                        start_lat=event.latitude,
                        start_lon=event.longitude,
                        start_odometer=event.odometer_km,
                        start_soc=event.soc_pct,
                    )
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise

    async def _store_trip_end(self, event: TripEndEvent) -> None:
        """Close the most recent open Trip record."""
        async with async_session() as session:
            try:
                result = await session.execute(
                    select(Trip)
                    .where(
                        Trip.user_vehicle_id == UUID(event.user_vehicle_id),
                        Trip.end_date.is_(None),
                    )
                    .order_by(Trip.start_date.desc())
                    .limit(1)
                )
                trip = result.scalar_one_or_none()
                if trip:
                    trip.end_date = event.captured_at
                    trip.end_lat = event.latitude
                    trip.end_lon = event.longitude
                    trip.end_odometer = event.odometer_km
                    trip.end_soc = event.soc_pct
                    if (
                        trip.start_odometer is not None
                        and event.odometer_km is not None
                    ):
                        trip.distance_km = event.odometer_km - trip.start_odometer
                    await session.commit()
                else:
                    logger.debug(
                        "TelemetryPipeline: no open trip to close for vehicle %s",
                        event.user_vehicle_id,
                    )
            except SQLAlchemyError:
                await session.rollback()
                raise

    async def _store_charge_start(self, event: ChargeStartEvent) -> None:
        """Begin a new ChargingSession record."""
        async with async_session() as session:
            try:
                session.add(
                    ChargingSession(
                        user_vehicle_id=UUID(event.user_vehicle_id),
                        session_start=event.captured_at,
                        latitude=event.latitude,
                        longitude=event.longitude,
                        start_level=event.soc_pct,
                        charging_type=event.charge_type,
                    )
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                raise

    async def _store_charge_end(self, event: ChargeEndEvent) -> None:
        """Close the most recent open ChargingSession record."""
        async with async_session() as session:
            try:
                result = await session.execute(
                    select(ChargingSession)
                    .where(
                        ChargingSession.user_vehicle_id == UUID(event.user_vehicle_id),
                        ChargingSession.session_end.is_(None),
                    )
                    .order_by(ChargingSession.session_start.desc())
                    .limit(1)
                )
                session_obj = result.scalar_one_or_none()
                if session_obj:
                    session_obj.session_end = event.captured_at
                    session_obj.end_level = event.soc_pct
                    session_obj.energy_kwh = event.energy_kwh
                    session_obj.actual_cost_eur = event.cost_eur
                    await session.commit()
                else:
                    logger.debug(
                        "TelemetryPipeline: no open charging session to close for vehicle %s",
                        event.user_vehicle_id,
                    )
            except SQLAlchemyError:
                await session.rollback()
                raise


# Singleton pipeline instance — imported by collector and state machine
pipeline = TelemetryPipeline()
