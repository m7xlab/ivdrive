"""Tests for BFF payload → NormalizedSnapshot mapping."""

from datetime import UTC, datetime

from app.services.skoda_normalize import snapshot_from_bff


def test_snapshot_from_bff_maps_core_fields():
    charging = {
        "status": {
            "state": "CHARGING",
            "chargePowerInKw": 50.0,
            "chargeType": "DC",
            "battery": {
                "stateOfChargeInPercent": 41,
                "remainingCruisingRangeInMeters": 116000,
            },
        },
        "settings": {"targetStateOfChargeInPercent": 80},
        "carCapturedTimestamp": "2026-10-20T17:37:41Z",
    }
    vehicle_status = {
        "overall": {
            "doorsLocked": "YES",
            "locked": "YES",
            "doors": "CLOSED",
            "windows": "CLOSED",
            "lights": "OFF",
        },
        "detail": {"trunk": "CLOSED", "bonnet": "CLOSED"},
        "carCapturedTimestamp": "2026-10-20T17:37:47.348Z",
    }
    parking = {
        "parkingPosition": {
            "gpsCoordinates": {"latitude": 54.6, "longitude": 25.2},
            "formattedAddress": "Vilnius",
        }
    }
    driving_range = {
        "primaryEngineRange": {"currentSoCInPercent": 41, "remainingRangeInKm": 116},
        "totalRangeInKm": 116,
        "carCapturedTimestamp": "2026-10-20T17:37:47.351Z",
    }
    readiness = {"unreachable": False, "inMotion": False, "ignitionOn": False}
    snap = snapshot_from_bff(
        charging=charging,
        vehicle_status=vehicle_status,
        parking=parking,
        driving_range=driving_range,
        readiness=readiness,
        now=datetime.now(UTC),
        vin="TESTVIN0000000001",
    )
    assert snap.source == "login"
    assert snap.soc == 41.0
    assert snap.charge_power_kw == 50.0
    assert snap.charge_state == "CHARGING"
    assert snap.remaining_range_m == 116000
    assert snap.target_soc == 80.0
    assert snap.lat == 54.6 and snap.lon == 25.2
    assert snap.is_online is True
    assert snap.is_moving is False
    assert snap.extra["doors_locked"] == "YES"


def test_snapshot_from_bff_driving_range_fallback_soc():
    charging = {"status": {"state": "CONNECT_CABLE", "battery": {}}}
    snap = snapshot_from_bff(
        charging=charging,
        vehicle_status={},
        parking={},
        driving_range={"primaryEngineRange": {"currentSoCInPercent": 55, "remainingRangeInKm": 200}},
        readiness=None,
        now=datetime.now(UTC),
        vin="TESTVIN0000000001",
    )
    assert snap.soc == 55.0
    assert snap.range_km == 200.0
    assert snap.is_online is True


def test_snapshot_from_bff_does_not_invent_zero_longitude():
    snap = snapshot_from_bff(
        charging={"status": {"battery": {"stateOfChargeInPercent": 50}}},
        vehicle_status={},
        parking={"parkingPosition": {"gpsCoordinates": {"latitude": 54.6}}},
        driving_range=None,
        readiness=None,
        now=datetime.now(UTC),
        vin="TESTVIN0000000001",
    )
    # Incomplete GPS (missing lon) must not become (54.6, 0.0)
    assert snap.lat is None
    assert snap.lon is None
