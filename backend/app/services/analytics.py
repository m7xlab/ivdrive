import asyncio
import logging
from datetime import datetime, UTC
from uuid import UUID

from sqlalchemy import select, update
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

logger = logging.getLogger(__name__)

async def process_completed_trips_and_charges(user_vehicle_id: UUID) -> None:
    """
    Runs after telemetry is gathered. 
    Maintains an open Trip or ChargingSession if active, and closes them with final deltas when parked/unplugged.
    """
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
                    # Start a new trip!
                    new_trip = Trip(
                        user_vehicle_id=user_vehicle_id,
                        start_date=latest_conn.captured_at,
                        start_lat=latest_pos.latitude if latest_pos else None,
                        start_lon=latest_pos.longitude if latest_pos else None,
                        start_odometer=latest_odom.mileage_in_km if latest_odom else None,
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

                    if open_trip.start_odometer and open_trip.end_odometer:
                        open_trip.distance_km = float(open_trip.end_odometer - open_trip.start_odometer)
                        
                    if open_trip.start_soc and open_trip.end_soc:
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
                    open_trip.end_date = datetime.now(UTC)
                    open_trip.end_lat = latest_pos.latitude if latest_pos else None
                    open_trip.end_lon = latest_pos.longitude if latest_pos else None
                    open_trip.end_odometer = latest_odom.mileage_in_km if latest_odom else None
                    open_trip.end_soc = latest_charge.battery_pct if latest_charge else None
                    
                    if open_trip.start_odometer and open_trip.end_odometer:
                        open_trip.distance_km = float(open_trip.end_odometer - open_trip.start_odometer)
                    
                    v_res = await session.execute(select(UserVehicle).where(UserVehicle.id == user_vehicle_id))
                    veh = v_res.scalar_one_or_none()

                    if open_trip.start_soc and open_trip.end_soc:
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


            # --- CHARGING SESSIONS LOGIC ---
            is_charging = latest_charge and latest_charge.state in ("CHARGING", "READY_FOR_CHARGING")
            
            open_charge_res = await session.execute(
                select(ChargingSession).where(ChargingSession.user_vehicle_id == user_vehicle_id, ChargingSession.session_end.is_(None))
            )
            open_charge = open_charge_res.scalar_one_or_none()

            if is_charging:
                if not open_charge:
                    new_charge = ChargingSession(
                        user_vehicle_id=user_vehicle_id,
                        session_start=latest_charge.first_date,
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
                    if latest_pos and latest_pos.outside_temp_celsius:
                        if open_charge.avg_temp_celsius is None:
                            open_charge.avg_temp_celsius = latest_pos.outside_temp_celsius
                        else:
                            open_charge.avg_temp_celsius = (open_charge.avg_temp_celsius + latest_pos.outside_temp_celsius) / 2.0
                    
                    # Update live charging variables
                    open_charge.end_level = latest_charge.battery_pct if latest_charge else open_charge.end_level
                    
                    if open_charge.start_level and open_charge.end_level:
                        soc_added = open_charge.end_level - open_charge.start_level
                        v_res = await session.execute(select(UserVehicle).where(UserVehicle.id == user_vehicle_id))
                        veh = v_res.scalar_one_or_none()
                        capacity_kwh = getattr(veh, "battery_capacity_kwh", 77.0) if veh else 77.0
                        if capacity_kwh is None: capacity_kwh = 77.0
                        
                        if soc_added > 0:
                            added_kwh = (soc_added / 100.0) * capacity_kwh
                            open_charge.energy_kwh = added_kwh
            else:
                if open_charge:
                    open_charge.session_end = datetime.now(UTC)
                    open_charge.end_level = latest_charge.battery_pct if latest_charge else None
                    
                    if open_charge.start_level and open_charge.end_level:
                        soc_added = open_charge.end_level - open_charge.start_level
                        v_res = await session.execute(select(UserVehicle).where(UserVehicle.id == user_vehicle_id))
                        veh = v_res.scalar_one_or_none()
                        capacity_kwh = getattr(veh, "battery_capacity_kwh", 77.0) if veh else 77.0
                        if capacity_kwh is None: capacity_kwh = 77.0
                        
                        if soc_added > 0:
                            added_kwh = (soc_added / 100.0) * capacity_kwh
                            open_charge.energy_kwh = added_kwh
                            
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
                                open_charge.base_cost_eur = added_kwh * float(eco_price.electricity_price_kwh_eur)
                            else:
                                # Fallback if no energy price found
                                np_price = await fetch_nordpool_price()
                                open_charge.base_cost_eur = added_kwh * np_price
                    
                    logger.info("Ended ChargingSession for %s (Cost: %s EUR)", user_vehicle_id, open_charge.base_cost_eur)

            await session.commit()
            
    except Exception as e:
        logger.error("Error in analytics processing for %s: %s", user_vehicle_id, e)

