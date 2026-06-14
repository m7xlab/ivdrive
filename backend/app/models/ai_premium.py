import uuid
from datetime import datetime
from sqlalchemy import Boolean, Integer, Numeric, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin, generate_uuid


class AITierConfig(TimestampMixin, Base):
    __tablename__ = "ai_tier_configs"

    tier: Mapped[str] = mapped_column(String(20), primary_key=True)
    max_questions_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_questions_per_month: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="deterministic")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    daily_cost_limit_usd: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class AIUserOverride(TimestampMixin, Base):
    __tablename__ = "ai_user_overrides"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    ai_enabled_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tier_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    max_questions_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_questions_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])


class AIUsageLog(Base):
    __tablename__ = "ai_usage_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_vehicles.id", ondelete="SET NULL"), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    model_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user = relationship("User")
    vehicle = relationship("UserVehicle")
