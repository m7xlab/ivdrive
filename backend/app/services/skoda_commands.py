"""Command router — MyŠkoda Login wins when present, else official Public API."""

from __future__ import annotations

from typing import Any

from app.services.skoda_bff_api import SkodaBFFClient
from app.services.skoda_public_api import SkodaPublicAPIClient

# ops that only Login BFF can do
LOGIN_ONLY_OPS = frozenset({"wake", "lock", "unlock"})
# ops both stacks support (with method names on each client)
SHARED_OPS = frozenset(
    {
        "charge_start",
        "charge_stop",
        "charge_limit",
        "charge_mode",
        "climate_start",
        "climate_stop",
    }
)

_ALL_OPS = LOGIN_ONLY_OPS | SHARED_OPS

_MESSAGES = {
    "wake": "Wake-up request sent.",
    "lock": "Lock request sent.",
    "unlock": "Unlock request sent.",
    "charge_start": "Charging start request sent.",
    "charge_stop": "Charging stop request sent.",
    "charge_limit": "Charge limit updated.",
    "charge_mode": "Charge mode updated.",
    "climate_start": "Climate start request sent.",
    "climate_stop": "Climate stop request sent.",
}


class CommandUnsupported(Exception):
    """Operation not available on the connected sources."""


class CommandError(Exception):
    """Upstream rejected or failed the command."""


def command_supported(op: str, *, has_login: bool, has_public: bool) -> bool:
    if op not in _ALL_OPS:
        return False
    if op in LOGIN_ONLY_OPS:
        return has_login
    return has_login or has_public


async def run_command(
    op: str,
    *,
    vin: str,
    login_client: SkodaBFFClient | None = None,
    public_client: SkodaPublicAPIClient | None = None,
    **params: Any,
) -> str:
    """Execute *op*. Login BFF is preferred whenever it is connected."""
    if op not in _ALL_OPS:
        raise CommandUnsupported(f"Unknown command: {op}")
    if not command_supported(
        op, has_login=login_client is not None, has_public=public_client is not None
    ):
        if op in LOGIN_ONLY_OPS:
            raise CommandUnsupported("Connect MyŠkoda Login to lock / unlock / wake the car.")
        raise CommandUnsupported("Connect MyŠkoda Public API or MyŠkoda Login first.")

    try:
        if login_client is not None:
            await _run_bff(login_client, op, vin, **params)
        else:
            await _run_public(public_client, op, vin, **params)
    except CommandUnsupported:
        raise
    except Exception as exc:
        # Shared ops: if the Login path fails, try the official Public API
        # (climate start is better specified there).
        if public_client is not None and op in SHARED_OPS and login_client is not None:
            try:
                await _run_public(public_client, op, vin, **params)
                return _MESSAGES[op]
            except Exception as fallback_exc:
                raise CommandError(
                    f"{exc} | public fallback: {fallback_exc}"
                ) from exc
        raise CommandError(str(exc)) from exc
    return _MESSAGES[op]


async def _run_bff(client: SkodaBFFClient, op: str, vin: str, **params: Any) -> None:
    if op == "wake":
        await client.wake(vin)
    elif op == "lock":
        await client.lock(vin)
    elif op == "unlock":
        await client.unlock(vin, spin=params.get("spin"))
    elif op == "charge_start":
        await client.start_charging(vin)
    elif op == "charge_stop":
        await client.stop_charging(vin)
    elif op == "charge_limit":
        await client.set_charge_limit(vin, int(params["percent"]))
    elif op == "charge_mode":
        await client.set_charge_mode(vin, str(params["mode"]))
    elif op == "climate_start":
        await client.start_climate(vin, float(params["temp_c"]))
    elif op == "climate_stop":
        await client.stop_climate(vin)
    else:
        raise CommandUnsupported(f"Unknown command: {op}")


async def _run_public(client: SkodaPublicAPIClient, op: str, vin: str, **params: Any) -> None:
    if client is None:
        raise CommandUnsupported("Connect MyŠkoda Public API or MyŠkoda Login first.")
    if op == "charge_start":
        await client.start_charging(vin)
    elif op == "charge_stop":
        await client.stop_charging(vin)
    elif op == "charge_limit":
        await client.set_charge_limit(vin, int(params["percent"]))
    elif op == "charge_mode":
        await client.set_charge_mode(vin, str(params["mode"]))
    elif op == "climate_start":
        await client.start_air_conditioning(vin, float(params["temp_c"]))
    elif op == "climate_stop":
        await client.stop_air_conditioning(vin)
    else:
        raise CommandUnsupported("Connect MyŠkoda Login for this action.")
