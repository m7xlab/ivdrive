import asyncio
import logging
import httpx
import re
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.database import async_session
from app.models.fuel_price import FuelPrice, PriceBreakdown, CountryEconomics, Vignette

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NAMESPACE_FUEL = uuid.uuid5(uuid.NAMESPACE_OID, "ivdrive.fuel_prices")

def safe_float(val):
    if not val or val == '-': return None
    try:
        return float(str(val).replace(',', ''))
    except ValueError:
        return None

async def fetch_and_store_fuel_prices():
    url = 'https://www.fuel-prices.eu/llms-full.txt'
    logger.info(f"Fetching full data from {url}...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            content = response.text
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        return

    # Extract date
    date_match = re.search(r'data_date:\s*(\d{4}-\d{2}-\d{2})', content)
    if not date_match:
        logger.error("Could not find 'data_date'.")
        return
    data_date_str = date_match.group(1)
    try:
        data_date = datetime.strptime(data_date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.error(f"Invalid date format: {data_date_str}")
        return

    # Find the detailed country profiles section
    detailed_profiles_match = re.search(r'## DETAILED COUNTRY PROFILES(.*?)(?=\n## |\Z)', content, re.DOTALL)
    if not detailed_profiles_match:
        logger.error("Could not find DETAILED COUNTRY PROFILES.")
        return
    
    profiles_text = detailed_profiles_match.group(1)
    country_blocks = re.split(r'### ', profiles_text)[1:] # Skip the first empty split
    
    fuel_records = []
    breakdown_records = []
    eco_records = []
    vignette_records = []

    for block in country_blocks:
        header_match = re.match(r'(.*?)\s+\(([A-Z]{2})\)', block)
        if not header_match:
            continue
        
        country_name = header_match.group(1).strip()
        country_code = header_match.group(2)

        # Current Prices
        e95_match = re.search(r'Euro 95 Petrol:.*?€([0-9.]+)/L.*?\$([0-9.]+)/gal', block)
        diesel_match = re.search(r'Diesel:.*?€([0-9.]+)/L.*?\$([0-9.]+)/gal', block)
        change_match = re.search(r'Weekly change:.*?Petrol ([+-]?[0-9.]+)%.*?Diesel ([+-]?[0-9.]+)%', block)
        
        # Breakdown
        e95_bd_match = re.search(r'Euro 95: Product €([0-9.]+).*?Excise €([0-9.]+).*?Other €([0-9.]+).*?VAT €([0-9.]+).*?Tax share: ([0-9.]+)%', block)
        diesel_bd_match = re.search(r'Diesel: Product €([0-9.]+).*?Excise €([0-9.]+).*?Other €([0-9.]+).*?VAT €([0-9.]+).*?Tax share: ([0-9.]+)%', block)
        
        # Economics
        wage_match = re.search(r'Average net monthly wage: €([0-9,.]+)', block)
        elec_match = re.search(r'Electricity price: €([0-9.]+)/kWh', block)
        infl_match = re.search(r'Inflation rate: ([0-9.]+)%', block)
        


        eco_id = uuid.uuid5(NAMESPACE_FUEL, f"eco_{country_code}_{data_date}")
        if wage_match or elec_match or infl_match:
            wage = safe_float(wage_match.group(1)) if wage_match else None
            elec = safe_float(elec_match.group(1)) if elec_match else None
            infl = safe_float(infl_match.group(1)) if infl_match else None
            eco_records.append({
                "id": eco_id,
                "country_code": country_code,
                "date": data_date,
                "avg_net_monthly_wage_eur": wage,
                "electricity_price_kwh_eur": elec,
                "inflation_rate_pct": infl
            })

        # Process E95
        if e95_match:
            f_id = uuid.uuid5(NAMESPACE_FUEL, f"fuel_{country_code}_{data_date}_E95")
            fuel_records.append({
                "id": f_id,
                "country_code": country_code,
                "week_date": data_date,
                "fuel_type": "Euro95",
                "price_eur_liter": safe_float(e95_match.group(1)),
                "price_usd_gallon": safe_float(e95_match.group(2)),
                "weekly_change_pct": safe_float(change_match.group(1)) if change_match else None
            })
            if e95_bd_match:
                breakdown_records.append({
                    "id": uuid.uuid5(NAMESPACE_FUEL, f"bd_{f_id}"),
                    "fuel_price_id": f_id,
                    "product_cost_eur": safe_float(e95_bd_match.group(1)),
                    "excise_duty_eur": safe_float(e95_bd_match.group(2)),
                    "other_taxes_eur": safe_float(e95_bd_match.group(3)),
                    "vat_eur": safe_float(e95_bd_match.group(4)),
                    "tax_share_pct": safe_float(e95_bd_match.group(5))
                })

        # Process Diesel
        if diesel_match:
            f_id = uuid.uuid5(NAMESPACE_FUEL, f"fuel_{country_code}_{data_date}_Diesel")
            fuel_records.append({
                "id": f_id,
                "country_code": country_code,
                "week_date": data_date,
                "fuel_type": "Diesel",
                "price_eur_liter": safe_float(diesel_match.group(1)),
                "price_usd_gallon": safe_float(diesel_match.group(2)),
                "weekly_change_pct": safe_float(change_match.group(2)) if change_match else None
            })
            if diesel_bd_match:
                breakdown_records.append({
                    "id": uuid.uuid5(NAMESPACE_FUEL, f"bd_{f_id}"),
                    "fuel_price_id": f_id,
                    "product_cost_eur": safe_float(diesel_bd_match.group(1)),
                    "excise_duty_eur": safe_float(diesel_bd_match.group(2)),
                    "other_taxes_eur": safe_float(diesel_bd_match.group(3)),
                    "vat_eur": safe_float(diesel_bd_match.group(4)),
                    "tax_share_pct": safe_float(diesel_bd_match.group(5))
                })

        # Vignettes
        vignette_section = re.search(r'Vignettes:(.*?)(?:Major toll points:|Economics:|$)', block, re.DOTALL)
        if vignette_section:
            vlines = vignette_section.group(1).strip().split('\n')
            for vl in vlines:
                vm = re.search(r'-\s+(.*?):\s+€([0-9.]+)\s+—\s+(.*)', vl)
                if vm:
                    vignette_records.append({
                        "id": uuid.uuid4(),
                        "country_code": country_code,
                        "name": vm.group(1).strip(),
                        "price_eur": float(vm.group(2)),
                        "validity_duration": vm.group(3).strip()[:50]
                    })

    if not fuel_records:
        logger.warning("No valid records parsed.")
        return

    logger.info(f"Parsed {len(fuel_records)} fuel records, {len(breakdown_records)} breakdowns, {len(eco_records)} economics, {len(vignette_records)} vignettes. Upserting...")

    async with async_session() as db:
        # 1. Economics
        if eco_records:
            eco_stmt = insert(CountryEconomics).values(eco_records)
            eco_stmt = eco_stmt.on_conflict_do_update(
                index_elements=['country_code', 'date'],
                set_={
                    'avg_net_monthly_wage_eur': eco_stmt.excluded.avg_net_monthly_wage_eur,
                    'electricity_price_kwh_eur': eco_stmt.excluded.electricity_price_kwh_eur,
                    'inflation_rate_pct': eco_stmt.excluded.inflation_rate_pct
                }
            )
            await db.execute(eco_stmt)

        # 2. Fuel Prices
        if fuel_records:
            fuel_stmt = insert(FuelPrice).values(fuel_records)
            fuel_stmt = fuel_stmt.on_conflict_do_update(
                index_elements=['country_code', 'week_date', 'fuel_type'],
                set_={
                    'price_eur_liter': fuel_stmt.excluded.price_eur_liter,
                    'price_usd_gallon': fuel_stmt.excluded.price_usd_gallon,
                    'weekly_change_pct': fuel_stmt.excluded.weekly_change_pct
                }
            )
            await db.execute(fuel_stmt)
            
            # 3. Breakdowns
            if breakdown_records:
                bd_stmt = insert(PriceBreakdown).values(breakdown_records)
                bd_stmt = bd_stmt.on_conflict_do_update(
                    index_elements=['fuel_price_id'],
                    set_={
                        'product_cost_eur': bd_stmt.excluded.product_cost_eur,
                        'excise_duty_eur': bd_stmt.excluded.excise_duty_eur,
                        'other_taxes_eur': bd_stmt.excluded.other_taxes_eur,
                        'vat_eur': bd_stmt.excluded.vat_eur,
                        'tax_share_pct': bd_stmt.excluded.tax_share_pct
                    }
                )
                await db.execute(bd_stmt)

        # 4. Vignettes (static, so UPSERT by country and name)
        if vignette_records:
            vig_stmt = insert(Vignette).values(vignette_records)
            vig_stmt = vig_stmt.on_conflict_do_update(
                index_elements=['country_code', 'name'],
                set_={
                    'price_eur': vig_stmt.excluded.price_eur,
                    'validity_duration': vig_stmt.excluded.validity_duration
                }
            )
            await db.execute(vig_stmt)

        await db.commit()
        logger.info("Database updated successfully.")

if __name__ == "__main__":
    asyncio.run(fetch_and_store_fuel_prices())
