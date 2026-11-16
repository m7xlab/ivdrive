"""The static guard in front of the AI assistant's SQL tool (v1.4.0 security release).

The database role, row-security policies, statement timeout and LIMIT wrapper are the real
fence (tests/replay/test_ai_sql_fence.py). This guard turns the obvious escapes into a message
the model can act on before anything reaches the database."""

import pytest

from app.services.chat_tools import check_ai_sql, AI_SQL_ROW_CAP


@pytest.mark.parametrize("sql", [
    "SELECT * FROM trips LIMIT 10",
    "select count(*) from public.trips",
    "SELECT t.distance_km FROM trips t JOIN user_vehicles v ON v.id = t.user_vehicle_id WHERE v.display_name = 'BlackMagic'",
    "SELECT * FROM (SELECT * FROM trips) q",
    "WITH t AS (SELECT * FROM trips) SELECT * FROM t",
    "WITH a AS (SELECT 1 AS x), b AS (SELECT * FROM charging_sessions) SELECT * FROM a, b",
    "SELECT updated_at, created_at FROM charging_sessions",   # column names that contain keywords
    "SELECT * FROM v_trip_analytics ORDER BY start_date DESC LIMIT 5",
    "SELECT * FROM trips t JOIN (SELECT id FROM user_vehicles) v ON v.id = t.user_vehicle_id",
])
def test_ordinary_analytical_queries_pass(sql):
    assert check_ai_sql(sql) is None


@pytest.mark.parametrize("sql, fragment", [
    # quoted relation names used to slip past the unquoted-only allow-list
    ('SELECT * FROM "users"', "quote"),
    ('select * from public."ai_missed_intents"', "quote"),
    ('SELECT * FROM "trips"', "quote"),
    # out-of-scope relations, quoted or not
    ("SELECT * FROM users", "users"),
    ("SELECT * FROM (SELECT * FROM users) q", "users"),
    ("WITH t AS (SELECT * FROM trips) SELECT * FROM users", "users"),
    ("SELECT * FROM ai_missed_intents", "ai_missed_intents"),
    # rewriting the user id the row-security policies read
    ("WITH s AS (SELECT set_config('app.current_user_id', 'x', true)) SELECT * FROM trips, s", "construct"),
    ("SELECT current_setting('app.current_user_id')", "construct"),
    # catalogue, other sessions, denial of service
    ("SELECT * FROM pg_stat_activity", "construct"),
    ("SELECT * FROM information_schema.tables", "construct"),
    ("SELECT pg_sleep(600)", "construct"),
    ("SELECT * FROM generate_series(1, 100000000)", "construct"),
    # hiding tokens
    ("SELECT * FROM trips -- comment", "construct"),
    ("SELECT /* x */ * FROM trips", "construct"),
    ("SELECT $$x$$", "construct"),
    # not a read
    ("DELETE FROM trips", "SELECT/WITH"),
    ("SELECT * FROM trips; DROP TABLE trips", "single"),
    ("SELECT 1 UNION SELECT 1; SET ROLE ivdrive", "single"),
    ("SELECT * FROM trips WHERE 1=1 AND (SELECT 1 FROM trips FOR UPDATE) = 1", "read-only"),
])
def test_escapes_are_refused_with_an_actionable_message(sql, fragment):
    msg = check_ai_sql(sql)
    assert msg is not None and msg.startswith("SQL_ERROR"), sql
    assert fragment.lower() in msg.lower(), (sql, msg)


def test_row_cap_is_the_documented_fifty():
    assert AI_SQL_ROW_CAP == 50
