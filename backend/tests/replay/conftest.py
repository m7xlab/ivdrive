"""Scratch-DB fixtures for telemetry replay tests.

Creates a throw-away database next to the configured one, builds the schema
from the ORM models and points `analytics.async_session` at it. Skips when no
Postgres is reachable. Never touches the configured database's data.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

SCRATCH_DB = "ivdrive_replay_test"


def _admin_dsn() -> tuple[dict, str]:
    url = make_url(settings.database_url)
    return (
        dict(user=url.username, password=url.password, host=url.host, port=url.port or 5432),
        url.set(database=SCRATCH_DB).render_as_string(hide_password=False),
    )


@pytest_asyncio.fixture
async def replay_sessionmaker():
    creds, scratch_url = _admin_dsn()
    try:
        admin = await asyncpg.connect(database="postgres", **creds)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Postgres not reachable for replay tests: {exc}")
    await admin.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')
    await admin.execute(f'CREATE DATABASE "{SCRATCH_DB}"')
    await admin.close()

    engine = create_async_engine(scratch_url)
    import app.models  # noqa: F401
    import app.models.ai_premium, app.models.charging_plan, app.models.fuel_price  # noqa: F401,E401
    import app.models.user, app.models.vehicle, app.models.telemetry  # noqa: F401,E401
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
    admin = await asyncpg.connect(database="postgres", **creds)
    await admin.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')
    await admin.close()


@pytest_asyncio.fixture
async def vehicle_id(replay_sessionmaker, monkeypatch):
    from app.models.user import User
    from app.models.vehicle import UserVehicle
    from app.services import analytics

    monkeypatch.setattr(analytics, "async_session", replay_sessionmaker)

    async def _no_price():  # avoid network in _close_session
        return 0.2

    monkeypatch.setattr(analytics, "fetch_nordpool_price", _no_price)

    async with replay_sessionmaker() as s:
        user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@t.local", password_hash="x")
        s.add(user)
        await s.flush()
        veh = UserVehicle(
            id=uuid.uuid4(), user_id=user.id, vin_hash=uuid.uuid4().hex, vin_encrypted="x",
            battery_capacity_kwh=77.0,
        )
        s.add(veh)
        await s.commit()
        return veh.id


@pytest.fixture(autouse=True)
def fail_on_swallowed_analytics_errors(caplog):
    """process_completed_trips_and_charges swallows exceptions; replay must not."""
    yield
    bad = [r.getMessage() for r in caplog.get_records("call")
           if r.name == "app.services.analytics" and r.levelname == "ERROR"]
    assert not bad, f"analytics swallowed {len(bad)} error(s): {bad[0][:300]}"
