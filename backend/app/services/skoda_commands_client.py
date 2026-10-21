from __future__ import annotations

import logging

from app.services.skoda_bff_api import SkodaBFFClient
from app.services.skoda_commands import CommandError, CommandUnsupported, run_command
from app.services.skoda_public_api import SkodaPublicAPIClient

logger = logging.getLogger(__name__)

# API command method name → router op
_OP_MAP = {
    "start_climatization": "climate_start",
    "stop_climatization": "climate_stop",
    "start_charging": "charge_start",
    "stop_charging": "charge_stop",
    "lock": "lock",
    "unlock": "unlock",
    "wake": "wake",
    "honk_flash": "lock",  # no honk on BFF yet; refuse below
}


class SkodaCommandClient:
    """Remote commands via MyŠkoda Login (BFF) when connected, else Public API.

    Replaces the unofficial myskoda library command path.
    """

    def __init__(
        self,
        *,
        access_token: str | None = None,
        public_api_key: str | None = None,
        email: str | None = None,
        password: str | None = None,
        spin: str | None = None,
    ) -> None:
        self.access_token = access_token
        self.public_api_key = public_api_key
        self.email = email
        self.password = password
        self.spin = spin

    async def _run(self, vin: str, op: str, **params):
        login_client = SkodaBFFClient(self.access_token) if self.access_token else None
        public_client = SkodaPublicAPIClient(self.public_api_key) if self.public_api_key else None
        try:
            return await run_command(
                op, vin=vin, login_client=login_client, public_client=public_client, **params
            )
        finally:
            if login_client:
                await login_client.close()
            if public_client:
                await public_client.close()

    async def start_climatization(self, vin: str, target_temp: float):
        await self._run(vin, "climate_start", temp_c=target_temp)

    async def stop_climatization(self, vin: str):
        await self._run(vin, "climate_stop")

    async def start_charging(self, vin: str):
        await self._run(vin, "charge_start")

    async def stop_charging(self, vin: str):
        await self._run(vin, "charge_stop")

    async def lock(self, vin: str):
        await self._run(vin, "lock")

    async def unlock(self, vin: str, spin: str | None = None):
        await self._run(vin, "unlock")

    async def honk_flash(self, vin: str):
        raise CommandUnsupported("Honk and flash is not available on this connection.")

    async def wake(self, vin: str):
        await self._run(vin, "wake")
