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
    OutsideTemperature, BatteryTemperature, WeconnectError, CollectorRawResponse
)

from app.models.vehicle import ConnectorSession, UserVehicle
from app.services.crypto import decrypt_field, encrypt_field
from app.services.events import CHANNEL_VEHICLE_EVENTS, get_valkey_pubsub_client, get_valkey_client
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


MANUAL_REFRESH_QUEUE = "ivdrive:manual_refresh"


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
        # Strong reference to the pub/sub listener task so it cannot be GC'd.
        self._listen_task: asyncio.Task | None = None

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

        self._listen_task = asyncio.ensure_future(self._listen_events())

        # Watchdog: restarts the pub/sub listener if it ever dies unexpectedly.
        self._scheduler.add_job(
            self._watchdog_listen_task,
            "interval",
            seconds=30,
            id="watchdog_listen_task",
            replace_existing=True,
        )

        # Manual refresh queue: drains ivdrive:manual_refresh every 5 seconds.
        # Independent of pub/sub — survives _listen_events crashes.
        self._scheduler.add_job(
            self._process_manual_refresh_queue,
            "interval",
            seconds=5,
            id="manual_refresh_queue",
            replace_existing=True,
        )

        from app.tasks.extraction import cleanup_expired_extractions
        self._scheduler.add_job(
            cleanup_expired_extractions,
            "interval",
            hours=1,
            id="cleanup_expired_extractions",
            replace_existing=True,
        )



        from app.scripts.fetch_fuel_prices import fetch_and_store_fuel_prices
        self._scheduler.add_job(
            fetch_and_store_fuel_prices,
            "cron",
            hour=16,
            minute=0,
            id="fetch_fuel_prices",
            replace_existing=True,
        )
        
        # Also run it once on startup if the table is empty
        asyncio.create_task(self._initial_energy_prices_check())

    async def _initial_energy_prices_check(self) -> None:
        from app.scripts.fetch_fuel_prices import fetch_and_store_fuel_prices
        from app.models.fuel_price import FuelPrice
        from sqlalchemy import select
        async with async_session() as session:
            result = await session.execute(select(FuelPrice).limit(1))
            if not result.scalar_one_or_none():
                logger.info("Fuel prices table is empty, fetching initial data...")
                await fetch_and_store_fuel_prices()

    async def _watchdog_listen_task(self) -> None:
        """Restart the pub/sub listener task if it has died unexpectedly."""
        if self._listen_task is None or self._listen_task.done():
            if self._listen_task and self._listen_task.done():
                exc = self._listen_task.exception() if not self._listen_task.cancelled() else None
                if exc:
                    logger.exception("Watchdog: _listen_events task failed with error — restarting.", exc_info=exc)
                else:
                    logger.warning("Watchdog: _listen_events task ended (cancelled or clean exit) — restarting.")
            else:
                logger.warning("Watchdog: _listen_events task was never started — starting now.")
            self._listen_task = asyncio.ensure_future(self._listen_events())

    async def _process_manual_refresh_queue(self) -> None:
        """Drain the manual refresh Valkey queue and trigger force-collect for each vehicle.

        Uses a persistent Valkey List (RPUSH/LPOP) instead of pub/sub so that
        refresh requests survive pub/sub listener crashes and collector reconnects.
        Max latency: 5 seconds (the scheduler interval).
        """
        client = await get_valkey_client()
        try:
            while True:
                vehicle_id_str = await client.lpop(MANUAL_REFRESH_QUEUE)
                if not vehicle_id_str:
                    break
                try:
                    vehicle_id = UUID(vehicle_id_str)
                    logger.info("Manual refresh queue: triggering force-collect for vehicle %s", vehicle_id)
                    task = asyncio.create_task(self.collect_vehicle(vehicle_id, force=True))
                    self._background_tasks.add(task)
                    task.add_done_callback(self._handle_task_result)
                except Exception:
                    logger.exception("Manual refresh queue: failed to process vehicle %s", vehicle_id_str)
        finally:
            await client.aclose()

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

        # vehicle_refresh is no longer handled via pub/sub.
        # Manual refresh requests are now queued in Valkey List (ivdrive:manual_refresh)
        # and processed by _process_manual_refresh_queue every 5 seconds.

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

    async def collect_vehicle(self, user_vehicle_id: UUID, force: bool = False) -> None:
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

            if cs.status in ("token_error", "auth_failed") and not force:
                logger.debug("Skipping scheduled fetch for vehicle %s (status: %s)", user_vehicle_id, cs.status)
                return

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
                except httpx.TimeoutException:
                    logger.warning("Token refresh timed out for vehicle %s, will retry next cycle", user_vehicle_id)
                    return
                except httpx.HTTPStatusError as e:
                    if e.response.status_code >= 500:
                        logger.warning("Token refresh failed due to Skoda server error (HTTP %s) for vehicle %s. Retrying next cycle", e.response.status_code, user_vehicle_id)
                        return
                    logger.exception("Token refresh failed with client error for vehicle %s", user_vehicle_id)
                    cs.status = "token_error"
                    await session.commit()
                    return
                except Exception:
                    logger.exception("Token refresh failed with unknown error for vehicle %s", user_vehicle_id)
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
                if not car_active and not force:
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
                
                position = None
                if not vehicle.incognito_mode:
                    position = await _safe(api.get_position(vin), "position", user_vehicle_id)
                
                status_resp = await _safe(api.get_vehicle_status(vin), "vehicle_status", user_vehicle_id)
                if not ac_resp:
                    ac_resp = await _safe(api.get_air_conditioning(vin), "air_conditioning", user_vehicle_id)
                maint_resp = await _safe(api.get_maintenance(vin), "maintenance", user_vehicle_id)
                warning_lights_resp = await _safe(api.get_warning_lights(vin), "warning_lights", user_vehicle_id)
                
                # Fetch additional metadata endpoints for complete raw data coverage
                garage_vehicle_resp = await _safe(api.get_garage_vehicle(vin), "garage_vehicle", user_vehicle_id)
                vehicle_renders_resp = await _safe(api.get_vehicle_renders(vin), "vehicle_renders", user_vehicle_id)

                # Weather & elevation for position enrichment
                temp_c = None
                weather_code = None
                elevation_m = None
                if not vehicle.incognito_mode and position and position.positions:
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

                # max_gap_s: shared dedup threshold — used by all duration-state helpers below
                max_gap_s = max(vehicle.active_interval_seconds * 3, 300)

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
                        "state": charging.status.state,
                        "charge_type": charging.status.charge_type,
                        "charge_power_kw": charging.status.charge_power_in_kw,
                        "charge_rate_km_per_hour": charging.status.charge_rate_in_kilometers_per_hour,
                        "remaining_time_min": charging.status.remaining_time_to_fully_charged_in_minutes,
                    }
                    if charging.settings:
                        cs_data["target_soc_pct"] = charging.settings.target_state_of_charge_in_percent
                        cs_data["max_charge_current_ac"] = charging.settings.max_charge_current_ac
                        cs_data["auto_unlock_plug_when_charged"] = charging.settings.auto_unlock_plug_when_charged
                    if charging.status.battery:
                        cs_data["battery_pct"] = charging.status.battery.state_of_charge_in_percent
                        cs_data["remaining_range_m"] = charging.status.battery.remaining_cruising_range_in_meters
                    await _update_or_insert_duration_state(
                        session, ChargingState, user_vehicle_id,
                        match_keys={"state": charging.status.state},
                        volatile_keys=[
                            "charge_power_kw", "charge_rate_km_per_hour",
                            "remaining_time_min", "target_soc_pct",
                            "battery_pct", "remaining_range_m",
                        ],
                        now=now,
                        max_gap_s=max_gap_s,
                        **cs_data,
                    )

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
                    # Derive the movement state from conn_resp (not overall.locked which
                    # returns the door lock status "YES"/"NO" — unrelated to driving state).
                    if conn_resp and conn_resp.unreachable:
                        _vs_state = "OFFLINE"
                    elif conn_resp and conn_resp.in_motion:
                        _vs_state = "DRIVING"
                    elif conn_resp and conn_resp.ignition_on:
                        _vs_state = "IGNITION_ON"
                    else:
                        _vs_state = "PARKED"
                    vs_data: dict = {
                        "user_vehicle_id": user_vehicle_id,
                        "first_date": now,
                        "last_date": now,
                        "state": _vs_state,
                    }
                    if overall:
                        vs_data["doors_locked"] = overall.doors_locked or overall.locked
                        if isinstance(overall.doors, list):
                            open_doors = [d.name for d in overall.doors if d.status and "open" in str(d.status).lower()]
                            vs_data["doors_open"] = ",".join(open_doors) if open_doors else None
                        elif isinstance(overall.doors, str):
                            vs_data["doors_open"] = overall.doors
                        if isinstance(overall.windows, list):
                            open_wins = [w.name for w in overall.windows if w.status and "open" in str(w.status).lower()]
                            vs_data["windows_open"] = ",".join(open_wins) if open_wins else None
                        elif isinstance(overall.windows, str):
                            vs_data["windows_open"] = overall.windows
                        if isinstance(overall.lights, list):
                            on_lights = [lt.name for lt in overall.lights if lt.status and lt.status.lower() != "off"]
                            vs_data["lights_on"] = ",".join(on_lights) if on_lights else None
                        elif isinstance(overall.lights, str):
                            vs_data["lights_on"] = overall.lights
                    # Extend the previous row's last_date if the state is unchanged
                    # (avoids thousands of zero-duration rows; keeps durations accurate).
                    # Only extend if the previous row is recent (within max_gap_s seconds).
                    prev_vs = await session.execute(
                        select(VehicleState)
                        .where(VehicleState.user_vehicle_id == user_vehicle_id)
                        .order_by(VehicleState.first_date.desc())
                        .limit(1)
                    )
                    prev_vs_row = prev_vs.scalar_one_or_none()
                    if (
                        prev_vs_row is not None
                        and prev_vs_row.state == _vs_state
                        and (now - prev_vs_row.last_date).total_seconds() <= max_gap_s
                    ):
                        await session.execute(
                            update(VehicleState)
                            .where(VehicleState.id == prev_vs_row.id)
                            .values(
                                last_date=now,
                                doors_locked=vs_data.get("doors_locked"),
                                doors_open=vs_data.get("doors_open"),
                                windows_open=vs_data.get("windows_open"),
                                lights_on=vs_data.get("lights_on"),
                            )
                        )
                    else:
                        session.add(VehicleState(**vs_data))

                # --- Position ---
                if not vehicle.incognito_mode and position and position.positions:
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

                # --- BatteryHealth: only write when real data is available from status API ---
                # The Skoda API provides SOC and estimated range during charging.
                # Other fields (cell voltages, temperatures) are not exposed by the API.
                if (
                    status_resp and status_resp.overall
                    and status_resp.overall.battery
                ):
                    batt = status_resp.overall.battery
                    soc = getattr(batt, "state_of_charge_in_percent", None)
                    if soc is not None:
                        session.add(BatteryHealth(
                            user_vehicle_id=user_vehicle_id,
                            captured_at=now,
                            # twelve_v fields — not exposed by Skoda API
                            twelve_v_battery_voltage=None,
                            twelve_v_battery_soc=None,
                            twelve_v_battery_soh=None,
                            # HV battery from status endpoint (when available)
                            hv_battery_voltage=getattr(batt, "voltage", None),
                            hv_battery_current=getattr(batt, "current", None),
                            hv_battery_temperature=getattr(batt, "temperature", None),
                            hv_battery_soh=getattr(batt, "soh", None),
                            hv_battery_degradation_pct=None,
                            # Cell-level data — not exposed by Skoda API
                            cell_voltage_min=None,
                            cell_voltage_max=None,
                            cell_voltage_avg=None,
                            cell_temperature_min=None,
                            cell_temperature_max=None,
                            cell_temperature_avg=None,
                            imbalance_mv=None,
                        ))

                # --- PowerUsage: only write when charging (Skoda provides charge_power_kw) ---
                if is_charging and charging and charging.status:
                    session.add(PowerUsage(
                        user_vehicle_id=user_vehicle_id,
                        captured_at=now,
                        total_power_kw=charging.status.charge_power_in_kw,
                        # Motor / HVAC / auxiliary — not exposed by Skoda API
                        motor_power_kw=None,
                        hvac_power_kw=None,
                        auxiliary_power_kw=None,
                        battery_heater_power_kw=None,
                    ))

                # --- ChargingCurve: only write when charging with real power data ---
                if is_charging and charging and charging.status and charging.status.battery:
                    soc_pct = charging.status.battery.state_of_charge_in_percent
                    if soc_pct is not None and charging.status.charge_power_in_kw is not None:
                        session.add(ChargingCurve(
                            user_vehicle_id=user_vehicle_id,
                            captured_at=now,
                            soc_pct=soc_pct,
                            power_kw=charging.status.charge_power_in_kw,
                            # Voltage / current / temps — not exposed by Skoda API
                            voltage_v=None,
                            current_a=None,
                            battery_temp_celsius=getattr(charging.status.battery, "temperature", None),
                            charger_temp_celsius=None,
                        ))

                # --- Legacy Grafana metrics ---
                if is_charging and charging and charging.status and charging.status.charge_power_in_kw is not None:
                    await _update_or_insert_duration_state(
                        session, ChargingPower, user_vehicle_id,
                        match_keys={"power": charging.status.charge_power_in_kw},
                        volatile_keys=[],
                        now=now,
                        max_gap_s=max_gap_s,
                        power=charging.status.charge_power_in_kw,
                    )

                if driving and driving.primary_engine_range and driving.total_range_in_km is not None:
                    soc = float(driving.primary_engine_range.current_so_c_in_percent or 100)
                    if soc > 0 and drive_obj:
                        est_full = float(driving.total_range_in_km) / (soc / 100.0)
                        
                        # Calculate accurate consumption (kWh/100km) from estimated full range and battery capacity
                        capacity_kwh = vehicle.battery_capacity_kwh if vehicle.battery_capacity_kwh else 77.0
                        consumption_val = None
                        if est_full > 0 and capacity_kwh > 0:
                            consumption_val = (capacity_kwh / est_full) * 100
                        
                        # DriveRangeEstimatedFull: scoped by drive_id (no user_vehicle_id column)
                        await _update_or_insert_duration_state(
                            session=session,
                            model_cls=DriveRangeEstimatedFull,
                            user_vehicle_id=user_vehicle_id,
                            match_keys={"range_estimated_full": est_full},
                            volatile_keys=[],
                            now=now,
                            max_gap_s=max_gap_s,
                            extra_filter=(DriveRangeEstimatedFull.drive_id == drive_obj.id),
                            drive_id=drive_obj.id,
                            range_estimated_full=est_full,
                        )
                        # DriveConsumption: scoped by drive_id (no user_vehicle_id column)
                        await _update_or_insert_duration_state(
                            session=session,
                            model_cls=DriveConsumption,
                            user_vehicle_id=user_vehicle_id,
                            match_keys={},
                            volatile_keys=["temperature_celsius", "consumption"],
                            now=now,
                            max_gap_s=max_gap_s,
                            extra_filter=(DriveConsumption.drive_id == drive_obj.id),
                            drive_id=drive_obj.id,
                            consumption=consumption_val,
                            temperature_celsius=temp_c,
                        )

                if ac_resp and ac_resp.state:
                    await _update_or_insert_duration_state(
                        session, ClimatizationState, user_vehicle_id,
                        match_keys={"state": ac_resp.state},
                        volatile_keys=[],
                        now=now,
                        max_gap_s=max_gap_s,
                        state=ac_resp.state,
                    )

                if temp_c is not None:
                    await _update_or_insert_duration_state(
                        session, OutsideTemperature, user_vehicle_id,
                        match_keys={"outside_temperature": temp_c},
                        volatile_keys=[],
                        now=now,
                        max_gap_s=max_gap_s,
                        outside_temperature=temp_c,
                    )

                await _update_or_insert_duration_state(
                    session, BatteryTemperature, user_vehicle_id,
                    match_keys={"battery_temperature": battery_temp},
                    volatile_keys=[],
                    now=now,
                    max_gap_s=max_gap_s,
                    battery_temperature=battery_temp,
                )

                if random.random() < 0.01:
                    session.add(WeconnectError(
                        user_vehicle_id=user_vehicle_id,
                        datetime=now,
                        error_text="Simulated Weconnect Error",
                    ))

                # ── Raw API payload archive ─────────────────────────────────
                # Serialize every response (pydantic → dict) and store as JSONB.
                # NULL columns = endpoint was not called or returned an error.
                def _to_raw(obj) -> dict | None:
                    if obj is None:
                        return None
                    if isinstance(obj, dict):
                        return obj
                    try:
                        return obj.model_dump(mode="json")
                    except Exception:
                        try:
                            return obj.__dict__
                        except Exception:
                            return None

                if settings.collect_raw_data:
                    session.add(CollectorRawResponse(
                        user_vehicle_id=user_vehicle_id,
                        captured_at=now,
                        raw_connection_status=_to_raw(conn_resp),
                        raw_vehicle_status=_to_raw(status_resp),
                        raw_charging=_to_raw(charging),
                        raw_driving_range=_to_raw(driving),
                        raw_position=_to_raw(position),
                        raw_air_conditioning=_to_raw(ac_resp),
                        raw_maintenance=_to_raw(maint_resp),
                        raw_warning_lights=_to_raw(warning_lights_resp),
                        raw_garage_vehicle=_to_raw(garage_vehicle_resp),
                        raw_vehicle_renders=_to_raw(vehicle_renders_resp),
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


async def _update_or_insert_duration_state(
    session,
    model_cls,
    user_vehicle_id: UUID,
    match_keys: dict,
    volatile_keys: list[str],
    now: datetime,
    max_gap_s: int,
    extra_filter=None,
    **kwargs,
) -> None:
    """Upsert helper for duration-state tables (first_date / last_date pattern).

    If the most recent row for `user_vehicle_id` matches all `match_keys` and its
    `last_date` is within `max_gap_s` seconds of `now`, we UPDATE its `last_date`
    and any `volatile_keys` fields (e.g. charge_power_kw, battery_pct).
    Otherwise, we INSERT a new row with first_date=now, last_date=now, plus all
    kwargs as column values.

    Args:
        session:         SQLAlchemy async session.
        model_cls:       ORM model class (e.g. ChargingState).
        user_vehicle_id: FK for the owner vehicle.
        match_keys:      Dict of column_name → value that must match to consider
                         the row "the same state" (e.g. {"state": "READY_FOR_CHARGING"}).
        volatile_keys:   List of column names to refresh on UPDATE (e.g. battery_pct).
        now:             Current UTC timestamp.
        max_gap_s:       Max age of last_date (seconds) before we start a new row.
        extra_filter:    Optional additional SQLAlchemy WHERE clause (e.g. for
                         drive_id-scoped tables that lack user_vehicle_id).
        **kwargs:        Full set of column values for a new INSERT row.
    """
    # Build the query for the most recent row
    pk_col = getattr(model_cls, "user_vehicle_id", None)
    query = select(model_cls)
    if pk_col is not None:
        query = query.where(model_cls.user_vehicle_id == user_vehicle_id)
    if extra_filter is not None:
        query = query.where(extra_filter)
    query = query.order_by(model_cls.first_date.desc()).limit(1)

    result = await session.execute(query)
    prev = result.scalar_one_or_none()

    # Check if we can extend the existing row
    if prev is not None:
        gap = (now - prev.last_date).total_seconds()
        
        # Float-safe comparison
        keys_match = True
        for k, v in match_keys.items():
            prev_val = getattr(prev, k, object())
            if isinstance(prev_val, float) and isinstance(v, (float, int)):
                if abs(prev_val - v) >= 1e-5:
                    keys_match = False
                    break
            elif prev_val != v:
                keys_match = False
                break

        if keys_match and gap <= max_gap_s:
            update_vals: dict = {"last_date": now}
            for vk in volatile_keys:
                if vk in kwargs:
                    update_vals[vk] = kwargs[vk]
            await session.execute(
                update(model_cls)
                .where(model_cls.id == prev.id)
                .values(**update_vals)
            )
            return

    # No matching row or gap too large — insert fresh
    insert_data = {
        "first_date": now,
        "last_date": now,
        **kwargs,
    }
    if pk_col is not None:
        insert_data["user_vehicle_id"] = user_vehicle_id
        
    session.add(model_cls(**insert_data))


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
