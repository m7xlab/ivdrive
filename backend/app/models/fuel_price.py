from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.models.base import Base

class FuelPrice(Base):
    __tablename__ = "fuel_prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    country_code = Column(String(2), nullable=False, index=True)
    week_date = Column(Date, nullable=False, index=True)
    fuel_type = Column(String(50), nullable=False)
    price_eur_liter = Column(Numeric(8, 4), nullable=True)
    price_usd_gallon = Column(Numeric(8, 4), nullable=True)
    weekly_change_pct = Column(Numeric(5, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint('country_code', 'week_date', 'fuel_type', name='uq_fuel_price_country_date_type'),
    )

class PriceBreakdown(Base):
    __tablename__ = "price_breakdowns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    fuel_price_id = Column(UUID(as_uuid=True), ForeignKey('fuel_prices.id', ondelete='CASCADE'), nullable=False, unique=True)
    product_cost_eur = Column(Numeric(8, 4), nullable=True)
    excise_duty_eur = Column(Numeric(8, 4), nullable=True)
    other_taxes_eur = Column(Numeric(8, 4), nullable=True)
    vat_eur = Column(Numeric(8, 4), nullable=True)
    tax_share_pct = Column(Numeric(5, 2), nullable=True)

class CountryEconomics(Base):
    __tablename__ = "country_economics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    country_code = Column(String(2), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    avg_net_monthly_wage_eur = Column(Numeric(10, 2), nullable=True)
    electricity_price_kwh_eur = Column(Numeric(8, 4), nullable=True)
    inflation_rate_pct = Column(Numeric(5, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint('country_code', 'date', name='uq_country_economics_code_date'),
    )

class Vignette(Base):
    __tablename__ = "vignettes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    country_code = Column(String(2), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    price_eur = Column(Numeric(8, 2), nullable=True)
    validity_duration = Column(String(50), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('country_code', 'name', name='uq_vignette_country_name'),
    )
