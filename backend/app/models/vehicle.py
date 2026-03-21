import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class UserVehicle(TimestampMixin, Base):
    __tablename__ = "user_vehicles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vin_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    vin_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    model_year: Mapped[str | None] = mapped_column(String(4))
    license_plate_encrypted: Mapped[str | None] = mapped_column(Text)
    connector_config_encrypted: Mapped[str | None] = mapped_column(Text)
    collection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    parked_interval_seconds: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    wltp_range_km: Mapped[float | None] = mapped_column(Float)

    image_url: Mapped[str | None] = mapped_column(Text)
    body_type: Mapped[str | None] = mapped_column(String(50))
    trim_level: Mapped[str | None] = mapped_column(String(100))
    exterior_colour: Mapped[str | None] = mapped_column(String(50))
    battery_capacity_kwh: Mapped[float | None] = mapped_column(Float)
    max_charging_power_kw: Mapped[float | None] = mapped_column(Float)
    engine_power_kw: Mapped[float | None] = mapped_column(Float)
    software_version: Mapped[str | None] = mapped_column(String(100))
    capabilities: Mapped[list | None] = mapped_column(JSONB)
    specifications: Mapped[dict | None] = mapped_column(JSONB)
    warning_lights: Mapped[list | None] = mapped_column(JSONB)
    country_code: Mapped[str] = mapped_column(String(2), default="LT", nullable=False)

    user: Mapped["User"] = relationship(back_populates="vehicles")  # noqa: F821
    connector_session: Mapped["ConnectorSession | None"] = relationship(
        back_populates="user_vehicle", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    drives: Mapped[list["Drive"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    charging_sessions: Mapped[list["ChargingSession"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    charging_states: Mapped[list["ChargingState"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    vehicle_states: Mapped[list["VehicleState"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    vehicle_positions: Mapped[list["VehiclePosition"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    trips: Mapped[list["Trip"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    air_conditioning_states: Mapped[list["AirConditioningState"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    maintenance_reports: Mapped[list["MaintenanceReport"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    odometer_readings: Mapped[list["OdometerReading"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    battery_health_records: Mapped[list["BatteryHealth"]] = relationship(
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    power_usage_records: Mapped[list["PowerUsage"]] = relationship(
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )
    charging_curves: Mapped[list["ChargingCurve"]] = relationship(
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )

    connection_states: Mapped[list["ConnectionState"]] = relationship(  # noqa: F821
        back_populates="user_vehicle", cascade="all, delete-orphan", lazy="noload"
    )


class ConnectorSession(TimestampMixin, Base):
    __tablename__ = "connector_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_vehicles.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    connector_type: Mapped[str] = mapped_column(String(50), default="skoda", nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    user_vehicle: Mapped["UserVehicle"] = relationship(back_populates="connector_session")
