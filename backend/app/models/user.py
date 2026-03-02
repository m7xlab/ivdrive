import uuid

from sqlalchemy import Boolean, Integer, JSON, String, Text
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

    vehicles: Mapped[list["UserVehicle"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    geofences: Mapped[list["Geofence"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
