import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 2FA / TOTP fields
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    is_totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")

    # Phase 4: replay-attack prevention — stores the 30-s TOTP window counter
    # that was last successfully used (epoch // 30). Any reuse within the same
    # window is rejected.
    last_totp_at: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    # Phase 4: recovery codes — list of SHA-256-hashed 8-char alphanumeric codes
    # stored as a JSON array. Each code is consumed (deleted) on use.
    recovery_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)

    # AI Premium gating
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    ai_tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False, server_default="free")
    default_currency: Mapped[str] = mapped_column(
        String(3), default="EUR", nullable=False, server_default="EUR"
    )
    unit_system: Mapped[str] = mapped_column(
        String(16), default="metric", nullable=False, server_default="metric"
    )

    # ABRP (A Better Route Planner) — per-user free Telemetry API key.
    # Per-vehicle tokens live on ABRPConnection.
    abrp_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    # Official MyŠkoda Public API (v1.3.0) — one key per user (bound to VINs in the app)
    skoda_public_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    skoda_public_key_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Human-readable last API problem (e.g. “Your key has expired…”)
    skoda_public_last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Optional MyŠkoda Login — optional advanced channel; password + tokens encrypted
    skoda_login_email: Mapped[str | None] = mapped_column(String(320), nullable=True, default=None)
    skoda_login_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    skoda_login_access_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    skoda_login_refresh_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    vehicles: Mapped[list["UserVehicle"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    extraction_jobs: Mapped[list["ExtractionJob"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    geofences: Mapped[list["Geofence"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    charging_plans: Mapped[list["UserChargingPlan"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
