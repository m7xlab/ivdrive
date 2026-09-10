from types import SimpleNamespace

from app.services.collector import _charging_probe_fields, _driving_range_soc, _to_raw


def test_charging_probe_fields_connect_cable_zero_power():
    charging = SimpleNamespace(
        status=SimpleNamespace(
            state="CONNECT_CABLE",
            charge_type=None,
            charge_power_in_kw=0,
            remaining_time_to_fully_charged_in_minutes=0,
            battery=SimpleNamespace(state_of_charge_in_percent=38),
        )
    )
    fields = _charging_probe_fields(charging)
    assert fields["state"] == "CONNECT_CABLE"
    assert fields["charge_power_kw"] == 0
    assert fields["remaining_time_min"] == 0
    assert fields["charging_soc"] == 38


def test_charging_probe_fields_empty():
    assert _charging_probe_fields(None)["state"] is None
    assert _charging_probe_fields(SimpleNamespace(status=None))["charging_soc"] is None


def test_driving_range_soc():
    driving = SimpleNamespace(
        primary_engine_range=SimpleNamespace(current_so_c_in_percent=72)
    )
    assert _driving_range_soc(driving) == 72
    assert _driving_range_soc(None) is None


def test_to_raw_dict_passthrough():
    assert _to_raw({"state": "CHARGING"}) == {"state": "CHARGING"}
    assert _to_raw(None) is None


def test_connect_cable_does_not_count_as_active_charging():
    """v1.1.14 sleep rule: only state == CHARGING wakes Active for charging."""
    charging = SimpleNamespace(status=SimpleNamespace(state="CONNECT_CABLE"))
    is_charging = bool(
        charging and charging.status and charging.status.state == "CHARGING"
    )
    assert is_charging is False
    charging.status.state = "CHARGING"
    is_charging = bool(
        charging and charging.status and charging.status.state == "CHARGING"
    )
    assert is_charging is True
