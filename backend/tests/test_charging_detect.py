from app.services.analytics import is_plugged_in


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
