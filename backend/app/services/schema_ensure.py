"""Startup repair for schema changes that would otherwise need a manual `alembic upgrade head`.

The documented upgrade flow asks operators to run migrations by hand. Anyone who forgets would get an
error on every query that touches `trips` the moment the ORM expects a new column. So the API and the
collector make sure the v1.3.12 trip edit/delete schema exists when they start. It is idempotent (the
same SQL as migration c5d7e9f1a3b4, which then has nothing left to do), serialized across the two
processes, and skipped entirely when the schema is already there.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_LOCK_KEY = 73120001
_STATEMENTS = (
    "ALTER TABLE trips ADD COLUMN IF NOT EXISTS data_quality VARCHAR(30)",
    "ALTER TABLE trips ADD COLUMN IF NOT EXISTS manually_edited BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE trips ADD COLUMN IF NOT EXISTS edit_history JSONB",
    """CREATE TABLE IF NOT EXISTS deleted_trips (
        id BIGSERIAL PRIMARY KEY,
        user_vehicle_id UUID NOT NULL REFERENCES user_vehicles(id) ON DELETE CASCADE,
        start_date TIMESTAMPTZ NOT NULL,
        end_date TIMESTAMPTZ,
        start_odometer DOUBLE PRECISION,
        end_odometer DOUBLE PRECISION,
        deleted_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_deleted_trips_user_vehicle_id ON deleted_trips (user_vehicle_id)",
)

_PRESENT = text("""
    SELECT
      (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'trips'
          AND column_name IN ('data_quality', 'manually_edited', 'edit_history')) AS cols,
      (SELECT count(*) FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'deleted_trips') AS tbl
""")


async def ensure_trip_edit_schema(engine: AsyncEngine, attempts: int = 3) -> bool:
    """True when the schema is in place afterwards. Never raises: the app should still start."""
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                row = (await conn.execute(_PRESENT)).one()
                if row.cols == 3 and row.tbl == 1:
                    return True
                await conn.execute(text("SET LOCAL lock_timeout = '10s'"))
                await conn.execute(text(f"SELECT pg_advisory_xact_lock({_LOCK_KEY})"))
                for stmt in _STATEMENTS:          # every statement is IF NOT EXISTS: safe to repeat
                    await conn.execute(text(stmt))
            logger.warning("Trip edit/delete schema was missing and has been created (run `alembic upgrade head` to record it).")
            return True
        except Exception:  # noqa: BLE001
            logger.warning("ensure_trip_edit_schema attempt %d/%d failed", attempt, attempts, exc_info=attempt == attempts)
            if attempt < attempts:
                await asyncio.sleep(3)
    return False
