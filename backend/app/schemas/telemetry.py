from datetime import datetime

from pydantic import BaseModel, Field


class TimeRangeParams(BaseModel):
    from_date: datetime | None = None
    to_date: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class BatteryHistoryItem(BaseModel):
    timestamp: datetime
    level: float


class RangeHistoryItem(BaseModel):
    timestamp: datetime
    range_km: float


class ChargingSessionItem(BaseModel):
    id: int
    session_start: datetime | None = None
    session_end: datetime | None = None
    start_level: float | None = None
    end_level: float | None = None
    charging_type: str | None = None
    energy_kwh: float | None = None
    actual_cost_eur: float | None = None
    base_cost_eur: float | None = None
    latitude: float | None = None
    longitude: float | None = None

    model_config = {"from_attributes": True}


class ChargingStateItem(BaseModel):
    first_date: datetime
    last_date: datetime
    state: str | None = None
    charge_power_kw: float | None = None
    charge_rate_km_per_hour: float | None = None
    remaining_time_min: int | None = None
    target_soc_pct: int | None = None
    battery_pct: int | None = None
    remaining_range_m: int | None = None
    charge_type: str | None = None

    model_config = {"from_attributes": True}


class TripItem(BaseModel):
    id: int
    start_date: datetime
    end_date: datetime | None = None
    start_lat: float | None = None
    start_lon: float | None = None
    end_lat: float | None = None
    end_lon: float | None = None
    start_odometer: float | None = None
    end_odometer: float | None = None

    model_config = {"from_attributes": True}


class TripAnalyticsItem(BaseModel):
    trip_id: int
    start_time: datetime
    end_time: datetime | None = None
    start_latitude: float | None = None
    start_longitude: float | None = None
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    distance_km: float | None = None
    duration_minutes: float | None = None
    average_speed_kmh: float | None = None
    kwh_used: float | None = None
    efficiency_kwh_100km: float | None = None

    model_config = {"from_attributes": True}


class PositionItem(BaseModel):
    captured_at: datetime
    latitude: float
    longitude: float


class VisitedLocationItem(BaseModel):
    latitude: float
    longitude: float
    timestamp: datetime
    source: str  # "position" or "charging"
    model_config = {"from_attributes": True}


class VehicleStateItem(BaseModel):
    first_date: datetime
    last_date: datetime
    state: str | None = None
    doors_locked: str | None = None
    doors_open: str | None = None
    windows_open: str | None = None
    lights_on: str | None = None
    trunk_open: bool | None = None
    bonnet_open: bool | None = None

    model_config = {"from_attributes": True}


class AirConditioningItem(BaseModel):
    captured_at: datetime
    state: str | None = None
    target_temp_celsius: float | None = None
    outside_temp_celsius: float | None = None
    seat_heating_front_left: bool | None = None
    seat_heating_front_right: bool | None = None
    window_heating_enabled: bool | None = None

    model_config = {"from_attributes": True}


class MaintenanceItem(BaseModel):
    captured_at: datetime
    mileage_in_km: int | None = None
    inspection_due_in_days: int | None = None
    inspection_due_in_km: int | None = None
    oil_service_due_in_days: int | None = None
    oil_service_due_in_km: int | None = None

    model_config = {"from_attributes": True}


class OdometerItem(BaseModel):
    captured_at: datetime
    mileage_in_km: int

    model_config = {"from_attributes": True}


class ConnectionStateItem(BaseModel):
    captured_at: datetime
    is_online: bool | None = None
    in_motion: bool | None = None
    ignition_on: bool | None = None

    model_config = {"from_attributes": True}


class StatisticsPeriod(BaseModel):
    period: str
    drives_count: int = 0
    total_distance_km: float = 0
    time_driven_seconds: float = 0
    median_distance_km: float | None = None
    charging_sessions_count: int = 0
    total_energy_kwh: float = 0  # This will be renamed to "Energy Charged" in the frontend
    total_kwh_consumed: float = 0
    avg_energy_per_session_kwh: float = 0
    time_charging_seconds: float = 0


class StateBandItem(BaseModel):
    """Time band for Car Overview state timeline (e.g. Online, Climatization, Charging, Driving)."""
    from_date: datetime
    to_date: datetime
    state: str  # 'online' | 'climatization' | 'charging' | 'driving'


class RangeAt100Point(BaseModel):
    """Single point for Range at 100% SoC chart (Grafana-style)."""
    time: datetime
    range_estimated_full: float


class EfficiencyPoint(BaseModel):
    """Single point for Efficiency % chart (range_estimated_full / wltp_range * 100)."""
    time: datetime
    efficiency_pct: float


class WLTPResponse(BaseModel):
    """WLTP range in km for reference line (from drives or vehicle specs)."""
    wltp_range_km: float | None = None

class PulseResponse(BaseModel):
    status: str
    battery_pct: int
    remaining_range_km: int
    temperature_celsius: float | None
    weather_code: str | None
    is_online: bool
    charging_power_kw: float
    remaining_charge_time_min: int
