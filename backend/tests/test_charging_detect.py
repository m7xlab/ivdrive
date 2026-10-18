from app.services.analytics import is_actively_charging, is_plugged_in


def test_plugged_in_includes_connect_cable():
    assert is_plugged_in("CONNECT_CABLE") is True
    assert is_plugged_in("charging") is True
    assert is_plugged_in("READY_FOR_CHARGING") is True
    assert is_plugged_in("CHARGING_INTERRUPTED") is True
    assert is_plugged_in("CONSERVING") is True


def test_plugged_in_rejects_parked_and_empty():
    assert is_plugged_in(None) is False
    assert is_plugged_in("") is False
    assert is_plugged_in("DISCONNECTED") is False
    assert is_plugged_in("OFF") is False


def test_actively_charging_state_charging():
    assert is_actively_charging("CHARGING") is True
    assert is_actively_charging("charging") is True
    assert is_actively_charging("CHARGING", 0.0) is True


def test_actively_charging_requires_power_when_cable_only():
    # Overnight home cable at 0 kW must NOT keep Active polling
    assert is_actively_charging("CONNECT_CABLE") is False
    assert is_actively_charging("CONNECT_CABLE", 0.0) is False
    assert is_actively_charging("READY_FOR_CHARGING", 0.0) is False
    assert is_actively_charging("CONSERVING", None) is False


def test_actively_charging_with_power_on_plugged_states():
    assert is_actively_charging("CONNECT_CABLE", 7.2) is True
    assert is_actively_charging("READY_FOR_CHARGING", 11.0) is True
    assert is_actively_charging("CHARGING_INTERRUPTED", 3.3) is True


def test_actively_charging_rejects_unplugged():
    assert is_actively_charging(None) is False
    assert is_actively_charging("") is False
    assert is_actively_charging("DISCONNECTED", 50.0) is False
    assert is_actively_charging("OFF", 50.0) is False
