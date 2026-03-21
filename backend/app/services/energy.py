import asyncio
import logging
from datetime import datetime, UTC
import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import async_session
from app.models.telemetry import EnergyPrice

logger = logging.getLogger(__name__)

async def fetch_and_store_energy_prices():
    """Fetches weekly fuel/electricity prices from fuel-prices.eu and upserts them."""
    url = "https://www.fuel-prices.eu/api/natural-language/?q=Electricity%20(ev)%20vs%20Fuel%20price%20in%20Europe"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            countries = data.get("data", {}).get("countries", [])
            if not countries:
                logger.warning("No countries found in energy prices API response.")
                return
                
            upserts = []
            for c in countries:
                upserts.append({
                    "country_code": c.get("country_code", "UNKNOWN"),
                    "country_name": c.get("country_name", "UNKNOWN"),
                    "electricity_price_eur_kwh": float(c.get("electricity_price_eur_kwh", 0.0)),
                    "petrol_price_eur_l": float(c.get("petrol_price_eur_l", 0.0)),
                    "updated_at": datetime.now(UTC),
                })
                
            async with async_session() as session:
                stmt = insert(EnergyPrice).values(upserts)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['country_code'],
                    set_={
                        'electricity_price_eur_kwh': stmt.excluded.electricity_price_eur_kwh,
                        'petrol_price_eur_l': stmt.excluded.petrol_price_eur_l,
                        'updated_at': stmt.excluded.updated_at,
                    }
                )
                await session.execute(stmt)
                await session.commit()
                
            logger.info(f"Successfully updated energy prices for {len(upserts)} countries.")
            
    except Exception as e:
        logger.error(f"Failed to fetch and store energy prices: {e}", exc_info=True)
