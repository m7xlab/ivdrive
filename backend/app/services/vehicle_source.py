"""Vehicle telemetry source port — legacy (myskoda) and official public API."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal, Protocol

from app.services.crypto import decrypt_field
from app.services.skoda_normalize import (
    NormalizedSnapshot,
    SourceKind,
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

TelemetrySourcePref = Literal["auto", "legacy", "public"]


class VehicleSource(Protocol):
    kind: SourceKind

    async def fetch_snapshot(self, vin: str) -> NormalizedSnapshot: ...

    async def close(self) -> None: ...


class PublicVehicleSource:
    """Official MyŠkoda Public API — one GET per snapshot (rate-limited)."""

    kind: SourceKind = "public"

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


def public_source_from_encrypted(api_key_encrypted: str | None) -> PublicVehicleSource | None:
    if not api_key_encrypted:
        return None
    try:
        return PublicVehicleSource(decrypt_field(api_key_encrypted))
    except Exception:
        logger.warning("Failed to decrypt Škoda public API key", exc_info=True)
        return None


async def fetch_snapshot_auto(
    *,
    vin: str,
    preference: TelemetrySourcePref,
    api_key_encrypted: str | None,
    legacy_fetch,
) -> tuple[NormalizedSnapshot | None, SourceKind | None, str | None]:
    """Fetch one snapshot using policy: public preferred when key exists (auto).

    `legacy_fetch` is an async callable (vin) -> NormalizedSnapshot | None
    supplied by the collector (keeps this module free of myskoda imports).
    Returns (snapshot, source_kind, error).
    """
    error: str | None = None
    use_public = preference == "public" or (preference == "auto" and bool(api_key_encrypted))
    use_legacy = preference == "legacy" or (preference == "auto" and not api_key_encrypted)

    if preference == "auto" and api_key_encrypted:
        use_public, use_legacy = True, True  # legacy only as fallback

    if use_public and api_key_encrypted:
        src = public_source_from_encrypted(api_key_encrypted)
        if src is not None:
            try:
                snap = await src.fetch_snapshot(vin)
                await src.close()
                return snap, "public", None
            except SkodaPublicRateLimitError as exc:
                error = f"public rate-limit: {exc}"
                if preference == "public":
                    return None, "public", error
            except SkodaPublicAuthError as exc:
                error = f"public auth: {exc}"
                if preference == "public":
                    return None, "public", error
            except SkodaPublicAPIError as exc:
                error = f"public error: {exc}"
                if preference == "public":
                    return None, "public", error
            except Exception as exc:
                error = f"public unexpected: {exc}"
                if preference == "public":
                    return None, "public", error
            finally:
                await src.close()

    if use_legacy or (preference == "auto" and error):
        try:
            snap = await legacy_fetch(vin)
            if snap is not None:
                return snap, "legacy", error
        except Exception as exc:
            error = f"{error or ''} legacy: {exc}".strip()

    return None, None, error or "no source available"
