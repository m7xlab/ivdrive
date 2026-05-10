"""Efficiency calibration defaults — analytics uses these when vehicle columns are null."""

from typing import TypedDict

from app.models.vehicle import UserVehicle


class VehicleCalibrationDefaults(TypedDict):
    charger_power_kw: float
    ice_l_per_100km: float
    uphill_kwh_per_100km_per_100m: float
    downhill_kwh_per_100km_per_100m: float
    speed_city_threshold_kmh: float
    speed_highway_threshold_kmh: float
    temp_cold_max_celsius: float
    temp_optimal_min_celsius: float
    temp_optimal_max_celsius: float


VEHICLE_CALIBRATION_DEFAULTS: VehicleCalibrationDefaults = {
    "charger_power_kw": 22.0,
    "ice_l_per_100km": 8.0,
    "uphill_kwh_per_100km_per_100m": 0.20,
    "downhill_kwh_per_100km_per_100m": 0.15,
    "speed_city_threshold_kmh": 50.0,
    "speed_highway_threshold_kmh": 90.0,
    "temp_cold_max_celsius": 5.0,
    "temp_optimal_min_celsius": 15.0,
    "temp_optimal_max_celsius": 25.0,
}


def effective_vehicle_calibration(vehicle: UserVehicle) -> VehicleCalibrationDefaults:
    """Per-vehicle efficiency thresholds with app defaults where columns are null."""
    d = VEHICLE_CALIBRATION_DEFAULTS
    return {
        "charger_power_kw": vehicle.charger_power_kw or d["charger_power_kw"],
        "ice_l_per_100km": vehicle.ice_l_per_100km or d["ice_l_per_100km"],
        "uphill_kwh_per_100km_per_100m": vehicle.uphill_kwh_per_100km_per_100m or d["uphill_kwh_per_100km_per_100m"],
        "downhill_kwh_per_100km_per_100m": vehicle.downhill_kwh_per_100km_per_100m or d["downhill_kwh_per_100km_per_100m"],
        "speed_city_threshold_kmh": vehicle.speed_city_threshold_kmh or d["speed_city_threshold_kmh"],
        "speed_highway_threshold_kmh": vehicle.speed_highway_threshold_kmh or d["speed_highway_threshold_kmh"],
        "temp_cold_max_celsius": vehicle.temp_cold_max_celsius or d["temp_cold_max_celsius"],
        "temp_optimal_min_celsius": vehicle.temp_optimal_min_celsius or d["temp_optimal_min_celsius"],
        "temp_optimal_max_celsius": vehicle.temp_optimal_max_celsius or d["temp_optimal_max_celsius"],
    }
