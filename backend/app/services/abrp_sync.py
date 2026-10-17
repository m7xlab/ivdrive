"""ABRP telemetry mapping + outbox/flusher orchestration.

Collector cycles enqueue a snapshot per vehicle into a Valkey outbox list.
A periodic flusher pops pending samples and pushes them to ABRP via
``/tlm/send`` (single sample) or ``/tlm/bulk`` (two or more vehicles of the
same user).

Both credentials are per ABRP user:
- ``users.abrp_api_key_encrypted`` — free Telemetry API key from their ABRP account
- ``abrp_connections.token_encrypted`` — per-vehicle Custom connection token

ABRP units are metric. ``power`` sign convention: discharge positive,
charge NEGATIVE. ``utc`` is epoch seconds (not ms).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.vehicle import ABRPConnection, UserVehicle
from app.services.crypto import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)

OUTBOX_KEY = "ivdrive:abrp_outbox"
OUTBOX_MAX_LEN = 500

# ABRP fields we can populate from iVDrive / Škoda telemetry. Fields not listed
# (speed, heading, cabin_temp, tire pressures, voltage, current, soh) are omitted
# because no upstream source exists today.


@dataclass
class AbrpSnapshot:
    """Normalized values captured in one collector cycle (or from DB fallback)."""

    now: datetime
    soc: float | None = None
    charge_power_kw: float | None = None  # positive while charging
    is_charging: bool | None = None
    is_parked: bool | None = None
    charge_type: str | None = None
    lat: float | None = None
    lon: float | None = None
    elevation_m: float | None = None
    odometer_km: float | None = None
    remaining_range_m: float | None = None
    range_km: float | None = None
    ext_temp_c: float | None = None
    batt_temp_c: float | None = None
    hvac_setpoint_c: float | None = None
    capacity_kwh: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _is_fresh(ts: datetime | None, now: datetime, max_age_s: float) -> bool:
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (now - ts).total_seconds() <= max_age_s


def build_tlm(
    *,
    snapshot: AbrpSnapshot,
    vehicle: UserVehicle,
    abrp_conn: ABRPConnection | None,
    incognito: bool,
) -> dict[str, Any]:
    """Map an iVDrive snapshot to an ABRP ``tlm`` dict. Unknown fields are omitted."""
    now = snapshot.now
    tlm: dict[str, Any] = {"utc": int(now.timestamp())}

    # ── SOC ────────────────────────────────────────────────────────────────
    soc = snapshot.soc
    if soc is not None:
        tlm["soc"] = float(soc)

    # ── power (discharge +, charge −) ──────────────────────────────────────
    if snapshot.is_charging and snapshot.charge_power_kw is not None:
        tlm["power"] = -float(snapshot.charge_power_kw)
    elif snapshot.extras.get("discharge_power_kw") is not None:
        tlm["power"] = float(snapshot.extras["discharge_power_kw"])

    # ── flags ──────────────────────────────────────────────────────────────
    if snapshot.is_charging is not None:
        tlm["is_charging"] = 1 if snapshot.is_charging else 0
    if snapshot.is_parked is not None:
        tlm["is_parked"] = 1 if snapshot.is_parked else 0

    # is_dcfc: DC charge_type, or high charge power as a heuristic
    if snapshot.is_charging:
        charge_type = (snapshot.charge_type or "").upper()
        if "DC" in charge_type:
            tlm["is_dcfc"] = 1
        elif snapshot.charge_power_kw is not None and snapshot.charge_power_kw > 22:
            tlm["is_dcfc"] = 1
        else:
            tlm["is_dcfc"] = 0

    # ── position (suppressed in incognito) ─────────────────────────────────
    if not incognito:
        if snapshot.lat is not None and snapshot.lon is not None:
            tlm["lat"] = float(snapshot.lat)
            tlm["lon"] = float(snapshot.lon)
        if snapshot.elevation_m is not None:
            tlm["elevation"] = float(snapshot.elevation_m)

    # ── capacity / soe ─────────────────────────────────────────────────────
    capacity = snapshot.capacity_kwh if snapshot.capacity_kwh is not None else vehicle.battery_capacity_kwh
    if capacity is not None:
        tlm["capacity"] = float(capacity)
        if soc is not None:
            tlm["soe"] = float(capacity) * float(soc) / 100.0

    # ── range ──────────────────────────────────────────────────────────────
    if snapshot.remaining_range_m is not None:
        tlm["est_battery_range"] = float(snapshot.remaining_range_m) / 1000.0
    elif snapshot.range_km is not None:
        tlm["est_battery_range"] = float(snapshot.range_km)

    # ── odometer ───────────────────────────────────────────────────────────
    if snapshot.odometer_km is not None:
        tlm["odometer"] = float(snapshot.odometer_km)

    # ── temps / HVAC ───────────────────────────────────────────────────────
    if snapshot.ext_temp_c is not None:
        tlm["ext_temp"] = float(snapshot.ext_temp_c)
    if snapshot.batt_temp_c is not None:
        tlm["batt_temp"] = float(snapshot.batt_temp_c)
    if snapshot.hvac_setpoint_c is not None:
        tlm["hvac_setpoint"] = float(snapshot.hvac_setpoint_c)
    if snapshot.extras.get("hvac_power_kw") is not None:
        tlm["hvac_power"] = float(snapshot.extras["hvac_power_kw"])

    # ── car model typecode ─────────────────────────────────────────────────
    if abrp_conn and abrp_conn.car_model_typecode:
        tlm["car_model"] = abrp_conn.car_model_typecode

    # Optional extras pass-through (voltage/current/soh when available)
    for key in ("voltage", "current", "soh", "heading", "cabin_temp"):
        val = snapshot.extras.get(key)
        if val is not None:
            tlm[key] = val

    return tlm


def tlm_has_signal(tlm: dict[str, Any]) -> bool:
    """True if the datapoint is worth sending (has SOC or a definite state flag)."""
    return (
        tlm.get("soc") is not None
        or tlm.get("is_charging") is not None
        or tlm.get("is_parked") is not None
    )


# ── Outbox (Valkey) ─────────────────────────────────────────────────────────


async def _get_valkey():
    from app.services.events import get_valkey_client

    return await get_valkey_client()


async def enqueue_snapshot(
    *,
    user_id: UUID,
    user_vehicle_id: UUID,
    token_plain: str,
    tlm: dict[str, Any],
) -> None:
    """Queue one datapoint for the flusher. Never raises to the caller."""
    try:
        if not tlm_has_signal(tlm):
            return
        item = {
            "user_id": str(user_id),
            "vehicle_id": str(user_vehicle_id),
            "token": token_plain,
            "tlm": tlm,
            "queued_at": datetime.now(UTC).isoformat(),
        }
        client = await _get_valkey()
        try:
            await client.rpush(OUTBOX_KEY, json.dumps(item))
            await client.ltrim(OUTBOX_KEY, -OUTBOX_MAX_LEN, -1)
        finally:
            await client.aclose()
    except Exception:
        logger.warning("ABRP enqueue failed for vehicle %s", user_vehicle_id, exc_info=True)


async def _pop_outbox(limit: int = 200) -> list[dict[str, Any]]:
    client = await _get_valkey()
    try:
        items: list[dict[str, Any]] = []
        for _ in range(limit):
            raw = await client.lpop(OUTBOX_KEY)
            if raw is None:
                break
            try:
                items.append(json.loads(raw))
            except Exception:
                continue
        return items
    finally:
        await client.aclose()


def _backoff_seconds(failures: int) -> int:
    return min(2 ** max(failures, 1) * 60, 3600)


async def _load_user_api_key(session: AsyncSession, user_id: UUID) -> str | None:
    """Decrypt the per-user ABRP Telemetry API key, or None if unset."""
    row = await session.execute(
        select(User.abrp_api_key_encrypted).where(User.id == user_id)
    )
    enc = row.scalar_one_or_none()
    if not enc:
        return None
    try:
        return decrypt_field(enc)
    except Exception:
        logger.warning("ABRP api_key decrypt failed for user %s", user_id, exc_info=True)
        return None


async def _record_result(
    session: AsyncSession,
    vehicle_id: UUID,
    *,
    ok: bool,
    error: str | None = None,
) -> None:
    result = await session.execute(
        select(ABRPConnection).where(ABRPConnection.user_vehicle_id == vehicle_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        return
    now = datetime.now(UTC)
    if ok:
        conn.last_sent_at = now
        conn.consecutive_failures = 0
        conn.last_error_text = None
        conn.backoff_until = None
    else:
        conn.consecutive_failures = (conn.consecutive_failures or 0) + 1
        conn.last_error_text = (error or "unknown error")[:255]
        conn.backoff_until = now + timedelta(seconds=_backoff_seconds(conn.consecutive_failures))
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("ABRP bookkeeping commit failed for %s", vehicle_id, exc_info=True)


async def flush_outbox(session: AsyncSession) -> None:
    """Pop pending samples and push to ABRP.

    Single sample → ``/tlm/send``. Multiple samples from the same user →
    ``/tlm/bulk`` (grouped by vehicle token). Different users are flushed
    separately because each has their own API key.
    """
    items = await _pop_outbox()
    if not items:
        return

    now = datetime.now(UTC)
    live: list[dict[str, Any]] = []
    for item in items:
        vid_raw = item.get("vehicle_id")
        uid_raw = item.get("user_id")
        try:
            vid = UUID(str(vid_raw))
            uid = UUID(str(uid_raw))
        except Exception:
            continue
        result = await session.execute(
            select(ABRPConnection).where(ABRPConnection.user_vehicle_id == vid)
        )
        conn = result.scalar_one_or_none()
        if conn is None or not conn.enabled or not conn.token_encrypted:
            continue
        if conn.backoff_until and conn.backoff_until > now:
            continue
        api_key = await _load_user_api_key(session, uid)
        if not api_key:
            await _record_result(
                session, vid, ok=False,
                error="ABRP API key not configured in user settings",
            )
            continue
        item["_api_key"] = api_key
        live.append(item)

    if not live:
        return

    from app.services.abrp_api import ABRPAPIClient

    # Group by (user_id, api_key) — bulk only within one user's key
    by_user: dict[str, list[dict[str, Any]]] = {}
    for item in live:
        by_user.setdefault(item["user_id"], []).append(item)

    for _uid, user_items in by_user.items():
        api_key = user_items[0]["_api_key"]

        # Single sample for this user → primary /tlm/send path
        if len(user_items) == 1:
            item = user_items[0]
            client = ABRPAPIClient(item["token"], api_key)
            try:
                await client.send_tlm(item["tlm"])
                await _record_result(session, UUID(item["vehicle_id"]), ok=True)
                logger.info("ABRP send ok for vehicle %s", item["vehicle_id"])
            except Exception as exc:
                await _record_result(session, UUID(item["vehicle_id"]), ok=False, error=str(exc))
                logger.warning("ABRP send failed for vehicle %s: %s", item["vehicle_id"], exc)
            finally:
                await client.close()
            continue

        # Multiple samples → /tlm/bulk grouped by vehicle token
        by_token: dict[str, list[dict[str, Any]]] = {}
        for item in user_items:
            by_token.setdefault(item["token"], []).append(item)
        bulk_items = [
            {"token": token, "tlm_list": [it["tlm"] for it in group]}
            for token, group in by_token.items()
        ]
        client = ABRPAPIClient(next(iter(by_token)), api_key)
        try:
            await client.send_bulk(bulk_items)
            for item in user_items:
                await _record_result(session, UUID(item["vehicle_id"]), ok=True)
            logger.info(
                "ABRP bulk ok for %d sample(s) / %d token(s)",
                len(user_items), len(by_token),
            )
        except Exception as exc:
            for item in user_items:
                await _record_result(session, UUID(item["vehicle_id"]), ok=False, error=str(exc))
            logger.warning("ABRP bulk failed (%d sample(s)): %s", len(user_items), exc)
        finally:
            await client.close()


# ── Push helpers used by the collector ───────────────────────────────────────


async def push_vehicle_tlm(
    session: AsyncSession,
    vehicle: UserVehicle,
    snapshot: AbrpSnapshot,
) -> bool:
    """Build + enqueue one datapoint for a vehicle. Returns True if enqueued."""
    result = await session.execute(
        select(ABRPConnection).where(ABRPConnection.user_vehicle_id == vehicle.id)
    )
    conn = result.scalar_one_or_none()
    if conn is None or not conn.enabled or not conn.token_encrypted:
        return False

    now = snapshot.now
    if conn.backoff_until and conn.backoff_until > now:
        return False

    api_key = await _load_user_api_key(session, vehicle.user_id)
    if not api_key:
        return False

    try:
        token_plain = decrypt_field(conn.token_encrypted)
    except Exception:
        logger.warning("ABRP token decrypt failed for vehicle %s", vehicle.id, exc_info=True)
        return False

    tlm = build_tlm(
        snapshot=snapshot,
        vehicle=vehicle,
        abrp_conn=conn,
        incognito=bool(vehicle.incognito_mode),
    )
    if not tlm_has_signal(tlm):
        return False

    await enqueue_snapshot(
        user_id=vehicle.user_id,
        user_vehicle_id=vehicle.id,
        token_plain=token_plain,
        tlm=tlm,
    )
    return True


async def refresh_next_charge(session: AsyncSession, vehicle: UserVehicle) -> float | None:
    """Fetch ABRP next charge-to goal and cache it on the connection row."""
    result = await session.execute(
        select(ABRPConnection).where(ABRPConnection.user_vehicle_id == vehicle.id)
    )
    conn = result.scalar_one_or_none()
    if conn is None or not conn.token_encrypted:
        return None

    api_key = await _load_user_api_key(session, vehicle.user_id)
    if not api_key:
        return None

    from app.services.abrp_api import ABRPAPIClient

    token_plain = decrypt_field(conn.token_encrypted)
    client = ABRPAPIClient(token_plain, api_key)
    try:
        resp = await client.get_next_charge()
        pct = resp.result.next_charge if resp.result else None
        conn.next_charge_pct = pct
        conn.next_charge_fetched_at = datetime.now(UTC)
        conn.last_error_text = None
        await session.commit()
        return pct
    except Exception as exc:
        conn.last_error_text = str(exc)[:255]
        try:
            await session.commit()
        except Exception:
            await session.rollback()
        logger.warning("ABRP get_next_charge failed for vehicle %s: %s", vehicle.id, exc)
        return None
    finally:
        await client.close()


def upsert_token_fields(
    conn: ABRPConnection,
    *,
    token: str | None,
    enabled: bool | None,
    car_model_typecode: str | None,
) -> None:
    """Apply a settings update to an ABRPConnection row."""
    if token is not None:
        if token == "":
            conn.token_encrypted = None
            conn.enabled = False
        else:
            conn.token_encrypted = encrypt_field(token)
    if enabled is not None:
        conn.enabled = enabled
    if car_model_typecode is not None:
        conn.car_model_typecode = car_model_typecode or None


def upsert_user_api_key(user: User, api_key: str | None) -> None:
    """Set or clear the user's ABRP Telemetry API key (empty string clears)."""
    if api_key is None:
        return
    if api_key == "":
        user.abrp_api_key_encrypted = None
    else:
        user.abrp_api_key_encrypted = encrypt_field(api_key)
