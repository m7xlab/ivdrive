import asyncio
import os
import sys

# Ensure the app can be imported
sys.path.append(os.getcwd())

from app.database import engine
from app.models.base import Base
from app.services.ai_seed import ensure_ai_defaults
import app.models.user
import app.models.vehicle
import app.models.telemetry
import app.models.invite

async def init_db():
    async with engine.begin() as conn:
        print("Creating all tables from models...")
        await conn.run_sync(Base.metadata.create_all)
        if await ensure_ai_defaults(conn):
            print("AI tier defaults ensured.")
        print("Database initialized successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
