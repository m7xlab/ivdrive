import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

PlanType = Literal["subscription", "home", "public"]
Periodicity = Literal["monthly", "yearly"]


class ChargingPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    plan_type: PlanType
    periodicity: Periodicity | None = "monthly"
    subscription_start_date: date | None = None
    monthly_fee_eur: float | None = None
    kwh_allotment: float | None = None
    overage_price_per_kwh_eur: float | None = None
    price_per_kwh_eur: float | None = None
    geofence_id: uuid.UUID | None = None
    notes: str | None = None


class ChargingPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    plan_type: PlanType | None = None
    periodicity: Periodicity | None = None
    subscription_start_date: date | None = None
    monthly_fee_eur: float | None = None
    kwh_allotment: float | None = None
    overage_price_per_kwh_eur: float | None = None
    price_per_kwh_eur: float | None = None
    geofence_id: uuid.UUID | None = None
    notes: str | None = None


class ChargingPlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    plan_type: str
    periodicity: str | None = None
    subscription_start_date: date | None = None
    monthly_fee_eur: float | None = None
    kwh_allotment: float | None = None
    overage_price_per_kwh_eur: float | None = None
    price_per_kwh_eur: float | None = None
    geofence_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer(
        "monthly_fee_eur",
        "kwh_allotment",
        "overage_price_per_kwh_eur",
        "price_per_kwh_eur",
    )
    def serialize_amounts(self, value):
        return float(value) if value is not None else None


class SuggestCostResponse(BaseModel):
    plan_id: uuid.UUID | None = None
    plan_name: str | None = None
    plan_type: str | None = None
    suggested_provider_name: str | None = None
    suggested_cost_eur: float | None = None
    reason: str
    remaining_kwh: float | None = None
    allotment_kwh: float | None = None
    matched_by: str | None = None
