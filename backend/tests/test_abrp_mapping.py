"""Unit tests for ABRP telemetry field mapping (pure functions, no network/DB)."""

from datetime import UTC, datetime

from app.models.vehicle import ABRPConnection, UserVehicle
from app.services.abrp_sync import AbrpSnapshot, build_tlm, tlm_has_signal


def _vehicle(**kwargs) -> UserVehicle:
    defaults = {"battery_capacity_kwh": 77.0, "incognito_mode": False}
    defaults.update(kwargs)
    return UserVehicle(**defaults)


def _snap(**kwargs) -> AbrpSnapshot:
    defaults = {"now": datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC)}
    defaults.update(kwargs)
    return AbrpSnapshot(**defaults)


def test_utc_is_epoch_seconds_not_millis():
    tlm = build_tlm(snapshot=_snap(soc=50.0), vehicle=_vehicle(), abrp_conn=None, incognito=False)
    assert isinstance(tlm["utc"], int)
    assert tlm["utc"] == int(datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC).timestamp())
    assert tlm["utc"] < 10**11  # seconds, not ms


def test_charging_power_is_negated():
    tlm = build_tlm(
        snapshot=_snap(soc=80.0, is_charging=True, charge_power_kw=50.0),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    assert tlm["power"] == -50.0
    assert tlm["is_charging"] == 1


def test_missing_power_is_omitted_not_zero():
    tlm = build_tlm(
        snapshot=_snap(soc=80.0, is_charging=False),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    assert "power" not in tlm


def test_est_battery_range_from_meters():
    tlm = build_tlm(
        snapshot=_snap(soc=50.0, remaining_range_m=50000),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    assert tlm["est_battery_range"] == 50.0


def test_est_battery_range_fallback_to_km():
    tlm = build_tlm(
        snapshot=_snap(soc=50.0, range_km=123.0),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    assert tlm["est_battery_range"] == 123.0


def test_is_parked_flag():
    tlm = build_tlm(
        snapshot=_snap(soc=50.0, is_parked=True, is_charging=False),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    assert tlm["is_parked"] == 1
    assert tlm["is_charging"] == 0


def test_is_dcfc_from_charge_type():
    tlm = build_tlm(
        snapshot=_snap(soc=40.0, is_charging=True, charge_power_kw=100.0, charge_type="DC"),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    assert tlm["is_dcfc"] == 1


def test_is_dcfc_from_high_power_heuristic():
    tlm = build_tlm(
        snapshot=_snap(soc=40.0, is_charging=True, charge_power_kw=50.0, charge_type="AC"),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    assert tlm["is_dcfc"] == 1


def test_is_dcfc_false_for_slow_ac():
    tlm = build_tlm(
        snapshot=_snap(soc=40.0, is_charging=True, charge_power_kw=11.0, charge_type="AC"),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    assert tlm["is_dcfc"] == 0


def test_incognito_drops_position_keeps_soc():
    tlm = build_tlm(
        snapshot=_snap(soc=55.0, lat=54.7, lon=25.3, elevation_m=100.0),
        vehicle=_vehicle(incognito_mode=True),
        abrp_conn=None,
        incognito=True,
    )
    assert "lat" not in tlm
    assert "lon" not in tlm
    assert "elevation" not in tlm
    assert tlm["soc"] == 55.0


def test_soe_computed_from_capacity_and_soc():
    tlm = build_tlm(
        snapshot=_snap(soc=50.0, capacity_kwh=77.0),
        vehicle=_vehicle(battery_capacity_kwh=77.0),
        abrp_conn=None,
        incognito=False,
    )
    assert tlm["capacity"] == 77.0
    assert abs(tlm["soe"] - 38.5) < 1e-6


def test_missing_fields_are_omitted():
    tlm = build_tlm(
        snapshot=_snap(soc=10.0),
        vehicle=_vehicle(),
        abrp_conn=None,
        incognito=False,
    )
    for key in ("power", "speed", "lat", "lon", "odometer", "est_battery_range", "soh", "car_model"):
        assert key not in tlm, key
    assert tlm["soc"] == 10.0


def test_car_model_typecode_included_when_set():
    conn = ABRPConnection(car_model_typecode="skoda:enyaq:21:58:other")
    tlm = build_tlm(
        snapshot=_snap(soc=10.0),
        vehicle=_vehicle(),
        abrp_conn=conn,
        incognito=False,
    )
    assert tlm["car_model"] == "skoda:enyaq:21:58:other"


def test_tlm_has_signal():
    assert tlm_has_signal({"utc": 1, "soc": 50.0})
    assert tlm_has_signal({"utc": 1, "is_parked": 1})
    assert not tlm_has_signal({"utc": 1})
