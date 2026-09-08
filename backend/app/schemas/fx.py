from datetime import date

from pydantic import BaseModel, field_serializer


class CurrencyResponse(BaseModel):
    code: str
    name: str
    symbol: str
    rate_per_eur: float
    as_of: date
    source: str

    model_config = {"from_attributes": True}

    @field_serializer("rate_per_eur")
    def serialize_rate(self, value):
        return float(value)
