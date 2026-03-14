
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
import httpx
import asyncio
from pydantic import BaseModel
from decimal import Decimal

router = APIRouter()

class GeoRequest(BaseModel):
    latitude: float
    longitude: float

class GeoResponse(BaseModel):
    display_name: str

@router.post("/reverse", response_model=GeoResponse)
async def reverse_geocode(
    req: GeoRequest,
    db: AsyncSession = Depends(get_db)
):
    # Round to 5 decimal places for consistent caching (approx 1 meter precision)
    lat = Decimal(str(req.latitude)).quantize(Decimal("1.000000"))
    lon = Decimal(str(req.longitude)).quantize(Decimal("1.000000"))

    # 1. Check Cache
    stmt = text("SELECT display_name FROM geocoded_locations WHERE latitude = :lat AND longitude = :lon")
    result = await db.execute(stmt, {"lat": lat, "lon": lon})
    row = result.fetchone()
    
    if row:
        return {"display_name": row[0]}

    # 2. Not in cache, call Nominatim
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "format": "jsonv2",
                    "lat": float(lat),
                    "lon": float(lon)
                },
                headers={"User-Agent": "iVDrive-Backend-Cache (info@ivdrive.eu)"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                address = data.get("address", {})
                
                # Try to build a better name: Road + House Number, or Suburb, or City
                road = address.get("road")
                house_number = address.get("house_number")
                suburb = address.get("suburb")
                city = address.get("city") or address.get("town") or address.get("village")
                
                if road:
                    parts = [road]
                    if house_number:
                        parts.append(house_number)
                    short_name = " ".join(parts)
                elif suburb:
                    short_name = suburb
                else:
                    short_name = city or "Unknown Location"
                
                # 3. Save to cache
                save_stmt = text("INSERT INTO geocoded_locations (latitude, longitude, display_name) VALUES (:lat, :lon, :name) ON CONFLICT DO NOTHING")
                await db.execute(save_stmt, {"lat": lat, "lon": lon, "name": short_name})
                await db.commit()
                
                return {"display_name": short_name}
            
            elif response.status_code == 429:
                # Backend rate limiting: if we hit 429, we don't want to spam
                raise HTTPException(status_code=429, detail="Geocoding service busy, try again later")
                
        except Exception as e:
            return {"display_name": "Location"}

    return {"display_name": "Location"}
