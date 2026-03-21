import asyncio
import httpx
import logging
from datetime import datetime
from nordpool import elspot

logger = logging.getLogger(__name__)

async def fetch_weather_and_elevation(lat: float, lon: float):
    """Fetch Open-Meteo weather and OpenTopoData elevation asynchronously."""
    weather = {"temp_c": None, "condition": None}
    elevation = None

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Weather
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true"
        }
        
        # Elevation
        elevation_url = "https://api.opentopodata.org/v1/eudem25m"
        elevation_params = {"locations": f"{lat},{lon}"}

        try:
            w_res, e_res = await asyncio.gather(
                client.get(weather_url, params=weather_params),
                client.get(elevation_url, params=elevation_params),
                return_exceptions=True
            )

            if isinstance(w_res, httpx.Response) and w_res.status_code == 200:
                cw = w_res.json().get("current_weather", {})
                weather["temp_c"] = cw.get("temperature")
                weather["condition"] = str(cw.get("weathercode")) if "weathercode" in cw else None
            
            if isinstance(e_res, httpx.Response) and e_res.status_code == 200:
                results = e_res.json().get("results", [])
                if results:
                    elevation = results[0].get("elevation")

        except Exception as e:
            logger.error("Failed to fetch external APIs: %s", e)

    return weather["temp_c"], weather["condition"], elevation

async def reverse_geocode_country(lat: float, lon: float) -> str | None:
    """Fetch the ISO 3166-1 alpha-2 country code using Nominatim."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "format": "jsonv2",
                    "lat": lat,
                    "lon": lon
                },
                headers={"User-Agent": "iVDrive-Backend-Collector (info@ivdrive.eu)"}
            )
            if response.status_code == 200:
                data = response.json()
                country_code = data.get("address", {}).get("country_code", "").upper()
                return country_code if len(country_code) == 2 else None
    except Exception as e:
        logger.warning("Failed to reverse geocode country: %s", e)
    return None

def _sync_fetch_nordpool(area: str = "LT") -> float:
    """Synchronous call to kipe/nordpool to get the current hourly price."""
    try:
        prices_spot = elspot.Prices()
        hourly_data = prices_spot.hourly(areas=[area])
        # Find the price for the current hour
        current_hour = datetime.now()
        for entry in hourly_data.get('areas', {}).get(area, {}).get('values', []):
            start = entry.get('start')
            end = entry.get('end')
            if start and end and start <= current_hour < end:
                # Value is usually in EUR/MWh, convert to EUR/kWh
                return entry.get('value', 0) / 1000.0
    except Exception as e:
        logger.warning("NordPool fetch error: %s", e)
    return 0.15  # Fallback EUR/kWh

async def fetch_nordpool_price(area: str = "LT") -> float:
    """Fetch current hourly NordPool price asynchronously."""
    return await asyncio.to_thread(_sync_fetch_nordpool, area)

