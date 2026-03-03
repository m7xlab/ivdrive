from app.config import settings
import os
import json
import random
from sqlalchemy.orm import selectinload
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from uuid import UUID
import logging
import asyncio
from datetime import UTC, datetime, timedelta
import httpx
from sqlalchemy import select, update, delete
from app.database import async_session
from app.models.telemetry import (
    Trip, ChargingSession, VehiclePosition, ChargingState, ConnectionState,
    VehicleState, AirConditioningState, MaintenanceReport, OdometerReading,
    DriveLevel, DriveRange, Drive, BatteryHealth, PowerUsage, ChargingCurve,
    ChargingPower, DriveRangeEstimatedFull, DriveConsumption, ClimatizationState,
    OutsideTemperature, BatteryTemperature, WeconnectError
)

from app.models.vehicle import ConnectorSession, UserVehicle
from app.services.crypto import decrypt_field, encrypt_field
from app.services.events import CHANNEL_VEHICLE_EVENTS, get_valkey_pubsub_client
from app.services.analytics import process_completed_trips_and_charges
from app.services.external_apis import fetch_weather_and_elevation, fetch_nordpool_price
from app.services.skoda_api import SkodaAPIClient
from app.services.skoda_auth import SkodaAuthClient

logger = logging.getLogger(__name__)


def _extract_render_url(data: dict, preferred_view: str) -> str | None:
    """Extract the best render URL from garage or renders API response.

    Both endpoints return compositeRenders with nested layers.
    We prefer the given viewPoint, falling back to the first available.
    """
    composites = data.get("compositeRenders") or []
    preferred_view_lower = preferred_view.lower()
    fallback_url: str | None = None

    for composite in composites:
        layers = composite.get("layers") or []
        for layer in layers:
            url = layer.get("url")
            if not url:
                continue
            vp = (layer.get("viewPoint") or "").lower()
            if preferred_view_lower in vp:
                return url
            if fallback_url is None:
                fallback_url = url

    return fallback_url


class DataCollector:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._background_tasks: set = set()
        self._stale_active_counters: dict[UUID, int] = {}  # Tracks extra polls after car stops being "active"
        # Smart Polling v2.3: tracks last known online/offline state per vehicle so we can
        # skip writing a ConnectionState record when nothing changed (avoids thousands of
        # identical rows while the car sits parked overnight).
        # None = unknown (first poll after startup → always write the initial record).
        self._last_connection_state: dict[UUID, bool | None] = {}

    async def start(self) -> None:
        registered = 0
        async with async_session() as session:
            stmt = (
                select(UserVehicle)
                .where(UserVehicle.collection_enabled.is_(True))
                .options(selectinload(UserVehicle.connector_session))
            )
            result = await session.execute(stmt)
            vehicles = result.scalars().all()

        for vehicle in vehicles:
            if vehicle.connector_session and vehicle.connector_session.access_token_encrypted:
                self.register_vehicle(vehicle.id, vehicle.parked_interval_seconds)
                registered += 1

        self._scheduler.start()
        logger.info(
            "DataCollector started: %d vehicles loaded from DB, %d with active tokens",
            len(vehicles), registered,
        )

        SYNC_INTERVAL_SECONDS = 90
        self._scheduler.add_job(
            self._sync_vehicles_from_db,
            "interval",
            seconds=SYNC_INTERVAL_SECONDS,
            id="sync_vehicles_from_db",
            replace_existing=True,
        )

        asyncio.ensure_future(self._listen_events())

    def _get_job_interval_seconds(self, job_id: str) -> int | None:
        """Return the interval in seconds of an existing interval job, or None."""
        job = self._scheduler.get_job(job_id)
        if not job or not getattr(job.trigger, "interval", None):
            return None
        return int(job.trigger.interval.total_seconds())

    async def _sync_vehicles_from_db(self) -> None:
        """Re-load enabled vehicles from DB and re-register scheduler jobs with current intervals.
        Called periodically and on pub/sub connect/reconnect so interval changes in user_vehicles
        are applied even if the vehicle_updated event was missed.
        Only re-registers when the DB interval differs from the job's interval, so we don't
        reset next_run_time every 90s (which would cause collection to run every ~90s).
        """
        async with async_session() as session:
            stmt = (
                select(UserVehicle)
                .where(UserVehicle.collection_enabled.is_(True))
                .options(selectinload(UserVehicle.connector_session))
            )
            result = await session.execute(stmt)
            vehicles = result.scalars().all()
        updated = 0
        for vehicle in vehicles:
            if not (vehicle.connector_session and vehicle.connector_session.access_token_encrypted):
                continue
            job_id = f"collect_{vehicle.id}"
            current = self._get_job_interval_seconds(job_id)
            # v2.3.2: If the job already exists with a valid interval (either parked or active),
            # leave it alone. Re-registering with parked_interval_seconds here would reset 
            # any active polling back to parked every 90 seconds.
            if current is not None:
                continue
            self.register_vehicle(vehicle.id, vehicle.parked_interval_seconds)
            updated += 1
        if updated:
            logger.info("Synced %d vehicles from DB (intervals re-applied)", updated)

    async def _listen_events(self) -> None:
        """Subscribe to Valkey pub/sub and handle vehicle lifecycle events."""
        while True:
            try:
                client = await get_valkey_pubsub_client()
                pubsub = client.pubsub()
                await pubsub.subscribe(CHANNEL_VEHICLE_EVENTS)
                logger.info("Subscribed to %s", CHANNEL_VEHICLE_EVENTS)
                await self._sync_vehicles_from_db()

                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                        await self._handle_event(data)
                    except Exception:
                        logger.exception("Error handling event: %s", message.get("data"))

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Pub/sub connection lost, reconnecting in 5s")
                await asyncio.sleep(5)

    async def _handle_event(self, data: dict) -> None:
        event_type = data.get("type")
        vehicle_id_str = data.get("vehicle_id")
        if not vehicle_id_str:
            return

        vehicle_id = UUID(vehicle_id_str)

        if event_type == "vehicle_linked":
            interval = data.get("interval", settings.default_parked_interval_seconds)
            self.register_vehicle(vehicle_id, interval)
            logger.info("Event: registered vehicle %s (interval=%ds)", vehicle_id, interval)
            asyncio.ensure_future(self._fetch_vehicle_metadata(vehicle_id))

        elif event_type == "vehicle_updated":
            enabled = data.get("enabled", True)
            interval = data.get("interval", settings.default_parked_interval_seconds)
            if enabled:
                self.register_vehicle(vehicle_id, interval)
                logger.info("Event: updated vehicle %s (interval=%ds)", vehicle_id, interval)
            else:
                self.unregister_vehicle(vehicle_id)
                logger.info("Event: disabled collection for vehicle %s", vehicle_id)

        elif event_type == "vehicle_deleted":
            self.unregister_vehicle(vehicle_id)
            logger.info("Event: removed vehicle %s", vehicle_id)

        elif event_type == "vehicle_refresh":
            logger.info("Event: manual refresh requested for vehicle %s", vehicle_id)
            try:
                await self._fetch_vehicle_metadata(vehicle_id)
            except Exception:
                logger.error("Metadata fetch failed", exc_info=True)
            
            task = asyncio.create_task(self.collect_vehicle(vehicle_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._handle_task_result)

    async def _fetch_vehicle_metadata(self, user_vehicle_id: UUID) -> None:
        """One-time fetch of garage data and renders to populate vehicle metadata."""
        async with async_session() as session:
            stmt = (
                select(UserVehicle)
                .where(UserVehicle.id == user_vehicle_id)
                .options(selectinload(UserVehicle.connector_session))
            )
            result = await session.execute(stmt)
            vehicle = result.scalar_one_or_none()
            if not vehicle or not vehicle.connector_session:
                return

            cs = vehicle.connector_session
            if not cs.access_token_encrypted:
                return

            access_token = decrypt_field(cs.access_token_encrypted)
            vin = decrypt_field(vehicle.vin_encrypted)
            api = SkodaAPIClient(access_token)

            try:
                garage_data = await _safe(api.get_garage_vehicle(vin), "garage_vehicle", user_vehicle_id)
                
                spec = dict(vehicle.specifications) if vehicle.specifications else {}
                if garage_data:
                    garage_spec = garage_data.get("specification", {}) or {}
                    spec.update(garage_spec)
                    
                    vehicle.manufacturer = vehicle.manufacturer or "Škoda"
                    vehicle.model = vehicle.model or spec.get("title") or spec.get("model")
                    vehicle.model_year = vehicle.model_year or spec.get("modelYear")
                    vehicle.body_type = spec.get("body")
                    vehicle.trim_level = spec.get("trimLevel")
                    vehicle.exterior_colour = spec.get("exteriorColour")
                    vehicle.software_version = garage_data.get("softwareVersion")

                    battery_spec = spec.get("battery", {}) or {}
                    if battery_spec.get("capacityInKWh"):
                        vehicle.battery_capacity_kwh = float(battery_spec["capacityInKWh"])
                    engine_spec = spec.get("engine", {}) or {}
                    if engine_spec.get("powerInKW"):
                        vehicle.engine_power_kw = float(engine_spec["powerInKW"])
                    if spec.get("maxChargingPowerInKW"):
                        vehicle.max_charging_power_kw = float(spec["maxChargingPowerInKW"])

                    caps = garage_data.get("capabilities", {}).get("capabilities", [])
                    if caps:
                        vehicle.capabilities = caps

                    lp = garage_data.get("licensePlate")
                    if lp and not vehicle.license_plate_encrypted:
                        vehicle.license_plate_encrypted = encrypt_field(lp)

                    vehicle.image_url = _extract_render_url(garage_data, "exterior_front") or _extract_render_url(garage_data, "exterior_side")

                renders_data = await _safe(api.get_vehicle_renders(vin), "renders", user_vehicle_id)
                if renders_data:
                    if not vehicle.image_url:
                        vehicle.image_url = _extract_render_url(renders_data, "EXTERIOR_FRONT") or _extract_render_url(renders_data, "EXTERIOR_SIDE")
                    
                    # Store all renders in specifications
                    all_renders = []
                    composites = renders_data.get("compositeRenders") or []
                    for comp in composites:
                        view_type = comp.get("viewType", "")
                        for layer in comp.get("layers", []):
                            if layer.get("url"):
                                all_renders.append({
                                    "viewType": view_type,
                                    "url": layer.get("url")
                                })
                    
                    if all_renders:
                        spec["renders"] = all_renders

                if spec:
                    vehicle.specifications = spec

                await session.commit()
                logger.info("Metadata fetched for vehicle %s", user_vehicle_id)
            except Exception:
                logger.warning("Failed to fetch metadata for vehicle %s", user_vehicle_id, exc_info=True)
                await session.rollback()
            finally:
                await api.close()

    async def collect_vehicle(self, user_vehicle_id: UUID) -> None:
        async with async_session() as session:
            stmt = (
                select(UserVehicle)
                .where(UserVehicle.id == user_vehicle_id)
                .options(selectinload(UserVehicle.connector_session))
            )
            result = await session.execute(stmt)
            vehicle = result.scalar_one_or_none()

            if not vehicle or not vehicle.connector_session:
                logger.warning("Vehicle %s not found or no session", user_vehicle_id)
                return

            if not vehicle.image_url or not vehicle.model or not vehicle.specifications or not vehicle.specifications.get("renders"):
                try:
                    logger.info("Triggering metadata backfill because specs=%s, image_url=%s", vehicle.specifications, vehicle.image_url)
                    await self._fetch_vehicle_metadata(user_vehicle_id)
                except Exception:
                    logger.warning("Metadata backfill failed for %s", user_vehicle_id, exc_info=True)

            cs: ConnectorSession = vehicle.connector_session

            if not cs.access_token_encrypted or not cs.refresh_token_encrypted:
                logger.warning("Vehicle %s missing tokens", user_vehicle_id)
                return

            access_token = decrypt_field(cs.access_token_encrypted)
            refresh_token = decrypt_field(cs.refresh_token_encrypted)

            if cs.token_expires_at and cs.token_expires_at < datetime.now(UTC) + timedelta(minutes=2):
                logger.info("Token expired for vehicle %s, refreshing", user_vehicle_id)
                auth = SkodaAuthClient()
                try:
                    tokens = await auth.refresh(refresh_token)
                    access_token = tokens.get("accessToken") or tokens.get("access_token", "")
                    refresh_token = tokens.get("refreshToken") or tokens.get("refresh_token", refresh_token)
                    cs.access_token_encrypted = encrypt_field(access_token)
                    cs.refresh_token_encrypted = encrypt_field(refresh_token)
                    expires_in = tokens.get("expiresIn") or tokens.get("expires_in", 3600)
                    cs.token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
                    await session.flush()
                except Exception:
                    logger.exception("Token refresh failed for vehicle %s", user_vehicle_id)
                    cs.status = "token_error"
                    await session.commit()
                    return
                finally:
                    await auth.close()

            vin = decrypt_field(vehicle.vin_encrypted)
            api = SkodaAPIClient(access_token)
            now = datetime.now(UTC)

            try:
                # ══════════════════════════════════════════════════════════════
                # SMART POLLING — Motion-Triggered approach  (v2.3)
                #
                # PARKED  → 1 API call  (connection_status only)
                #           ConnectionState only written when online/offline status CHANGES
                #           (prevents thousands of identical rows while car sleeps overnight)
                # ACTIVE  → full fetch   (all endpoints), save everything
                #           Interval switches to active_interval_seconds IMMEDIATELY when
                #           any of the 3 lightweight probes detect activity.
                #
                # "Active" = moving OR charging OR climatisation running.
                # There is NO periodic full-refresh timer while parked.
                # ══════════════════════════════════════════════════════════════

                # ── Step 1: Connection status (always, 1 API call) ──────────
                conn_resp = await _safe(api.get_connection_status(vin), "connection_status", user_vehicle_id)

                is_online = conn_resp and not conn_resp.unreachable
                is_moving = conn_resp and (conn_resp.in_motion or conn_resp.ignition_on)

                # DEBUG LOG for transition tracking
                logger.info(
                    "Smart poll: vehicle %s status check [online=%s, moving=%s, stale_count=%d]",
                    user_vehicle_id, is_online, is_moving, self._stale_active_counters.get(user_vehicle_id, 0)
                )

                # ── Step 2: Determine activity ──────────────────────────────
                # If clearly moving we can skip the charging/AC probes.
                is_charging = False
                is_ac_on = False
                charging = None
                ac_resp = None

                # Only check secondary status if the car is online.
                # If car is offline/unreachable, it cannot be charging or climatizing via API.
                if is_online:
                    if not is_moving:
                        # Not moving — check charging (2nd API call)
                        charging = await _safe(api.get_charging(vin), "charging", user_vehicle_id)
                        is_charging = (
                            charging and charging.status
                            and charging.status.state == "CHARGING"
                        )

                        if not is_charging:
                            # Not moving, not charging — check AC (3rd API call)
                            ac_resp = await _safe(api.get_air_conditioning(vin), "air_conditioning", user_vehicle_id)
                            is_ac_on = (
                                ac_resp is not None
                                and ac_resp.state is not None
                                and ac_resp.state.upper() in ("ON", "HEATING", "COOLING", "VENTILATION")
                            )

                car_active = is_online and (is_moving or is_charging or is_ac_on)

                # ── Step 3: Stabilization (Smart Polling v2.1) ───────────────
                # When car stops being active, we continue "Active" polling for a few cycles
                # to ensure we capture the final odometer/position/state for analytics.
                STABILIZATION_CYCLES = 3 # ~3 extra polls before dropping to parked interval

                if car_active:
                    # Car is genuinely active, reset the stabilization countdown
                    self._stale_active_counters[user_vehicle_id] = STABILIZATION_CYCLES
                else:
                    # Car is inactive, check if we are still stabilizing from a previous active state
                    count = self._stale_active_counters.get(user_vehicle_id, 0)
                    if count > 0:
                        car_active = True # Force active mode
                        self._stale_active_counters[user_vehicle_id] = count - 1
                        logger.info(
                            "Smart poll: vehicle %s stabilizing (%d extra active polls remaining)",
                            user_vehicle_id, count - 1
                        )
                        if count - 1 == 0:
                            logger.info("Smart poll: stabilization complete for vehicle %s, will return to parked next cycle", user_vehicle_id)

                # ── Step 4: Dynamic interval rescheduling ───────────────────
                # v2.3: When activity is first detected (Parked → Active transition), the
                # interval switches immediately here so the NEXT scheduler tick already
                # fires at active_interval_seconds.  The full fetch below runs in the
                # current cycle, so there is zero lag on the first active collection.
                job_id = f"collect_{user_vehicle_id}"
                desired_interval = vehicle.active_interval_seconds if car_active else vehicle.parked_interval_seconds
                current_interval = self._get_job_interval_seconds(job_id)
                if current_interval and current_interval != desired_interval:
                    self._scheduler.reschedule_job(job_id, trigger='interval', seconds=desired_interval)
                    logger.info(
                        "Smart poll: rescheduled vehicle %s from %ds → %ds (active=%s)",
                        user_vehicle_id, current_interval, desired_interval, car_active,
                    )

                # ── Step 5: PARKED — conditionally save connection state, bail out ─
                # v2.3: Only write a ConnectionState row when the online/offline status
                # has actually changed since the last poll.  This prevents the table from
                # accumulating thousands of identical rows while the car sleeps overnight.
                # On the very first poll after a collector restart (cache is empty) we
                # always write so the DB reflects current reality.
                if not car_active:
                    last_known = self._last_connection_state.get(user_vehicle_id)
                    state_changed = (last_known is None) or (last_known != is_online)

                    if state_changed:
                        session.add(ConnectionState(
                            user_vehicle_id=user_vehicle_id,
                            captured_at=now,
                            is_online=is_online,
                            in_motion=False,
                            ignition_on=conn_resp.ignition_on if conn_resp else None,
                        ))
                        self._last_connection_state[user_vehicle_id] = is_online
                        cs.status = "active"
                        await session.commit()
                        logger.info(
                            "Smart poll: vehicle %s PARKED — state changed (was=%s → now online=%s). "
                            "ConnectionState saved.",
                            user_vehicle_id, last_known, is_online,
                        )
                    else:
                        # No state change → nothing to persist; skip DB round-trip entirely.
                        logger.debug(
                            "Smart poll: vehicle %s PARKED (online=%s, unchanged). "
                            "Skipping DB write.",
                            user_vehicle_id, is_online,
                        )
                    return

                # ══════════════════════════════════════════════════════════════
                # Step 5: ACTIVE — Full fetch of all endpoints
                # ══════════════════════════════════════════════════════════════
                logger.info(
                    "Smart poll: vehicle %s is ACTIVE (moving=%s, charging=%s, ac=%s). Full fetch.",
                    user_vehicle_id, is_moving, is_charging, is_ac_on,
                )

                # Fetch charging if we didn't already (car was detected moving in step 2)
                if charging is None:
                    charging = await _safe(api.get_charging(vin), "charging", user_vehicle_id)

                driving = await _safe(api.get_driving_range(vin), "driving_range", user_vehicle_id)
                position = await _safe(api.get_position(vin), "position", user_vehicle_id)
                status_resp = await _safe(api.get_vehicle_status(vin), "vehicle_status", user_vehicle_id)
                if not ac_resp:
                    ac_resp = await _safe(api.get_air_conditioning(vin), "air_conditioning", user_vehicle_id)
                maint_resp = await _safe(api.get_maintenance(vin), "maintenance", user_vehicle_id)
                warning_lights_resp = await _safe(api.get_warning_lights(vin), "warning_lights", user_vehicle_id)

                # Weather & elevation for position enrichment
                temp_c = None
                weather_code = None
                elevation_m = None
                if position and position.positions:
                    for pos in position.positions:
                        if pos.type == "VEHICLE" and pos.gps_coordinates:
                            lat = pos.gps_coordinates.latitude
                            lon = pos.gps_coordinates.longitude
                            if lat and lon:
                                temp_c, weather_code, elevation_m = await fetch_weather_and_elevation(lat, lon)
                            break

                if os.environ.get("COLLECTOR_DEBUG", "false").lower() == "true":
                    summary = _debug_summary(charging, driving, conn_resp)
                    logger.debug(
                        "Collector API summary vehicle_id=%s: %s",
                        user_vehicle_id,
                        json.dumps(summary, default=str),
                    )

                # ── Persist all telemetry ───────────────────────────────────

                # --- Connection status ---
                # Always written during an ACTIVE cycle (we want the full picture in the DB).
                # Also update the in-memory cache so the parked-state dedup logic stays
                # accurate across Active → Parked transitions.
                if conn_resp:
                    session.add(ConnectionState(
                        user_vehicle_id=user_vehicle_id,
                        captured_at=now,
                        is_online=not conn_resp.unreachable if conn_resp.unreachable is not None else None,
                        in_motion=conn_resp.in_motion,
                        ignition_on=conn_resp.ignition_on,
                    ))
                    self._last_connection_state[user_vehicle_id] = is_online

                # --- Charging state ---
                if charging and charging.status:
                    cs_data = {
                        "user_vehicle_id": user_vehicle_id,
                        "first_date": now,
                        "last_date": now,
                        "state": charging.status.state,
                        "charge_type": charging.status.charge_type,
                        "charge_power_kw": charging.status.charge_power_in_kw,
                        "charge_rate_km_per_hour": charging.status.charge_rate_in_kilometers_per_hour,
                        "remaining_time_min": charging.status.remaining_time_to_fully_charged_in_minutes,
                    }
                    if charging.settings:
                        cs_data["target_soc_pct"] = charging.settings.target_state_of_charge_in_percent
                    if charging.status.battery:
                        cs_data["battery_pct"] = charging.status.battery.state_of_charge_in_percent
                        cs_data["remaining_range_m"] = charging.status.battery.remaining_cruising_range_in_meters
                    session.add(ChargingState(**cs_data))

                # --- Warning lights ---
                if warning_lights_resp and "warningLights" in warning_lights_resp:
                    vehicle.warning_lights = warning_lights_resp.get("warningLights", [])

                # --- Driving range ---
                drive_obj = None
                if driving and driving.primary_engine_range:
                    eng = driving.primary_engine_range
                    drive_obj = Drive(
                        user_vehicle_id=user_vehicle_id,
                        drive_id=f"poll_{now.isoformat()}",
                        type=eng.engine_type or driving.car_type,
                    )
                    session.add(drive_obj)
                    await session.flush()

                    if eng.current_so_c_in_percent is not None:
                        session.add(DriveLevel(
                            drive_id=drive_obj.id,
                            first_date=now,
                            last_date=now,
                            level=float(eng.current_so_c_in_percent),
                        ))

                    range_km = eng.remaining_range_in_km
                    if range_km is None and driving.total_range_in_km is not None:
                        range_km = driving.total_range_in_km
                    if range_km is not None:
                        session.add(DriveRange(
                            drive_id=drive_obj.id,
                            first_date=now,
                            last_date=now,
                            range_km=float(range_km),
                        ))

                # --- Vehicle status ---
                if status_resp:
                    overall = status_resp.overall
                    vs_data: dict = {
                        "user_vehicle_id": user_vehicle_id,
                        "first_date": now,
                        "last_date": now,
                        "state": overall.locked if overall else None,
                    }
                    if overall:
                        vs_data["doors_locked"] = overall.doors_locked or overall.locked
                        if isinstance(overall.doors, list):
                            open_doors = [d.name for d in overall.doors if d.status and "open" in str(d.status).lower()]
                            vs_data["doors_open"] = ",".join(open_doors) if open_doors else None
                        if isinstance(overall.windows, list):
                            open_wins = [w.name for w in overall.windows if w.status and "open" in str(w.status).lower()]
                            vs_data["windows_open"] = ",".join(open_wins) if open_wins else None
                        if isinstance(overall.lights, list):
                            on_lights = [lt.name for lt in overall.lights if lt.status and lt.status.lower() != "off"]
                            vs_data["lights_on"] = ",".join(on_lights) if on_lights else None
                    session.add(VehicleState(**vs_data))

                # --- Position ---
                if position and position.positions:
                    for pos in position.positions:
                        if pos.gps_coordinates:
                            session.add(VehiclePosition(
                                user_vehicle_id=user_vehicle_id,
                                captured_at=now,
                                latitude=pos.gps_coordinates.latitude,
                                longitude=pos.gps_coordinates.longitude,
                                elevation_m=elevation_m,
                                outside_temp_celsius=temp_c,
                                weather_condition=weather_code,
                            ))
                            break

                # --- Air conditioning ---
                if ac_resp:
                    ac_data: dict = {
                        "user_vehicle_id": user_vehicle_id,
                        "captured_at": now,
                        "state": ac_resp.state,
                        "window_heating_enabled": ac_resp.window_heating_enabled,
                        "steering_wheel_position": ac_resp.steering_wheel_position,
                    }
                    if ac_resp.target_temperature:
                        ac_data["target_temp_celsius"] = ac_resp.target_temperature.celsius
                    if ac_resp.outside_temperature:
                        ac_data["outside_temp_celsius"] = ac_resp.outside_temperature.celsius
                    if ac_resp.seat_heating_activated:
                        ac_data["seat_heating_front_left"] = ac_resp.seat_heating_activated.front_left
                        ac_data["seat_heating_front_right"] = ac_resp.seat_heating_activated.front_right
                    session.add(AirConditioningState(**ac_data))

                # --- Maintenance ---
                if maint_resp:
                    session.add(MaintenanceReport(
                        user_vehicle_id=user_vehicle_id,
                        captured_at=now,
                        mileage_in_km=maint_resp.mileage_in_km,
                        inspection_due_in_days=maint_resp.inspection_due_in_days,
                        inspection_due_in_km=maint_resp.inspection_due_in_km,
                        oil_service_due_in_days=maint_resp.oil_service_due_in_days,
                        oil_service_due_in_km=maint_resp.oil_service_due_in_km,
                    ))
                    if maint_resp.mileage_in_km is not None:
                        session.add(OdometerReading(
                            user_vehicle_id=user_vehicle_id,
                            captured_at=now,
                            mileage_in_km=maint_resp.mileage_in_km,
                        ))

                # --- Simulated metrics: BatteryHealth, PowerUsage, ChargingCurve ---
                base_soc = 50.0
                if driving and driving.primary_engine_range and driving.primary_engine_range.current_so_c_in_percent is not None:
                    base_soc = float(driving.primary_engine_range.current_so_c_in_percent)

                battery_temp = 20.0
                if temp_c is not None:
                    battery_temp = temp_c + 5.0
                elif is_charging:
                    battery_temp = 35.0

                session.add(BatteryHealth(
                    user_vehicle_id=user_vehicle_id,
                    captured_at=now,
                    twelve_v_battery_voltage=12.1 + random.uniform(0, 0.6) if not is_moving else 14.4 + random.uniform(-0.1, 0.1),
                    twelve_v_battery_soc=random.uniform(85, 99),
                    twelve_v_battery_soh=98.5,
                    hv_battery_voltage=380.0 + (base_soc * 0.4),
                    hv_battery_current=0.0 if not is_charging and not is_moving else (random.uniform(10, 100) if is_charging else random.uniform(-200, 200)),
                    hv_battery_temperature=battery_temp,
                    hv_battery_soh=95.0,
                    hv_battery_degradation_pct=5.0,
                    cell_voltage_min=3.5 + (base_soc * 0.006),
                    cell_voltage_max=3.5 + (base_soc * 0.006) + random.uniform(0.01, 0.05),
                    cell_voltage_avg=3.5 + (base_soc * 0.006) + 0.02,
                    cell_temperature_min=battery_temp - 1.0,
                    cell_temperature_max=battery_temp + 2.0,
                    cell_temperature_avg=battery_temp,
                    imbalance_mv=random.uniform(5, 25),
                ))

                session.add(PowerUsage(
                    user_vehicle_id=user_vehicle_id,
                    captured_at=now,
                    total_power_kw=random.uniform(0, 50) if is_moving else (random.uniform(1, 3) if is_ac_on else 0.0),
                    motor_power_kw=random.uniform(0, 45) if is_moving else 0.0,
                    hvac_power_kw=random.uniform(1, 4) if is_ac_on else 0.0,
                    auxiliary_power_kw=random.uniform(0.2, 0.5),
                    battery_heater_power_kw=random.uniform(1, 5) if is_charging and battery_temp < 15 else 0.0,
                ))

                if is_charging and charging and charging.status:
                    session.add(ChargingCurve(
                        user_vehicle_id=user_vehicle_id,
                        captured_at=now,
                        soc_pct=base_soc,
                        power_kw=charging.status.charge_power_in_kw or random.uniform(10, 50),
                        voltage_v=380.0 + (base_soc * 0.4),
                        current_a=(charging.status.charge_power_in_kw or 50) * 1000 / (380.0 + (base_soc * 0.4)),
                        battery_temp_celsius=battery_temp,
                        charger_temp_celsius=battery_temp + random.uniform(5, 10),
                    ))

                # --- Legacy Grafana metrics ---
                if is_charging and charging and charging.status and charging.status.charge_power_in_kw is not None:
                    session.add(ChargingPower(
                        user_vehicle_id=user_vehicle_id,
                        first_date=now,
                        last_date=now,
                        power=charging.status.charge_power_in_kw,
                    ))

                if driving and driving.primary_engine_range and driving.total_range_in_km is not None:
                    soc = float(driving.primary_engine_range.current_so_c_in_percent or 100)
                    if soc > 0 and drive_obj:
                        est_full = float(driving.total_range_in_km) / (soc / 100.0)
                        session.add(DriveRangeEstimatedFull(
                            drive_id=drive_obj.id,
                            first_date=now,
                            last_date=now,
                            range_estimated_full=est_full,
                        ))
                        session.add(DriveConsumption(
                            drive_id=drive_obj.id,
                            first_date=now,
                            last_date=now,
                            consumption=16.5 + random.uniform(-2, 3),
                        ))

                if ac_resp and ac_resp.state:
                    session.add(ClimatizationState(
                        user_vehicle_id=user_vehicle_id,
                        first_date=now,
                        last_date=now,
                        state=ac_resp.state,
                    ))

                if temp_c is not None:
                    session.add(OutsideTemperature(
                        user_vehicle_id=user_vehicle_id,
                        first_date=now,
                        last_date=now,
                        outside_temperature=temp_c,
                    ))

                session.add(BatteryTemperature(
                    user_vehicle_id=user_vehicle_id,
                    first_date=now,
                    last_date=now,
                    battery_temperature=battery_temp,
                ))

                if random.random() < 0.01:
                    session.add(WeconnectError(
                        user_vehicle_id=user_vehicle_id,
                        datetime=now,
                        error_text="Simulated Weconnect Error",
                    ))

                # ── Commit & update timestamp ───────────────────────────────
                cs.last_fetch_at = now
                cs.status = "active"
                await session.commit()
                logger.info("Collection complete for vehicle %s (ACTIVE full fetch)", user_vehicle_id)

                # Async analytics in background
                task = asyncio.create_task(process_completed_trips_and_charges(user_vehicle_id))
                self._background_tasks.add(task)
                task.add_done_callback(self._handle_task_result)

            except Exception:
                logger.exception("Collection failed for vehicle %s", user_vehicle_id)
                await session.rollback()
            finally:
                await api.close()

    def _handle_task_result(self, task: asyncio.Task) -> None:
        self._background_tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error("Background task failed with exception: %s", task.exception(), exc_info=task.exception())

    def register_vehicle(self, user_vehicle_id: UUID, interval: int) -> None:
        job_id = f"collect_{user_vehicle_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
        self._scheduler.add_job(
            self.collect_vehicle,
            "interval",
            seconds=interval,
            args=[user_vehicle_id],
            id=job_id,
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=60,
            next_run_time=datetime.now(UTC),
        )
        logger.info("Registered collection job %s every %ds (first run NOW)", job_id, interval)

    def unregister_vehicle(self, user_vehicle_id: UUID) -> None:
        job_id = f"collect_{user_vehicle_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("Unregistered collection job %s", job_id)


async def _safe(coro, label: str, vehicle_id: UUID):
    try:
        return await coro
    except Exception:
        logger.warning("Failed to fetch %s for vehicle %s", label, vehicle_id, exc_info=True)
        return None


def _debug_summary(charging, driving, conn_resp) -> dict:
    """Build a small summary of API responses for debug logging."""
    out = {}
    if charging and charging.status:
        st = charging.status
        out["charging"] = {
            "state": getattr(st, "state", None),
            "charge_power_kw": getattr(st, "charge_power_in_kw", None),
            "charge_rate_km_h": getattr(st, "charge_rate_in_kilometers_per_hour", None),
            "remaining_time_min": getattr(st, "remaining_time_to_fully_charged_in_minutes", None),
            "battery_pct": st.battery.state_of_charge_in_percent if getattr(st, "battery", None) else None,
        }
    if driving:
        prim = getattr(driving, "primary_engine_range", None)
        out["driving_range"] = {
            "car_type": getattr(driving, "car_type", None),
            "total_km": getattr(driving, "total_range_in_km", None),
            "primary_soc": prim.current_so_c_in_percent if prim else None,
            "primary_range_km": prim.remaining_range_in_km if prim else None,
        }
    if conn_resp is not None:
        out["connection"] = {
            "unreachable": getattr(conn_resp, "unreachable", None),
            "in_motion": getattr(conn_resp, "in_motion", None),
            "ignition_on": getattr(conn_resp, "ignition_on", None),
        }
    return out
