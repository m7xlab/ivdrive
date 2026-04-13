import json
import uuid
import zipfile
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.telemetry import (
    Drive, ChargingSession, Trip, VehiclePosition, 
    AirConditioningState, MaintenanceReport, OdometerReading,
    ConnectionState, BatteryHealth, PowerUsage, ChargingCurve,
    ChargingPower, ClimatizationState, OutsideTemperature,
    BatteryTemperature
)
from app.models.vehicle import UserVehicle
from app.models.user import User

class ExportService:
    """Service to handle user data extraction for data sovereignty."""
    
    EXPORT_DIR = Path("/app/shared_data/exports")

    def __init__(self, db: AsyncSession):
        self.db = db
        # Ensure export directory exists
        self.EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    async def generate_user_export(self, user_id: uuid.UUID) -> str:
        """
        Generates a 1-year data export for all vehicles owned by a user.
        Returns the path to the generated ZIP file.
        """
        # 1. Fetch all user vehicles
        result = await self.db.execute(
            select(UserVehicle).where(UserVehicle.user_id == user_id)
        )
        vehicles = result.scalars().all()
        
        if not vehicles:
            return None

        export_id = str(uuid.uuid4())
        export_filename = f"ivdrive_export_{user_id}_{datetime.now().strftime('%Y%m%d')}.json"
        zip_filename = f"ivdrive_export_{user_id}_{export_id}.zip"
        zip_path = self.EXPORT_DIR / zip_filename
        
        # Calculate time threshold (1 year ago)
        since = datetime.now(timezone.utc) - timedelta(days=365)
        
        export_data = {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user_id": str(user_id),
            "vehicles": []
        }

        for vehicle in vehicles:
            v_data = {
                "id": str(vehicle.id),
                "vin_hash": vehicle.vin_hash,
                "display_name": vehicle.display_name,
                "model": vehicle.model,
                "telemetry": {}
            }
            
            # Helper to query and serialize tables scoped to user_vehicle_id
            v_data["telemetry"]["drives"] = await self._get_table_data(
                Drive, vehicle.id, since, "id" # Internal ID for root drive
            )
            v_data["telemetry"]["charging_sessions"] = await self._get_table_data(
                ChargingSession, vehicle.id, since, "session_start"
            )
            v_data["telemetry"]["trips"] = await self._get_table_data(Trip, vehicle.id, since, "start_date")
            v_data["telemetry"]["positions"] = await self._get_table_data(VehiclePosition, vehicle.id, since, "captured_at")
            v_data["telemetry"]["ac_states"] = await self._get_table_data(AirConditioningState, vehicle.id, since, "captured_at")
            v_data["telemetry"]["maintenance"] = await self._get_table_data(MaintenanceReport, vehicle.id, since, "captured_at")
            v_data["telemetry"]["odometer"] = await self._get_table_data(OdometerReading, vehicle.id, since, "captured_at")
            v_data["telemetry"]["connection"] = await self._get_table_data(ConnectionState, vehicle.id, since, "captured_at")
            v_data["telemetry"]["battery_health"] = await self._get_table_data(BatteryHealth, vehicle.id, since, "captured_at")
            v_data["telemetry"]["power_usage"] = await self._get_table_data(PowerUsage, vehicle.id, since, "captured_at")
            v_data["telemetry"]["charging_curve"] = await self._get_table_data(ChargingCurve, vehicle.id, since, "captured_at")
            v_data["telemetry"]["charging_power"] = await self._get_table_data(ChargingPower, vehicle.id, since, "first_date")
            v_data["telemetry"]["climatization_state"] = await self._get_table_data(ClimatizationState, vehicle.id, since, "first_date")
            v_data["telemetry"]["outside_temperature"] = await self._get_table_data(OutsideTemperature, vehicle.id, since, "first_date")
            v_data["telemetry"]["battery_temperature"] = await self._get_table_data(BatteryTemperature, vehicle.id, since, "first_date")
            
            export_data["vehicles"].append(v_data)

        # Write to JSON and then ZIP
        json_content = json.dumps(export_data, default=str, indent=2)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr(export_filename, json_content)
            
        return str(zip_path)

    async def _get_table_data(self, model, vehicle_id: uuid.UUID, since: datetime, date_col: str) -> List[Dict[str, Any]]:
        """Generic query for telemetry tables."""
        # Find the actual column object for filtering
        attr = getattr(model, date_col)
        
        query = select(model).where(
            and_(
                model.user_vehicle_id == vehicle_id,
                attr >= since
            )
        )
        
        result = await self.db.execute(query)
        rows = result.scalars().all()
        
        # Convert SQLAlchemy objects to dicts, excluding internal IDs if necessary
        data = []
        for row in rows:
            d = {c.name: getattr(row, c.name) for c in row.__table__.columns}
            # Remove internal DB keys for cleaner export
            d.pop('id', None)
            d['user_vehicle_id'] = str(d['user_vehicle_id'])
            data.append(d)
        return data
