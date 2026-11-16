"""v1.3.12: the API and collector create the trip edit/delete schema themselves at startup."""
import asyncio

import pytest
from sqlalchemy import select, text

from app.models.telemetry import Trip
from app.services.schema_ensure import ensure_trip_edit_schema

from .test_trip_sync import _tr


async def _strip_to_v1311(engine):
    """What an install that has not run the v1.3.12 migration looks like."""
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS deleted_trips"))
        await conn.execute(text("ALTER TABLE trips DROP COLUMN IF EXISTS manually_edited"))
        await conn.execute(text("ALTER TABLE trips DROP COLUMN IF EXISTS edit_history"))
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS show_commands"))
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS token_version"))
        await conn.execute(text("UPDATE battery_health_analytics SET soh_pct = 0 WHERE soh_pct IS NULL"))
        await conn.execute(text("ALTER TABLE battery_health_analytics ALTER COLUMN soh_pct SET NOT NULL"))


async def _has(engine) -> tuple[int, int]:
    async with engine.connect() as conn:
        cols = (await conn.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name='trips' AND column_name IN ('manually_edited','edit_history')"))).scalar()
        tbl = (await conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_name='deleted_trips'"))).scalar()
        ucol = (await conn.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name='users' AND column_name IN ('show_commands','token_version')"))).scalar()
        nullable = (await conn.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name='battery_health_analytics' AND column_name='soh_pct' AND is_nullable='YES'"))).scalar()
    return cols, tbl + ucol + nullable          # tbl (1) + users columns (2) + nullable (1)


@pytest.mark.asyncio
async def test_missing_schema_is_created_and_the_orm_works_afterwards(replay_sessionmaker, vehicle_id):
    engine = replay_sessionmaker.kw["bind"]
    await _strip_to_v1311(engine)
    assert await _has(engine) == (0, 0)
    assert await ensure_trip_edit_schema(engine, attempts=1) is True
    assert await _has(engine) == (2, 4)
    async with replay_sessionmaker() as s:                       # the ORM selects the new columns
        s.add(_tr(vehicle_id, "08:00", "08:30", 1, 11))
        await s.commit()
        t = (await s.execute(select(Trip))).scalars().one()
        assert t.manually_edited is False and t.edit_history is None


@pytest.mark.asyncio
async def test_existing_schema_is_left_alone_and_repeat_runs_are_harmless(replay_sessionmaker, vehicle_id):
    engine = replay_sessionmaker.kw["bind"]
    async with replay_sessionmaker() as s:
        s.add(_tr(vehicle_id, "08:00", "08:30", 1, 11))
        await s.commit()
    assert await ensure_trip_edit_schema(engine, attempts=1) is True
    assert await ensure_trip_edit_schema(engine, attempts=1) is True
    async with replay_sessionmaker() as s:
        assert len((await s.execute(select(Trip))).scalars().all()) == 1     # data untouched


@pytest.mark.asyncio
async def test_api_and_collector_starting_together_do_not_clash(replay_sessionmaker):
    engine = replay_sessionmaker.kw["bind"]
    await _strip_to_v1311(engine)
    results = await asyncio.gather(*[ensure_trip_edit_schema(engine, attempts=1) for _ in range(6)])
    assert all(results) and await _has(engine) == (2, 4)


@pytest.mark.asyncio
async def test_a_failing_database_never_raises(replay_sessionmaker):
    from sqlalchemy.ext.asyncio import create_async_engine
    broken = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")
    assert await ensure_trip_edit_schema(broken, attempts=1) is False
    await broken.dispose()


@pytest.mark.asyncio
async def test_statistics_view_survives_the_new_columns(replay_sessionmaker, vehicle_id):
    """v_trip_analytics selects t.*: adding columns to trips must not break it."""
    engine = replay_sessionmaker.kw["bind"]
    await _strip_to_v1311(engine)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE VIEW v_probe AS SELECT t.*, 1 AS x FROM trips t"))
    assert await ensure_trip_edit_schema(engine, attempts=1) is True
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM v_probe"))).scalar() == 0


@pytest.mark.asyncio
async def test_a_missing_token_version_column_is_created_at_startup(replay_sessionmaker):
    """v1.4.0 shipped the column in a migration and in the repair list, but the check that decides whether
    any repair is needed did not look for it, so an install that skipped the migration was never repaired
    and every query touching users failed ("column users.token_version does not exist")."""
    engine = replay_sessionmaker.kw["bind"]
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS token_version"))
    assert await ensure_trip_edit_schema(engine, attempts=1) is True
    async with engine.connect() as conn:
        col = (await conn.execute(text(
            "SELECT column_default, is_nullable FROM information_schema.columns "
            "WHERE table_name='users' AND column_name='token_version'"))).one()
    assert col.is_nullable == "NO" and "1" in col.column_default
    # and the ORM can read users again (every login and every poll does)
    from app.models.user import User
    async with replay_sessionmaker() as s:
        s.add(User(email="selfrepair@example.com", password_hash="x"))
        await s.commit()
        assert (await s.execute(select(User.token_version).where(User.email == "selfrepair@example.com"))).scalar() == 1


def test_every_column_the_repair_adds_is_also_in_the_presence_check():
    """A statement in _STATEMENTS that _PRESENT does not look for is never executed on an install that
    has everything else (the early return), which is how token_version was missed."""
    import re
    from app.services import schema_ensure as se
    present = str(se._PRESENT)
    added = re.findall(r"ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+)", "\n".join(se._STATEMENTS))
    missing = [f"{table}.{col}" for table, col in added if col not in present]
    assert not missing, f"added by the repair but not checked by _PRESENT: {missing}"
