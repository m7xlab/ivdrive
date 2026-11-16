"""The parser-based guard in front of the AI assistant's SQL tool (v1.4.0).

Default-deny: one plain SELECT, allow-listed relations, allow-listed functions. The database role,
row-level security, READ ONLY transaction, timeout and LIMIT are tested in
tests/replay/test_ai_sql_fence.py; this file tests what reaches them."""

import pytest

from app.services.chat_tools import AI_SQL_ROW_CAP, check_ai_sql

VICTIM = "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize("sql", [
    "SELECT * FROM trips LIMIT 10",
    "select count(*) from public.trips",
    "SELECT t.distance_km FROM trips t JOIN user_vehicles v ON v.id = t.user_vehicle_id WHERE v.display_name = 'BlackMagic'",
    "SELECT * FROM (SELECT * FROM trips) q",
    "WITH t AS (SELECT * FROM trips) SELECT * FROM t",
    "WITH a AS (SELECT 1 AS x), b AS (SELECT * FROM charging_sessions) SELECT * FROM a, b",
    "WITH a(x) AS (SELECT 1) SELECT x FROM a",
    "SELECT updated_at, created_at FROM charging_sessions",
    "SELECT * FROM v_trip_analytics ORDER BY start_date DESC LIMIT 5",
    "SELECT * FROM trips t JOIN (SELECT id FROM user_vehicles) v ON v.id = t.user_vehicle_id",
    # things the old pattern guard refused although they are plain analytics
    "SELECT EXTRACT(HOUR FROM start_date) AS h, count(*) FROM trips GROUP BY 1",
    "SELECT date_trunc('day', start_date) AS d, sum(distance_km) AS \"Total km\" FROM trips GROUP BY 1",
    "SELECT * FROM trips WHERE start_soc IS DISTINCT FROM end_soc",
    "SELECT * FROM user_vehicles WHERE display_name ILIKE '%set%' OR display_name = 'a -- b'",
    "SELECT d::date, count(*) FROM generate_series(now() - interval '30 days', now(), interval '1 day') d GROUP BY 1",
    "SELECT round(avg(kwh_consumed / NULLIF(distance_km, 0) * 100)::numeric, 1) FROM trips",
    "SELECT lag(start_soc) OVER (ORDER BY start_date) FROM trips",
    "SELECT DATE(start_date) AS d, count(*) FROM trips GROUP BY 1",
    "SELECT to_char(start_date, 'YYYY-MM') AS m, round(avg(distance_km)::numeric, 1) FROM trips GROUP BY 1 ORDER BY 1",
])
def test_ordinary_analytical_queries_pass(sql):
    assert check_ai_sql(sql) is None, check_ai_sql(sql)


@pytest.mark.parametrize("sql, fragment", [
    # relations the parser sees in every position
    ("SELECT * FROM users", "users"),
    ('SELECT * FROM "users"', "users"),
    ('select * from public."ai_missed_intents"', "ai_missed_intents"),
    ("SELECT * FROM trips, geocoded_locations", "geocoded_locations"),
    ("SELECT * FROM trips CROSS JOIN geocoded_locations", "geocoded_locations"),
    ("SELECT * FROM (geocoded_locations CROSS JOIN trips) x", "geocoded_locations"),
    ("SELECT * FROM (TABLE geocoded_locations) g", "geocoded_locations"),
    ("TABLE geocoded_locations", "geocoded_locations"),
    ("SELECT * FROM (SELECT * FROM users) q", "users"),
    ("SELECT * FROM trips WHERE id IN (SELECT id FROM users)", "users"),
    ("WITH t AS (SELECT * FROM trips) SELECT * FROM users", "users"),
    ("SELECT * FROM pg_catalog.pg_authid", "pg_catalog"),
    ("SELECT * FROM information_schema.tables", "information_schema"),
    ("SELECT * FROM pg_stat_activity", "pg_stat_activity"),
    # a WITH name may not borrow a real table's name, in one scope or another
    ("WITH geocoded_locations AS (SELECT 1) SELECT * FROM geocoded_locations", "reuse a table name"),
    ("WITH users AS (SELECT 1) SELECT * FROM users", "reuse a table name"),
    ("SELECT * FROM (WITH vignettes AS (SELECT 1) SELECT * FROM vignettes) a, vignettes", "reuse a table name"),
    # functions that run a string as SQL, in any spelling
    ("SELECT query_to_xml('select 1', true, false, '')", "query_to_xml"),
    ("SELECT table_to_xml('users', true, false, '')", "table_to_xml"),
    ("SELECT cursor_to_xml('c', 1, true, false, '')", "cursor_to_xml"),
    ("SELECT ts_stat('select 1')", "ts_stat"),
    # the user id rewrite, plain and hidden
    ("SELECT set_config('app.current_user_id', '" + VICTIM + "', true)", "set_config"),
    ("SELECT SET_CONFIG('app.current_user_id', 'x', true)", "set_config"),
    ("SELECT pg_catalog.set_config('app.current_user_id', 'x', true)", "set_config"),
    ("SELECT current_setting('app.current_user_id')", "current_setting"),
    ("WITH s AS (SELECT query_to_xml('select set_'||'config(''app.current_user_id'',''" + VICTIM + "'',true)', true, false, '')) "
     "SELECT count(*) FROM s, vehicle_positions", "query_to_xml"),
    ("SELECT count(*) FROM (SELECT query_to_xml('select set_'||'config(''app.current_user_id'',''" + VICTIM + "'',true)', true, false, '') AS x OFFSET 0) s, vehicle_positions", "query_to_xml"),
    # denial of service, server access
    ("SELECT pg_sleep(600)", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT lo_import('/etc/passwd')", "lo_import"),
    ("SELECT nextval('trips_id_seq')", "nextval"),
    ("SELECT dblink('host=x', 'select 1')", "dblink"),
    ("SELECT current_user", "Connection information"),
    ("SELECT session_user", "Connection information"),
    # not a single plain read
    ("DELETE FROM trips", "SELECT"),
    ("INSERT INTO trips DEFAULT VALUES", "SELECT"),
    ("COPY trips TO '/tmp/x'", "SELECT"),
    ("DO $$ BEGIN PERFORM 1; END $$", "SELECT"),
    ("SET ROLE postgres", "SELECT"),
    ("SELECT * INTO newtable FROM trips", "INTO"),
    ("SELECT * FROM trips FOR UPDATE", "locking"),
    ("WITH d AS (DELETE FROM trips RETURNING *) SELECT * FROM d", "only contain SELECT"),
    ("SELECT 1; SELECT 2", "single"),
    ("SELECT * FROM trips; DROP TABLE trips", "single"),
    ("SELECT $1", "parameters"),
    ("SELECT FROM FROM", "syntax"),
    ("SELECT '" + "x" * 5000 + "'", "longer than"),
])
def test_escapes_are_refused_with_an_actionable_message(sql, fragment):
    msg = check_ai_sql(sql)
    assert msg is not None and msg.startswith("SQL_ERROR"), sql
    assert fragment.lower() in msg.lower(), (sql, msg)


def test_row_cap_is_the_documented_fifty():
    assert AI_SQL_ROW_CAP == 50


@pytest.mark.parametrize("sql, expected", [
    ("SELECT strftime('%Y-%m', start_date) FROM trips", "to_char"),
    ("SELECT STRFTIME('%H', start_date) AS h, count(*) FROM trips GROUP BY h", "EXTRACT(HOUR"),
    ("SELECT ifnull(distance_km, 0) FROM trips", "coalesce"),
    ("SELECT group_concat(display_name) FROM user_vehicles", "string_agg"),
    ("SELECT julianday(end_date) - julianday(start_date) FROM trips", "EPOCH"),
])
def test_a_sqlite_function_gets_the_postgresql_equivalent_so_the_model_can_correct_itself(sql, expected):
    msg = check_ai_sql(sql)
    assert msg and "does not exist in PostgreSQL" in msg and expected in msg, msg


def test_an_unknown_function_still_gets_a_useful_generic_hint():
    msg = check_ai_sql("SELECT frobnicate(id) FROM trips")
    assert "frobnicate() is not available" in msg and "date_trunc" in msg


def test_the_schema_prompt_tells_the_model_this_is_postgresql():
    import asyncio, uuid
    from app.services.chat_tools import get_database_schema
    text = asyncio.run(get_database_schema(None, uuid.uuid4()))
    assert "PostgreSQL, NOT SQLite" in text and "strftime" in text
