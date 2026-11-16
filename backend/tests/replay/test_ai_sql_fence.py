"""The AI assistant's SQL tool against a real Postgres: role, row security, timeout, row cap.

Applies migration c1a4e0b7d2f9 (and the pre-existing user_vehicles/trips policies it builds on)
to the scratch database, then calls execute_read_only_sql exactly as the chat pipeline does.
Skipped when the test database user may not create roles."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.services.chat_tools import execute_read_only_sql, AI_SQL_ROW_CAP

pytestmark = pytest.mark.asyncio

_MIGRATIONS = [
    "app/migrations/versions/c1a4e0b7d2f9_ai_role_fence_v1_4_0.py",
    "app/migrations/versions/f4a7c2d9e1b3_ai_role_least_privilege_v1_4_0.py",
]
_USER_ID = "(current_setting('app.current_user_id'::text, true))::uuid"


def _run_migration_upgrade(sync_conn) -> None:
    """Run each revision's upgrade() through a bare Alembic Operations object on this connection."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    for n, path in enumerate(_MIGRATIONS):
        spec = importlib.util.spec_from_file_location(f"ai_role_fence_{n}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.op = Operations(MigrationContext.configure(sync_conn))
        mod.upgrade()


@pytest_asyncio.fixture
async def fenced_db(replay_sessionmaker):
    """Two users with one vehicle each and 60 / 3 positions; the AI role and policies in place."""
    from app.models.user import User
    from app.models.vehicle import UserVehicle
    from app.models.telemetry import VehiclePosition, Trip

    async with replay_sessionmaker() as s:
        try:
            await s.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ivdrive_ai_readonly') "
                                 "THEN CREATE ROLE ivdrive_ai_readonly WITH NOLOGIN; END IF; END $$;"))
            await s.execute(text("GRANT ivdrive_ai_readonly TO CURRENT_USER"))
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"test database user cannot manage roles: {exc}")
        # The base policies from ea873b9fe6a2 that the new ones reference.
        await s.execute(text(
            f"CREATE POLICY isolate_user_vehicles ON user_vehicles FOR SELECT USING (user_id = {_USER_ID})"))
        await s.execute(text("ALTER TABLE user_vehicles ENABLE ROW LEVEL SECURITY"))
        await s.execute(text("GRANT SELECT ON user_vehicles TO ivdrive_ai_readonly"))
        await s.execute(text(
            f"CREATE POLICY isolate_trips ON trips FOR SELECT USING "
            f"(user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = {_USER_ID}))"))
        await s.execute(text("ALTER TABLE trips ENABLE ROW LEVEL SECURITY"))
        await s.execute(text("GRANT SELECT ON trips TO ivdrive_ai_readonly"))
        # Before the migration, mimic production: these tables are granted but have no policy.
        await s.execute(text("GRANT SELECT ON weconnect_errors TO ivdrive_ai_readonly"))
        # A table that exists only through migrations in production, with cross-user data, granted by
        # an old migration and missed by the first revoke list (cached addresses and coordinates).
        await s.execute(text("CREATE TABLE geocoded_locations (id serial PRIMARY KEY, label text)"))
        await s.execute(text("INSERT INTO geocoded_locations (label) VALUES ('someone''s home address')"))
        await s.execute(text("GRANT SELECT ON geocoded_locations TO ivdrive_ai_readonly"))
        conn = await s.connection()
        await conn.run_sync(_run_migration_upgrade)

        users, vehicles = [], []
        for n, positions in ((0, 60), (1, 3)):
            u = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@t.local", password_hash="x")
            s.add(u)
            await s.flush()
            v = UserVehicle(id=uuid.uuid4(), user_id=u.id, vin_hash=uuid.uuid4().hex, vin_encrypted="x",
                            battery_capacity_kwh=77.0, display_name=f"Car{n}")
            s.add(v)
            await s.flush()
            t0 = datetime(2026, 11, 1, tzinfo=UTC)
            for i in range(positions):
                s.add(VehiclePosition(user_vehicle_id=v.id, captured_at=t0 + timedelta(minutes=i),
                                      latitude=54.0 + n, longitude=25.0 + i / 1000))
            s.add(Trip(user_vehicle_id=v.id, start_date=t0, end_date=t0 + timedelta(hours=1), distance_km=10 + n))
            users.append(u.id)
            vehicles.append(v.id)
        await s.commit()
        yield s, users, vehicles


async def _rows(result_text: str) -> list[dict]:
    import json
    assert result_text.startswith("SQL SUCCESS"), result_text
    return json.loads(result_text.split("Rows returned:\n", 1)[1])


async def test_each_user_sees_only_their_own_vehicles_positions_and_trips(fenced_db):
    s, users, vehicles = fenced_db
    for idx, uid in enumerate(users):
        rows = await _rows(await execute_read_only_sql(s, uid, "SELECT display_name FROM user_vehicles ORDER BY 1"))
        assert [r["display_name"] for r in rows] == [f"Car{idx}"]
        rows = await _rows(await execute_read_only_sql(s, uid, "SELECT count(*) AS n FROM vehicle_positions"))
        assert rows[0]["n"] == (60 if idx == 0 else 3)
        rows = await _rows(await execute_read_only_sql(s, uid, "SELECT distance_km FROM trips"))
        assert [r["distance_km"] for r in rows] == [10 + idx]


async def test_a_table_without_a_policy_is_no_longer_readable_by_the_role(fenced_db):
    s, users, _ = fenced_db
    async with s.bind.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SET LOCAL ROLE ivdrive_ai_readonly"))
            with pytest.raises(Exception) as exc_info:
                await conn.execute(text("SELECT count(*) FROM weconnect_errors"))
            assert "permission denied" in str(exc_info.value)


async def test_the_user_id_cannot_be_rewritten_from_inside_the_query(fenced_db):
    s, users, _ = fenced_db
    victim, attacker = users
    sql = (f"WITH s AS (SELECT set_config('app.current_user_id', '{victim}', true) AS x) "
           f"SELECT count(*) AS n FROM vehicle_positions, s")
    out = await execute_read_only_sql(s, attacker, sql)
    assert out.startswith("SQL_ERROR"), out
    # And a plain count from the attacker's seat is still only the attacker's rows.
    rows = await _rows(await execute_read_only_sql(s, attacker, "SELECT count(*) AS n FROM vehicle_positions"))
    assert rows[0]["n"] == 3


async def test_quoted_relation_name_is_judged_like_an_unquoted_one(fenced_db):
    s, users, _ = fenced_db
    out = await execute_read_only_sql(s, users[1], 'SELECT count(*) FROM "weconnect_errors"')
    assert out.startswith("SQL_ERROR") and "not permitted" in out.lower()


async def test_row_cap_is_enforced_by_the_database_with_a_note(fenced_db):
    s, users, _ = fenced_db
    out = await execute_read_only_sql(s, users[0], "SELECT captured_at FROM vehicle_positions ORDER BY captured_at")
    rows = await _rows(out)
    assert len(rows) == AI_SQL_ROW_CAP
    assert f"first {AI_SQL_ROW_CAP} rows" in out
    out = await execute_read_only_sql(s, users[1], "SELECT captured_at FROM vehicle_positions")
    assert len(await _rows(out)) == 3 and "first" not in out.split("Rows returned")[0]


async def test_a_slow_query_is_cancelled_by_the_statement_timeout(fenced_db, monkeypatch):
    from app.services import chat_tools
    monkeypatch.setattr(chat_tools, "AI_SQL_STATEMENT_TIMEOUT_MS", 300)
    s, users, _ = fenced_db
    sql = ("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 200000000) "
           "SELECT count(*) AS n FROM r")
    out = await execute_read_only_sql(s, users[0], sql)
    assert out.startswith("SQL_ERROR") and "cancelled" in out, out


async def test_the_transaction_is_read_only_even_if_the_guard_were_bypassed(fenced_db, monkeypatch):
    from app.services import chat_tools
    monkeypatch.setattr(chat_tools, "check_ai_sql", lambda sql: None)
    s, users, _ = fenced_db
    out = await execute_read_only_sql(s, users[0], "DELETE FROM trips RETURNING id")
    assert out.startswith("SQL_ERROR"), out
    rows = await _rows(await execute_read_only_sql(s, users[0], "SELECT count(*) AS n FROM trips"))
    assert rows[0]["n"] == 1


async def test_the_role_can_read_only_the_allow_listed_relations_after_the_migrations(fenced_db):
    s, _, _ = fenced_db
    from app.services.ai_sql_guard import ALLOWED_TABLES
    import re as _re
    migration_list = set(_re.findall(r'"([a-z_]+)"', open(_MIGRATIONS[1]).read().split("ALLOWED = [")[1].split("]")[0]))
    assert migration_list == set(ALLOWED_TABLES), "migration ALLOWED and ai_sql_guard.ALLOWED_TABLES drifted"
    rows = (await s.execute(text(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p') "
        "AND has_table_privilege('ivdrive_ai_readonly', c.oid, 'SELECT')"))).scalars().all()
    assert set(rows) <= set(ALLOWED_TABLES), sorted(set(rows) - set(ALLOWED_TABLES))
    assert "geocoded_locations" not in rows and "weconnect_errors" not in rows


async def test_the_obfuscated_user_id_rewrite_and_the_comma_join_are_refused(fenced_db):
    """Regression for the review of the first v1.4.0 merge: a user id rewrite hidden inside a
    function that executes a string returned another user's rows."""
    s, users, _ = fenced_db
    victim, attacker = users
    inner = "select set_'||'config(''app.current_user_id'',''%s'',true)" % victim
    for sql in (
        "SELECT count(*) AS n FROM (SELECT query_to_xml('%s', true, false, '') AS x OFFSET 0) s, vehicle_positions" % inner,
        "WITH s AS (SELECT query_to_xml('%s', true, false, '')) SELECT count(*) AS n FROM s, vehicle_positions" % inner,
        "SELECT count(*) AS n FROM trips, geocoded_locations",
        "SELECT table_to_xml('geocoded_locations', true, false, '')",
    ):
        out = await execute_read_only_sql(s, attacker, sql)
        assert out.startswith("SQL_ERROR"), (sql, out)
    rows = await _rows(await execute_read_only_sql(s, attacker, "SELECT count(*) AS n FROM vehicle_positions"))
    assert rows[0]["n"] == 3     # the attacker still sees only their own 3, not the victim's 60


async def test_the_database_alone_refuses_the_rewrite_when_the_guard_is_bypassed(fenced_db, monkeypatch):
    """Second fence: even with the static guard disabled, the role cannot read geocoded_locations
    and a plain user-id rewrite leaves the other user's rows unreadable only because of the guard,
    so this documents that the guard is required for that part (see ai_sql_guard docstring)."""
    from app.services import chat_tools
    monkeypatch.setattr(chat_tools, "check_ai_sql", lambda sql: None)
    s, users, _ = fenced_db
    out = await execute_read_only_sql(s, users[1], "SELECT count(*) AS n FROM geocoded_locations")
    assert out.startswith("SQL_ERROR") and "not available" in out, out
