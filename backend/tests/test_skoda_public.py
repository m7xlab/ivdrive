"""Tests for official public API models + normalizer + source policy."""

from datetime import UTC, datetime

from app.schemas.skoda_public import VehicleResponse
from app.services.skoda_normalize import snapshot_from_public
from app.services.skoda_public_api import PublicResponseMeta, parse_expires_at


def _vehicle_payload() -> dict:
    return {
        "vehicle": {
            "vin": "TMBJJ7NE7N0123456",
            "name": "Test Enyaq",
            "charging": {
                "status": {
                    "state": "CHARGING",
                    "chargeType": "DC",
                    "chargePowerInKw": 50.5,
                    "plugConnectionState": "CONNECTED",
                    "battery": {
                        "stateOfChargeInPercent": 61,
                        "remainingCruisingRangeInMeters": 240000,
                    },
                },
                "settings": {"targetStateOfChargeInPercent": 80},
            },
            "odometer": {"mileageInKm": 12345},
            "parkingPosition": {
                "state": "PARKED",
                "gpsCoordinates": {"latitude": 54.7, "longitude": 25.3},
            },
            "airConditioning": {
                "state": "OFF",
                "targetTemperature": {"value": 21.0, "unit": "CELSIUS"},
            },
        },
        "errors": [],
    }


def test_parse_vehicle_response_camel_case():
    resp = VehicleResponse.model_validate(_vehicle_payload())
    assert resp.vehicle is not None
    assert resp.vehicle.charging.status.battery.state_of_charge_in_percent == 61
    assert resp.vehicle.parking_position.state == "PARKED"


def test_normalize_public_snapshot():
    resp = VehicleResponse.model_validate(_vehicle_payload())
    now = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    snap = snapshot_from_public(resp, now=now)
    assert snap.source == "public"
    assert snap.soc == 61.0
    assert snap.charge_power_kw == 50.5
    assert snap.charge_state == "CHARGING"
    assert snap.plug_connected is True
    assert snap.odometer_km == 12345.0
    assert snap.remaining_range_m == 240000.0
    assert snap.is_moving is False
    assert snap.is_parked is True
    assert snap.lat == 54.7
    assert snap.target_soc == 80.0


def test_normalize_public_in_motion_has_no_gps_required():
    payload = _vehicle_payload()
    payload["vehicle"]["parkingPosition"] = {"state": "IN_MOTION"}
    resp = VehicleResponse.model_validate(payload)
    snap = snapshot_from_public(resp, now=datetime.now(UTC))
    assert snap.is_moving is True
    assert snap.lat is None
    assert snap.soc == 61.0


def test_parse_key_expiry_header():
    meta = PublicResponseMeta(api_key_expires_at="2026-12-01T00:00:00Z")
    dt = parse_expires_at(meta)
    assert dt is not None
    assert dt.year == 2026


def test_friendly_errors_are_plain_language():
    from app.services.skoda_public_api import friendly_skoda_error

    expired = friendly_skoda_error(
        "err", 401, "https://public.api.connect.skoda-auto.cz/problems/api-key-expired"
    )
    assert "MyŠkoda" in expired or "MySkoda" in expired
    assert "3 month" in expired.lower()
    assert "msk_" not in expired

    rate = friendly_skoda_error("err", 429, "rate-limit-exceeded")
    assert "20" in rate and "hour" in rate.lower()

    not_auth = friendly_skoda_error("err", 403, "api-key-not-authorized")
    assert "vehicle" in not_auth.lower()

    generic = friendly_skoda_error("err", 500, None)
    assert "MyŠkoda" in generic or "MySkoda" in generic

