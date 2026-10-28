import asyncio
import logging
from datetime import datetime, timedelta, UTC
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.telemetry import (
    ConnectionState,
    ChargingState,
    OdometerReading,
    VehiclePosition,
    DriveRange,
    Trip,
    ChargingSession,
)
from app.models.vehicle import UserVehicle
from app.services.external_apis import fetch_nordpool_price

from app.services.external_apis import reverse_geocode_country
from app.services.trip_reconcile import reconcile_zero_distance_trips

logger = logging.getLogger(__name__)

# Škoda often never reports state=CHARGING. Home AC shows CONNECT_CABLE with
# charge_power_kw=0 the whole time while SoC still rises. Smart-poll used to
# treat that as parked (30 min), so charging_sessions were never opened.
PLUGGED_IN_STATES = frozenset({
    "CHARGING",
    "READY_FOR_CHARGING",
    "CONNECT_CABLE",
    "CHARGING_INTERRUPTED",
    "CONSERVING",
})


def is_plugged_in(state: str | None) -> bool:
    """True when the vehicle is on a cable / charging, not merely parked."""
    return bool(state) and state.upper() in PLUGGED_IN_STATES


def is_actively_charging(state: str | None, charge_power_kw: float | None = None) -> bool:
    """True when energy is actually flowing into the pack (or state says CHARGING).

    Used only for smart-poll intensity (Active vs Parked). A cable with 0 kW
    (CONNECT_CABLE overnight) is *plugged in* but must NOT keep the collector
    in Active full-fetch mode — use is_plugged_in() for charging sessions.
    """
    if not state:
        return False
    if state.upper() == "CHARGING":
        return True
    if is_plugged_in(state) and charge_power_kw is not None and charge_power_kw > 0:
        return True
    return False


FLAT_SOC_MINUTES = 30
# Trip start odometer backfill: ignore noise below MIN, refuse implausible jumps above MAX.
MIN_BACKFILL_KM = 0.5
MAX_BACKFILL_KM = 300.0


def should_start_session(
    *,
    state: str | None,
    charge_power_kw: float | None,
    new_soc: float | None,
    prev_soc: float | None,
    same_plug_event_session: bool = False,
) -> bool:
    """True when a *new* ChargingSession may be opened.

    `same_plug_event_session`: a session was already recorded for this plug-in
    (cable never removed since). Then only real power flow may open another one;
    a 1 % SoC tick at the charging->cable state change is not a new charge.

    A cable in the socket alone (CONNECT_CABLE / CONSERVING / READY_FOR_CHARGING
    at 0 kW with flat SoC) is not a charge. Without this guard, the flat-SoC
    auto-close and the next poll formed a close/reopen loop of empty sessions.
    Home AC that reports 0 kW is still captured when SoC is rising.
    """
    if not is_plugged_in(state):
        return False
    if is_actively_charging(state, charge_power_kw):
        return True
    if same_plug_event_session:
        return False
    return (
        new_soc is not None
        and prev_soc is not None
        and (new_soc - prev_soc) >= 0.5
    )


def _as_naive_utc(dt: datetime | None) -> datetime | None:
    """Compare DB timestamps safely whether the driver returns naive or aware."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def should_close_open_session(
    *,
    state: str | None,
    charge_power_kw: float | None,
    last_soc: float | None,
    new_soc: float | None,
    last_activity_at: datetime | None,
    now: datetime,
) -> bool:
    """True when an open ChargingSession should be closed.

    Long low-power AC stays open (active). A finished charge with the cable
    still connected (0 kW, SoC flat) closes after FLAT_SOC_MINUTES.
    A new charge after a gap (SoC dropped — the pack was used in between)
    closes the previous open session even while the new charge is active.
    """
    if not is_plugged_in(state):
        return True
    now_c = _as_naive_utc(now)
    last_c = _as_naive_utc(last_activity_at)
    # New charge after a gap: SoC dropped significantly, so the open row
    # belongs to a previous charge. Close it even though power is flowing.
    if (
        last_soc is not None
        and new_soc is not None
        and (last_soc - new_soc) >= 0.5
        and last_c is not None
        and (now_c - last_c) >= timedelta(minutes=FLAT_SOC_MINUTES)
    ):
        return True
    if is_actively_charging(state, charge_power_kw):
        return False
    # Plugged in, not actively charging: close once SoC has been flat long enough
    soc_flat = last_soc is None or new_soc is None or abs(new_soc - last_soc) < 0.5
    if not soc_flat:
        return False
    if last_c is None:
        return True
    return (now_c - last_c) >= timedelta(minutes=FLAT_SOC_MINUTES)


async def _session_exists_at(session: AsyncSession, vehicle_id: UUID, start: datetime) -> bool:
    """uq_charging_sessions_vehicle_start: re-inserting the same start aborts the whole poll."""
    res = await session.execute(
        select(ChargingSession.id)
        .where(ChargingSession.user_vehicle_id == vehicle_id, ChargingSession.session_start == start)
        .limit(1)
    )
    return res.first() is not None


async def process_completed_trips_and_charges(
    user_vehicle_id: UUID, now: datetime | None = None
) -> None:
    """
    Runs after telemetry is gathered. 
    Maintains an open Trip or ChargingSession if active, and closes them with final deltas when parked/unplugged.

    `now` is injectable so recorded telemetry can be replayed deterministically in tests.
    """
    clock = now or datetime.now(UTC)
    try:
        async with async_session() as session:
            # 1. Get latest vehicle state
            conn_res = await session.execute(
                select(ConnectionState).where(ConnectionState.user_vehicle_id == user_vehicle_id)
                .order_by(ConnectionState.captured_at.desc()).limit(1)
            )
            latest_conn = conn_res.scalar_one_or_none()
            
            charge_res = await session.execute(
                select(ChargingState).where(ChargingState.user_vehicle_id == user_vehicle_id)
                .order_by(ChargingState.first_date.desc()).limit(1)
            )
            latest_charge = charge_res.scalar_one_or_none()
            
            pos_res = await session.execute(
                select(VehiclePosition).where(VehiclePosition.user_vehicle_id == user_vehicle_id)
                .order_by(VehiclePosition.captured_at.desc()).limit(1)
            )
            latest_pos = pos_res.scalar_one_or_none()

            odom_res = await session.execute(
                select(OdometerReading).where(OdometerReading.user_vehicle_id == user_vehicle_id)
                .order_by(OdometerReading.captured_at.desc()).limit(1)
            )
            latest_odom = odom_res.scalar_one_or_none()

            # --- TRIPS LOGIC ---
            is_driving = latest_conn and (latest_conn.in_motion or latest_conn.ignition_on)
            
            # Find open trip
            open_trip_res = await session.execute(
                select(Trip).where(Trip.user_vehicle_id == user_vehicle_id, Trip.end_date.is_(None))
            )
            open_trip = open_trip_res.scalar_one_or_none()

            if is_driving:
                if not open_trip:
                    # Start a new trip! Departure is usually noticed one poll late
                    # (parked polls are minutes apart), so begin at the last odometer
                    # reading we saw before this one instead of discarding that distance.
                    start_odo = latest_odom.mileage_in_km if latest_odom else None
                    start_quality = None
                    if latest_odom is not None:
                        prev_odo_res = await session.execute(
                            select(OdometerReading.mileage_in_km)
                            .where(
                                OdometerReading.user_vehicle_id == user_vehicle_id,
                                OdometerReading.captured_at < latest_odom.captured_at,
                            )
                            .order_by(OdometerReading.captured_at.desc())
                            .limit(1)
                        )
                        prev_odo = prev_odo_res.scalar_one_or_none()
                        last_end_res = await session.execute(
                            select(Trip.end_odometer)
                            .where(Trip.user_vehicle_id == user_vehicle_id, Trip.end_date.is_not(None))
                            .order_by(Trip.end_date.desc())
                            .limit(1)
                        )
                        last_end = last_end_res.scalar_one_or_none()
                        floor = max((v for v in (prev_odo, last_end) if v is not None), default=None)
                        if floor is not None and 0 < latest_odom.mileage_in_km - floor <= MAX_BACKFILL_KM:
                            if latest_odom.mileage_in_km - floor >= MIN_BACKFILL_KM:
                                start_quality = "estimated_start"
                            start_odo = floor
                    new_trip = Trip(
                        user_vehicle_id=user_vehicle_id,
                        start_date=latest_conn.captured_at,
                        data_quality=start_quality,
                        start_lat=latest_pos.latitude if latest_pos else None,
                        start_lon=latest_pos.longitude if latest_pos else None,
                        start_odometer=start_odo,
                        start_soc=latest_charge.battery_pct if latest_charge else None,
                        avg_temp_celsius=latest_pos.outside_temp_celsius if latest_pos else None
                    )
                    session.add(new_trip)
                    logger.info("Started new Trip for %s", user_vehicle_id)
                else:
                    # Update running average temp
                    if latest_pos and latest_pos.outside_temp_celsius:
                        if open_trip.avg_temp_celsius is None:
                            open_trip.avg_temp_celsius = latest_pos.outside_temp_celsius
                        else:
                            open_trip.avg_temp_celsius = (open_trip.avg_temp_celsius + latest_pos.outside_temp_celsius) / 2.0
                    
                    # Update live tracking variables
                    open_trip.end_lat = latest_pos.latitude if latest_pos else open_trip.end_lat
                    open_trip.end_lon = latest_pos.longitude if latest_pos else open_trip.end_lon
                    open_trip.end_odometer = latest_odom.mileage_in_km if latest_odom else open_trip.end_odometer
                    open_trip.end_soc = latest_charge.battery_pct if latest_charge else open_trip.end_soc

                    if open_trip.start_odometer is not None and open_trip.end_odometer is not None:
                        open_trip.distance_km = float(open_trip.end_odometer - open_trip.start_odometer)
                        
                    if open_trip.start_soc is not None and open_trip.end_soc is not None:
                        soc_used = open_trip.start_soc - open_trip.end_soc
                        v_res = await session.execute(select(UserVehicle).where(UserVehicle.id == user_vehicle_id))
                        veh = v_res.scalar_one_or_none()
                        capacity_kwh = getattr(veh, "battery_capacity_kwh", 77.0) if veh else 77.0
                        if capacity_kwh is None: capacity_kwh = 77.0
                        if soc_used > 0:
                            open_trip.kwh_consumed = (soc_used / 100.0) * capacity_kwh
            else:
                if open_trip:
                    # End the trip! Calculate deltas.
                    open_trip.end_date = latest_conn.captured_at if latest_conn else clock
                    open_trip.end_lat = latest_pos.latitude if latest_pos else None
                    open_trip.end_lon = latest_pos.longitude if latest_pos else None
                    open_trip.end_odometer = latest_odom.mileage_in_km if latest_odom else None
                    open_trip.end_soc = latest_charge.battery_pct if latest_charge else None
                    
                    if open_trip.start_odometer is not None and open_trip.end_odometer is not None:
                        open_trip.distance_km = float(open_trip.end_odometer - open_trip.start_odometer)
                    
                    v_res = await session.execute(select(UserVehicle).where(UserVehicle.id == user_vehicle_id))
                    veh = v_res.scalar_one_or_none()

                    if open_trip.start_soc is not None and open_trip.end_soc is not None:
                        soc_used = open_trip.start_soc - open_trip.end_soc
                        # Needs total capacity. Let's fetch the vehicle
                        capacity_kwh = getattr(veh, "battery_capacity_kwh", 77.0) if veh else 77.0
                        if capacity_kwh is None: capacity_kwh = 77.0 # Default fallback
                        
                        if soc_used > 0:
                            open_trip.kwh_consumed = (soc_used / 100.0) * capacity_kwh
                            
                    logger.info("Ended Trip for %s (Dist: %s km, Consumed: %s kWh)", user_vehicle_id, open_trip.distance_km, open_trip.kwh_consumed)

                    # --- Automatic Country Code Update ---
                    if open_trip.end_lat and open_trip.end_lon:
                        try:
                            detected_cc = await reverse_geocode_country(open_trip.end_lat, open_trip.end_lon)
                            if detected_cc and veh:
                                if getattr(veh, "country_code", None) != detected_cc:
                                    logger.info("Auto-updating country_code for %s from %s to %s based on trip end location", user_vehicle_id, getattr(veh, "country_code", None), detected_cc)
                                    veh.country_code = detected_cc
                                    session.add(veh)
                        except Exception as e:
                            logger.warning("Failed to auto-update country code: %s", e)


            # Odometer lags the moving state: give recently closed 0 km trips their
            # distance once a later reading arrives (cheap; recent trips only).
            await reconcile_zero_distance_trips(
                session, user_vehicle_id, since=clock - timedelta(hours=3), apply=True
            )

            # --- CHARGING SESSIONS LOGIC ---
            is_charging = is_plugged_in(latest_charge.state if latest_charge else None)

            open_charge_res = await session.execute(
                select(ChargingSession)
                .where(ChargingSession.user_vehicle_id == user_vehicle_id, ChargingSession.session_end.is_(None))
                .order_by(ChargingSession.session_start.desc())
            )
            open_charges = list(open_charge_res.scalars().all())
            open_charge = open_charges[0] if open_charges else None
            extras = open_charges[1:]

            now = clock

            # Vehicle capacity/country is constant — fetch once for this run.
            v_res = await session.execute(
                select(UserVehicle).where(UserVehicle.id == user_vehicle_id)
            )
            veh = v_res.scalar_one_or_none()
            charge_state = latest_charge.state if latest_charge else None
            charge_power = getattr(latest_charge, "charge_power_kw", None) if latest_charge else None
            new_soc = (
                float(latest_charge.battery_pct)
                if latest_charge and latest_charge.battery_pct is not None
                else None
            )

            def _session_last_soc(ch: ChargingSession) -> float | None:
                if ch.end_level is not None:
                    return float(ch.end_level)
                if ch.start_level is not None:
                    return float(ch.start_level)
                return None

            def _should_close(ch: ChargingSession) -> bool:
                # latest_charge.last_date is refreshed every poll and would never look
                # stale; the session's own last SoC change is the real activity clock
                # (falls back to session_start for rows opened before it existed).
                return should_close_open_session(
                    state=charge_state,
                    charge_power_kw=charge_power,
                    last_soc=_session_last_soc(ch),
                    new_soc=new_soc,
                    last_activity_at=ch.last_soc_change_at or ch.session_start,
                    now=now,
                )

            async def _close_session(ch: ChargingSession, *, set_end_level: bool) -> None:
                ch.session_end = now
                if set_end_level:
                    ch.end_level = latest_charge.battery_pct if latest_charge else ch.end_level

                if ch.start_level is not None and ch.end_level is not None:
                    soc_added = ch.end_level - ch.start_level
                    capacity_kwh = getattr(veh, "battery_capacity_kwh", 77.0) if veh else 77.0
                    if capacity_kwh is None:
                        capacity_kwh = 77.0

                    if soc_added > 0:
                        added_kwh = (soc_added / 100.0) * capacity_kwh
                        ch.energy_kwh = added_kwh

                        # Get country code and fetch energy price
                        country_code = getattr(veh, "country_code", "LT")
                        from app.models.fuel_price import CountryEconomics
                        eco_res = await session.execute(
                            select(CountryEconomics)
                            .where(CountryEconomics.country_code == country_code)
                            .order_by(CountryEconomics.date.desc())
                            .limit(1)
                        )
                        eco_price = eco_res.scalar_one_or_none()

                        if not eco_price and country_code != "LT":
                            eco_res_fallback = await session.execute(
                                select(CountryEconomics)
                                .where(CountryEconomics.country_code == "LT")
                                .order_by(CountryEconomics.date.desc())
                                .limit(1)
                            )
                            eco_price = eco_res_fallback.scalar_one_or_none()

                        if eco_price and eco_price.electricity_price_kwh_eur:
                            ch.base_cost_eur = added_kwh * float(eco_price.electricity_price_kwh_eur)
                        else:
                            # Fallback if no energy price found
                            np_price = await fetch_nordpool_price()
                            ch.base_cost_eur = added_kwh * np_price

                logger.info("Ended ChargingSession for %s (Cost: %s EUR)", user_vehicle_id, ch.base_cost_eur)

            if is_charging:
                # Keep the newest open row; older duplicates are inconsistent
                # state and must not stay open (they blocked later charges).
                for extra in extras:
                    await _close_session(extra, set_end_level=False)

                prev_charge_res = await session.execute(
                    select(ChargingState.battery_pct)
                    .where(
                        ChargingState.user_vehicle_id == user_vehicle_id,
                        ChargingState.first_date < latest_charge.first_date,
                    )
                    .order_by(ChargingState.first_date.desc())
                    .limit(1)
                )
                prev_soc = prev_charge_res.scalar_one_or_none()
                prev_soc = float(prev_soc) if prev_soc is not None else None

                same_plug_event = False
                last_session_end = None
                if not open_charge or _should_close(open_charge):
                    # Same plug-in as the last recorded session? Skoda reports
                    # CONNECT_CABLE for an idle car too, so "no unplugged state row"
                    # is not enough: a trip since that session, or a lower SoC, means
                    # the car was used and the next rise is a genuinely new charge.
                    last_row = (await session.execute(
                        select(
                            ChargingSession.session_start, ChargingSession.end_level,
                            ChargingSession.start_level, ChargingSession.session_end,
                        )
                        .where(
                            ChargingSession.user_vehicle_id == user_vehicle_id,
                            ChargingSession.session_start.is_not(None),
                        )
                        .order_by(ChargingSession.session_start.desc())
                        .limit(1)
                    )).first()
                    if last_row is not None:
                        last_start, last_end, last_begin, last_session_end = last_row
                        last_level = last_end if last_end is not None else last_begin
                        soc_dropped = (
                            new_soc is not None and last_level is not None
                            and new_soc <= float(last_level) - 0.5
                        )
                        used_since = (await session.execute(
                            select(Trip.id).where(
                                Trip.user_vehicle_id == user_vehicle_id,
                                Trip.start_date > last_start,
                            ).limit(1)
                        )).first() is not None
                        unplugged_since = (await session.execute(
                            select(ChargingState.id).where(
                                ChargingState.user_vehicle_id == user_vehicle_id,
                                ChargingState.first_date > last_start,
                                ChargingState.state.is_not(None),
                                func.upper(ChargingState.state).not_in(sorted(PLUGGED_IN_STATES)),
                            ).limit(1)
                        )).first() is not None
                        same_plug_event = not (soc_dropped or used_since or unplugged_since)

                start_new_session = should_start_session(
                    state=charge_state,
                    charge_power_kw=charge_power,
                    new_soc=new_soc,
                    prev_soc=prev_soc,
                    same_plug_event_session=same_plug_event,
                )
                if open_charge and _should_close(open_charge):
                    # Gap (new charge after driving) or the previous charge
                    # finished with the cable still in. Close it; a new session
                    # opens only if energy is actually flowing again.
                    await _close_session(open_charge, set_end_level=False)
                    open_charge = None

                # A state row that merged across several days (CONNECT_CABLE) keeps its old
                # first_date; a charge starting now must not reuse an earlier session's start.
                new_session_start = latest_charge.first_date
                if last_session_end is not None and _as_naive_utc(new_session_start) <= _as_naive_utc(last_session_end):
                    new_session_start = now

                if open_charge:
                    if latest_pos and latest_pos.outside_temp_celsius:
                        if open_charge.avg_temp_celsius is None:
                            open_charge.avg_temp_celsius = latest_pos.outside_temp_celsius
                        else:
                            open_charge.avg_temp_celsius = (open_charge.avg_temp_celsius + latest_pos.outside_temp_celsius) / 2.0

                    # Update live charging variables
                    prev_level = _session_last_soc(open_charge)
                    open_charge.end_level = latest_charge.battery_pct if latest_charge else open_charge.end_level
                    if new_soc is not None and (prev_level is None or abs(new_soc - prev_level) >= 0.5):
                        open_charge.last_soc_change_at = now

                    if open_charge.start_level is not None and open_charge.end_level is not None:
                        soc_added = open_charge.end_level - open_charge.start_level
                        capacity_kwh = getattr(veh, "battery_capacity_kwh", 77.0) if veh else 77.0
                        if capacity_kwh is None:
                            capacity_kwh = 77.0

                        if soc_added > 0:
                            added_kwh = (soc_added / 100.0) * capacity_kwh
                            open_charge.energy_kwh = added_kwh
                elif start_new_session and not await _session_exists_at(
                    session, user_vehicle_id, new_session_start
                ):
                    new_charge = ChargingSession(
                        user_vehicle_id=user_vehicle_id,
                        session_start=new_session_start,
                        last_soc_change_at=now,
                        start_level=latest_charge.battery_pct,
                        charging_type=latest_charge.charge_type if latest_charge else None,
                        latitude=latest_pos.latitude if latest_pos else None,
                        longitude=latest_pos.longitude if latest_pos else None,
                        odometer=latest_odom.mileage_in_km if latest_odom else None,
                        avg_temp_celsius=latest_pos.outside_temp_celsius if latest_pos else None,
                    )
                    session.add(new_charge)
                    logger.info("Started new ChargingSession for %s (type: %s)", user_vehicle_id, latest_charge.charge_type if latest_charge else "unknown")
            else:
                for ch in open_charges:
                    if _should_close(ch):
                        await _close_session(ch, set_end_level=True)

            await session.commit()
            
    except Exception as e:
        logger.error("Error in analytics processing for %s: %s", user_vehicle_id, e)

