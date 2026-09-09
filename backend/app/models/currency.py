from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Currency(TimestampMixin, Base):
    """ISO-4217 currency plus the latest ECB rate vs EUR.

    ``rate_per_eur`` is how many units of this currency equal 1 EUR
    (``CurrencyConverter.convert(1, 'EUR', code)``). EUR itself is 1.
    Storage of costs elsewhere stays in ``*_eur`` columns.
    """

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    rate_per_eur: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="ECB", server_default="ECB", nullable=False)
