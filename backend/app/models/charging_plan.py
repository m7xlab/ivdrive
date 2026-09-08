import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class UserChargingPlan(TimestampMixin, Base):
    __tablename__ = "user_charging_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    periodicity: Mapped[str | None] = mapped_column(String(20))
    subscription_start_date: Mapped[date | None] = mapped_column(Date)
    monthly_fee_eur: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    kwh_allotment: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    overage_price_per_kwh_eur: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    price_per_kwh_eur: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    geofence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("geofences.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="charging_plans")  # noqa: F821
    geofence: Mapped["Geofence | None"] = relationship()  # noqa: F821
