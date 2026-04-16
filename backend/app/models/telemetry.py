"""Time-series telemetry models. All use bigint PKs and user_vehicle_id scoping."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Any

from app.models.base import Base


class Drive(Base):
    __tablename__ = "drives"
    __table_args__ = (UniqueConstraint("user_vehicle_id", "drive_id", name="uq_drives_vehicle_drive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    drive_id: Mapped[str | None] = mapped_column(String(50))
    type: Mapped[str | None] = mapped_column(String(20))
    capacity: Mapped[float | None] = mapped_column(Float)
    capacity_total: Mapped[float | None] = mapped_column(Float)
    wltp_range: Mapped[float | None] = mapped_column(Float)

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="drives")  # noqa: F821
    levels: Mapped[list["DriveLevel"]] = relationship(
        back_populates="drive", cascade="all, delete-orphan", lazy="noload"
    )
    ranges: Mapped[list["DriveRange"]] = relationship(
        back_populates="drive", cascade="all, delete-orphan", lazy="noload"
    )


class DriveLevel(Base):
    __tablename__ = "drive_levels"
    __table_args__ = (UniqueConstraint("drive_id", "first_date", name="uq_drive_levels_drive_first"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    drive_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("drives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[float | None] = mapped_column(Float)

    drive: Mapped["Drive"] = relationship(back_populates="levels")


class DriveRange(Base):
    __tablename__ = "drive_ranges"
    __table_args__ = (UniqueConstraint("drive_id", "first_date", name="uq_drive_ranges_drive_first"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    drive_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("drives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    range_km: Mapped[float | None] = mapped_column(Float)

    drive: Mapped["Drive"] = relationship(back_populates="ranges")


class ChargingSession(Base):
    __tablename__ = "charging_sessions"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "session_start", name="uq_charging_sessions_vehicle_start"),
        Index("ix_cs_vehicle_session_start", "user_vehicle_id", "session_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_level: Mapped[float | None] = mapped_column(Float)
    end_level: Mapped[float | None] = mapped_column(Float)
    charging_type: Mapped[str | None] = mapped_column(String(30))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    odometer: Mapped[float | None] = mapped_column(Float)
    energy_kwh: Mapped[float | None] = mapped_column(Float)

    # Pricing & Economics (iVDrive v2 Analytics)
    base_cost_eur: Mapped[float | None] = mapped_column(Float)
    actual_cost_eur: Mapped[float | None] = mapped_column(Float)
    provider_name: Mapped[str | None] = mapped_column(String(100))
    avg_temp_celsius: Mapped[float | None] = mapped_column(Float)

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="charging_sessions")  # noqa: F821


class ChargingState(Base):
    __tablename__ = "charging_states"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "first_date", name="uq_charging_states_vehicle_first"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str | None] = mapped_column(String(30))
    charge_power_kw: Mapped[float | None] = mapped_column(Float)
    charge_rate_km_per_hour: Mapped[float | None] = mapped_column(Float)
    remaining_time_min: Mapped[int | None] = mapped_column(Integer)
    target_soc_pct: Mapped[int | None] = mapped_column(Integer)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    remaining_range_m: Mapped[int | None] = mapped_column(Integer)
    charge_type: Mapped[str | None] = mapped_column(String(30))
    max_charge_current_ac: Mapped[str | None] = mapped_column(String(50))
    auto_unlock_plug_when_charged: Mapped[str | None] = mapped_column(String(50))

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="charging_states")  # noqa: F821


class VehicleState(Base):
    __tablename__ = "vehicle_states"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "first_date", name="uq_vehicle_states_vehicle_first"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str | None] = mapped_column(String(30))
    doors_locked: Mapped[str | None] = mapped_column(String(30))
    doors_open: Mapped[str | None] = mapped_column(String(200))
    windows_open: Mapped[str | None] = mapped_column(String(200))
    lights_on: Mapped[str | None] = mapped_column(String(200))
    trunk_open: Mapped[bool | None] = mapped_column(Boolean)
    bonnet_open: Mapped[bool | None] = mapped_column(Boolean)

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="vehicle_states")  # noqa: F821


class VehiclePosition(Base):
    __tablename__ = "vehicle_positions"
    __table_args__ = (
        Index("ix_vp_vehicle_captured_at", "user_vehicle_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Environmental & Spatial Context (iVDrive v2 Analytics)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    outside_temp_celsius: Mapped[float | None] = mapped_column(Float)
    weather_condition: Mapped[str | None] = mapped_column(String(50))

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="vehicle_positions")  # noqa: F821


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "start_date", name="uq_trips_vehicle_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_lat: Mapped[float | None] = mapped_column(Float)
    start_lon: Mapped[float | None] = mapped_column(Float)
    end_lat: Mapped[float | None] = mapped_column(Float)
    end_lon: Mapped[float | None] = mapped_column(Float)
    start_odometer: Mapped[float | None] = mapped_column(Float)
    end_odometer: Mapped[float | None] = mapped_column(Float)
    
    # Analytics (iVDrive v2 Analytics)
    distance_km: Mapped[float | None] = mapped_column(Float)
    start_soc: Mapped[int | None] = mapped_column(Integer)
    end_soc: Mapped[int | None] = mapped_column(Integer)
    kwh_consumed: Mapped[float | None] = mapped_column(Float)
    avg_temp_celsius: Mapped[float | None] = mapped_column(Float)

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="trips")  # noqa: F821


class AirConditioningState(Base):
    __tablename__ = "air_conditioning_states"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "captured_at", name="uq_ac_states_vehicle_captured"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str | None] = mapped_column(String(30))
    target_temp_celsius: Mapped[float | None] = mapped_column(Float)
    outside_temp_celsius: Mapped[float | None] = mapped_column(Float)
    seat_heating_front_left: Mapped[bool | None] = mapped_column(Boolean)
    seat_heating_front_right: Mapped[bool | None] = mapped_column(Boolean)
    window_heating_enabled: Mapped[bool | None] = mapped_column(Boolean)
    steering_wheel_position: Mapped[str | None] = mapped_column(String(30))

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="air_conditioning_states")  # noqa: F821


class MaintenanceReport(Base):
    __tablename__ = "maintenance_reports"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "captured_at", name="uq_maintenance_vehicle_captured"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mileage_in_km: Mapped[int | None] = mapped_column(Integer)
    inspection_due_in_days: Mapped[int | None] = mapped_column(Integer)
    inspection_due_in_km: Mapped[int | None] = mapped_column(Integer)
    oil_service_due_in_days: Mapped[int | None] = mapped_column(Integer)
    oil_service_due_in_km: Mapped[int | None] = mapped_column(Integer)

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="maintenance_reports")  # noqa: F821


class OdometerReading(Base):
    __tablename__ = "odometer_readings"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "captured_at", name="uq_odometer_vehicle_captured"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mileage_in_km: Mapped[int] = mapped_column(Integer, nullable=False)

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="odometer_readings")  # noqa: F821


class ConnectionState(Base):
    __tablename__ = "connection_states"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "captured_at", name="uq_conn_states_vehicle_captured"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_online: Mapped[bool | None] = mapped_column(Boolean)
    in_motion: Mapped[bool | None] = mapped_column(Boolean)
    ignition_on: Mapped[bool | None] = mapped_column(Boolean)

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="connection_states")  # noqa: F821


class BatteryHealth(Base):
    __tablename__ = "battery_health"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "captured_at", name="uq_battery_health_vehicle_captured"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # 12V Battery
    twelve_v_battery_voltage: Mapped[float | None] = mapped_column(Float)
    twelve_v_battery_soc: Mapped[float | None] = mapped_column(Float)
    twelve_v_battery_soh: Mapped[float | None] = mapped_column(Float)
    
    # HV Battery
    hv_battery_voltage: Mapped[float | None] = mapped_column(Float)
    hv_battery_current: Mapped[float | None] = mapped_column(Float)
    hv_battery_temperature: Mapped[float | None] = mapped_column(Float)
    hv_battery_soh: Mapped[float | None] = mapped_column(Float)
    hv_battery_degradation_pct: Mapped[float | None] = mapped_column(Float)
    
    # Cell level data (could be stored as JSON or average/min/max)
    cell_voltage_min: Mapped[float | None] = mapped_column(Float)
    cell_voltage_max: Mapped[float | None] = mapped_column(Float)
    cell_voltage_avg: Mapped[float | None] = mapped_column(Float)
    cell_temperature_min: Mapped[float | None] = mapped_column(Float)
    cell_temperature_max: Mapped[float | None] = mapped_column(Float)
    cell_temperature_avg: Mapped[float | None] = mapped_column(Float)
    imbalance_mv: Mapped[float | None] = mapped_column(Float)
    
    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="battery_health_records")


class PowerUsage(Base):
    __tablename__ = "power_usage"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "captured_at", name="uq_power_usage_vehicle_captured"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Consumption metrics
    total_power_kw: Mapped[float | None] = mapped_column(Float)
    motor_power_kw: Mapped[float | None] = mapped_column(Float)
    hvac_power_kw: Mapped[float | None] = mapped_column(Float)
    auxiliary_power_kw: Mapped[float | None] = mapped_column(Float)
    battery_heater_power_kw: Mapped[float | None] = mapped_column(Float)
    
    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="power_usage_records")


class ChargingCurve(Base):
    __tablename__ = "charging_curves"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "captured_at", name="uq_charging_curves_vehicle_captured"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[int | None] = mapped_column(ForeignKey("charging_sessions.id", ondelete="CASCADE"))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    soc_pct: Mapped[float | None] = mapped_column(Float)
    power_kw: Mapped[float | None] = mapped_column(Float)
    voltage_v: Mapped[float | None] = mapped_column(Float)
    current_a: Mapped[float | None] = mapped_column(Float)
    battery_temp_celsius: Mapped[float | None] = mapped_column(Float)
    charger_temp_celsius: Mapped[float | None] = mapped_column(Float)
    
    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="charging_curves")



class ChargingPower(Base):
    __tablename__ = "charging_powers"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "first_date", name="uq_charging_powers_vehicle_first"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    power: Mapped[float | None] = mapped_column(Float)

    user_vehicle: Mapped["UserVehicle"] = relationship()


class DriveRangeEstimatedFull(Base):
    __tablename__ = "drive_ranges_estimated_full"
    __table_args__ = (
        UniqueConstraint("drive_id", "first_date", name="uq_dr_estimated_full_drive_first"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    drive_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("drives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    range_estimated_full: Mapped[float | None] = mapped_column(Float)

    drive: Mapped["Drive"] = relationship()


class DriveConsumption(Base):
    __tablename__ = "drive_consumptions"
    __table_args__ = (
        UniqueConstraint("drive_id", "first_date", name="uq_dc_drive_first"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    drive_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("drives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumption: Mapped[float | None] = mapped_column(Float)

    drive: Mapped["Drive"] = relationship()


class ClimatizationState(Base):
    __tablename__ = "climatization_states"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "first_date", name="uq_climatization_states_vehicle_first"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str | None] = mapped_column(String(30))

    user_vehicle: Mapped["UserVehicle"] = relationship()


class OutsideTemperature(Base):
    __tablename__ = "outside_temperatures"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "first_date", name="uq_outside_temp_vehicle_first"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outside_temperature: Mapped[float | None] = mapped_column(Float)

    user_vehicle: Mapped["UserVehicle"] = relationship()


class BatteryTemperature(Base):
    __tablename__ = "battery_temperatures"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "first_date", name="uq_battery_temp_vehicle_first"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    battery_temperature: Mapped[float | None] = mapped_column(Float)

    user_vehicle: Mapped["UserVehicle"] = relationship()


class WeconnectError(Base):
    __tablename__ = "weconnect_errors"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "datetime", name="uq_weconnect_errors_vehicle_dt"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_text: Mapped[str | None] = mapped_column(String(255))

    user_vehicle: Mapped["UserVehicle"] = relationship()


class CollectorRawResponse(Base):
    """Stores the full raw API payloads for every collection cycle.

    One row per vehicle per collection run. Each column holds the raw JSON
    returned by a specific API endpoint (NULL when the endpoint was skipped
    or returned an error). This table is the source-of-truth for debugging
    parsing issues, discovering undocumented fields, and replaying history
    for new metrics without re-querying the Skoda API.
    """

    __tablename__ = "collector_raw_responses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Timestamp of when this collection cycle ran
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Raw JSON blobs — one per API endpoint; NULL when endpoint was not called or failed
    raw_connection_status: Mapped[Any | None] = mapped_column(JSONB)
    raw_vehicle_status: Mapped[Any | None] = mapped_column(JSONB)
    raw_charging: Mapped[Any | None] = mapped_column(JSONB)
    raw_driving_range: Mapped[Any | None] = mapped_column(JSONB)
    raw_position: Mapped[Any | None] = mapped_column(JSONB)
    raw_air_conditioning: Mapped[Any | None] = mapped_column(JSONB)
    raw_maintenance: Mapped[Any | None] = mapped_column(JSONB)
    raw_warning_lights: Mapped[Any | None] = mapped_column(JSONB)
    raw_garage_vehicle: Mapped[Any | None] = mapped_column(JSONB)
    raw_vehicle_renders: Mapped[Any | None] = mapped_column(JSONB)

    user_vehicle: Mapped["UserVehicle"] = relationship()  # noqa: F821


class EnergyPrice(Base):
    """
    Weekly electricity and petrol prices per country from fuel-prices.eu.
    Used for cost/savings calculations.
    """
    __tablename__ = "energy_prices"

    country_code: Mapped[str] = mapped_column(String(2), primary_key=True)
    country_name: Mapped[str] = mapped_column(String(50), nullable=False)
    electricity_price_eur_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    petrol_price_eur_l: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
