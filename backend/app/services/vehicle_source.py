"""Vehicle telemetry source port — MyŠkoda Login and official Public API."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal, Protocol

from app.services.crypto import decrypt_field
from app.services.skoda_bff_api import SkodaBFFClient, SkodaBFFError
from app.services.skoda_normalize import (
    NormalizedSnapshot,
    snapshot_from_bff,
    snapshot_from_public,
)
from app.services.skoda_public_api import (
    SkodaPublicAPIError,
    SkodaPublicAuthError,
    SkodaPublicAPIClient,
    SkodaPublicRateLimitError,
    parse_expires_at,
)

logger = logging.getLogger(__name__)

TelemetrySourcePref = Literal["auto", "public", "login"]


class VehicleSource(Protocol):
    kind: str

    async def fetch_snapshot(self, vin: str) -> NormalizedSnapshot: ...

    async def close(self) -> None: ...


class PublicVehicleSource:
    """Official MyŠkoda Public API — one GET per snapshot (rate-limited)."""

    kind = "public"

    def __init__(self, api_key: str) -> None:
        self._client = SkodaPublicAPIClient(api_key)

    async def fetch_snapshot(self, vin: str) -> NormalizedSnapshot:
        resp, meta = await self._client.get_vehicle_snapshot(vin)
        now = datetime.now(UTC)
        return snapshot_from_public(resp, now=now, vin=vin)

    @property
    def rate_limit_remaining(self) -> int | None:
        return self._client.last_meta.rate_limit_remaining

    @property
    def key_expires_at(self):
        return parse_expires_at(self._client.last_meta)

    async def close(self) -> None:
        await self._client.close()


class LoginVehicleSource:
    """MyŠkoda Login. Optional advanced source — wins when connected."""

    kind = "login"

    def __init__(self, access_token: str) -> None:
        self._client = SkodaBFFClient(access_token)

    async def fetch_snapshot(self, vin: str) -> NormalizedSnapshot:
        charging = await self._client.get_charging(vin)
        vehicle_status = await self._client.get_vehicle_status(vin)
        parking = await self._client.get_parking(vin)
        driving_range = None
        readiness = None
        try:
            driving_range = await self._client.get_driving_range(vin)
        except SkodaBFFError:
            logger.debug("BFF driving-range unavailable for %s", vin)
        try:
            readiness = await self._client.get_readiness(vin)
        except SkodaBFFError:
            logger.debug("BFF readiness unavailable for %s", vin)
        return snapshot_from_bff(
            charging=charging,
            vehicle_status=vehicle_status,
            parking=parking,
            driving_range=driving_range,
            readiness=readiness,
            now=datetime.now(UTC),
            vin=vin,
        )

    async def close(self) -> None:
        await self._client.close()


def public_source_from_encrypted(api_key_encrypted: str | None) -> PublicVehicleSource | None:
    if not api_key_encrypted:
        return None
    try:
        return PublicVehicleSource(decrypt_field(api_key_encrypted))
    except Exception:
        logger.warning("Failed to decrypt Škoda public API key", exc_info=True)
        return None


def login_source_from_encrypted(access_encrypted: str | None) -> LoginVehicleSource | None:
    if not access_encrypted:
        return None
    try:
        return LoginVehicleSource(decrypt_field(access_encrypted))
    except Exception:
        logger.warning("Failed to decrypt MyŠkoda login token", exc_info=True)
        return None


async def fetch_snapshot_auto(
    *,
    vin: str,
    preference: TelemetrySourcePref,
    api_key_encrypted: str | None = None,
    login_access_encrypted: str | None = None,
) -> tuple[NormalizedSnapshot | None, str | None, str | None]:
    """Fetch one snapshot.

    Policy: Login wins when connected (auto or login). Public is the official
    default and fallback in auto. Returns (snapshot, source_kind, error).
    """
    error: str | None = None
    want_login = preference == "login" or (preference == "auto" and bool(login_access_encrypted))
    want_public = preference == "public" or (
        preference == "auto" and bool(api_key_encrypted) and not want_login
    )
    # auto with both: login first, public only as fallback
    public_fallback = preference == "auto" and bool(api_key_encrypted)

    if want_login and login_access_encrypted:
        src = login_source_from_encrypted(login_access_encrypted)
        if src is not None:
            try:
                snap = await src.fetch_snapshot(vin)
                return snap, "login", None
            except Exception as exc:
                error = f"login: {exc}"
                if preference == "login":
                    return None, "login", error
            finally:
                await src.close()

    if (want_public or public_fallback) and api_key_encrypted:
        src = public_source_from_encrypted(api_key_encrypted)
        if src is not None:
            try:
                snap = await src.fetch_snapshot(vin)
                return snap, "public", error
            except SkodaPublicRateLimitError as exc:
                error = f"public rate-limit: {exc}"
            except SkodaPublicAuthError as exc:
                error = f"public auth: {exc}"
            except SkodaPublicAPIError as exc:
                error = f"public error: {exc}"
            except Exception as exc:
                error = f"public unexpected: {exc}"
            finally:
                await src.close()
            if preference == "public":
                return None, "public", error

    return None, None, error or "no source available"
