"""Static guard for the SQL the AI assistant writes (v1.4.0).

The query is parsed with PostgreSQL's own parser (pglast / libpg_query), never pattern-matched,
and is refused unless every part of it is on a list of things known to be safe:

  * exactly one statement, and it is a plain SELECT (no INTO, no FOR UPDATE, no writable CTE);
  * every relation is an allow-listed table or view in ``public`` or a CTE defined by the query
    (comma joins, parentheses, TABLE x, quoted names are all seen because the parser sees them);
  * every function is on ``ALLOWED_FUNCTIONS`` (aggregates, window, date, math and string
    functions). Functions that run a string as SQL (query_to_xml, ...), change settings
    (set_config) or touch the server (pg_*) are therefore unreachable however the call is spelled.

This is the first of several fences. The database role, its row-level security policies, the
READ ONLY transaction, the statement timeout and the LIMIT wrapper in ``execute_read_only_sql`` are
the others; none of them depends on this guard being perfect, and it does not depend on them.
"""
from __future__ import annotations

from functools import lru_cache

from pglast import parse_sql
from pglast.parser import ParseError
from pglast.visitors import Visitor

MAX_SQL_CHARS = 4000

# Relations the assistant may read. Each is either fenced by row-level security keyed on the
# current user, or a ``security_invoker`` view over fenced tables (migration c1a4e0b7d2f9).
ALLOWED_TABLES = frozenset({
    "user_vehicles", "trips", "charging_sessions", "charging_states",
    "vehicle_states", "battery_health", "vehicle_positions", "charging_curves",
    "drives", "drive_consumptions", "drive_ranges", "odometer_readings",
    "outside_temperatures", "connection_states", "climatization_states",
    "v_trip_analytics", "v_advanced_trip_stats", "v_charging_sessions_analytics",
    "v_climate_penalty_breakdown", "v_winter_penalty_stats", "v_phantom_drain_stats",
    "v_vehicle_state_durations", "v_place_stay_durations",
})

ALLOWED_FUNCTIONS = frozenset({
    # aggregates
    "count", "sum", "avg", "min", "max", "stddev", "stddev_pop", "stddev_samp", "variance",
    "var_pop", "var_samp", "array_agg", "string_agg", "bool_and", "bool_or", "every",
    "json_agg", "jsonb_agg", "percentile_cont", "percentile_disc", "mode", "corr",
    "covar_pop", "covar_samp", "regr_slope", "regr_intercept", "regr_r2",
    # window
    "row_number", "rank", "dense_rank", "percent_rank", "cume_dist", "ntile", "lag", "lead",
    "first_value", "last_value", "nth_value",
    # math
    "abs", "ceil", "ceiling", "floor", "round", "trunc", "sqrt", "cbrt", "power", "pow", "exp",
    "ln", "log", "log10", "mod", "div", "sign", "degrees", "radians", "sin", "cos", "tan", "asin",
    "acos", "atan", "atan2", "width_bucket", "scale", "min_scale",
    # strings
    "lower", "upper", "initcap", "length", "char_length", "character_length", "substr",
    "substring", "concat", "concat_ws", "trim", "btrim", "ltrim", "rtrim", "left", "right",
    "replace", "split_part", "position", "strpos", "lpad", "rpad", "reverse", "repeat", "format",
    "to_char", "to_number", "overlay", "starts_with",
    # arrays and json
    "unnest", "array_length", "cardinality", "array_position", "array_to_string",
    "string_to_array", "generate_series", "to_jsonb", "jsonb_build_object", "jsonb_build_array",
    "jsonb_extract_path_text", "jsonb_array_elements", "jsonb_array_elements_text", "jsonb_each",
    "jsonb_each_text", "jsonb_typeof", "jsonb_array_length",
    # dates and times (extract() parses as pg_catalog.extract / date_part)
    "date_trunc", "date_part", "extract", "age", "now", "make_interval", "make_date",
    "make_timestamp", "make_timestamptz", "timezone", "to_timestamp", "to_date", "date_bin",
    "justify_days", "justify_hours", "justify_interval", "isfinite",
})

# SQLValueFunction operations that only describe the connection.
_REFUSED_VALUE_FUNCTIONS = ("USER", "CATALOG", "SCHEMA")


# Tables that exist in production (many only through migrations, so the models do not list them)
# and must never be reachable by a WITH name that happens to match.
_SENSITIVE_RELATIONS = frozenset({
    "users", "geocoded_locations", "vignettes", "weconnect_errors", "chat_sessions",
    "chat_messages", "alembic_version", "extraction_jobs", "invite_requests",
})
_SENSITIVE_PREFIXES = ("pg_", "ai_", "chat_", "battery_soh_", "information_")


@lru_cache(maxsize=1)
def _known_relations() -> frozenset[str]:
    """Every table name the application defines, so a CTE cannot borrow a real table's name."""
    names = set(ALLOWED_TABLES) | set(_SENSITIVE_RELATIONS)
    try:  # best effort: a failure to import the models must not open anything
        import app.models  # noqa: F401
        from app.models.base import Base
        names.update(t.name for t in Base.metadata.tables.values())
    except Exception:  # noqa: BLE001
        pass
    return frozenset(names)


class _Check(Visitor):
    def __init__(self) -> None:
        super().__init__()
        self.problems: list[str] = []
        self.cte_names: set[str] = set()
        self.relations: list[tuple[str | None, str]] = []

    # ---- statement shape -------------------------------------------------------------------
    def visit_SelectStmt(self, ancestors, node):
        if node.intoClause is not None:
            self.problems.append("SELECT ... INTO is not allowed.")
        if node.lockingClause:
            self.problems.append("Row locking (FOR UPDATE/SHARE) is not allowed.")

    def visit_CommonTableExpr(self, ancestors, node):
        name = node.ctename.lower()
        if name in _known_relations() or name.startswith(_SENSITIVE_PREFIXES):
            self.problems.append(f"A WITH name may not reuse a table name ({node.ctename}); pick another alias.")
        self.cte_names.add(name)
        if type(node.ctequery).__name__ != "SelectStmt":
            self.problems.append("WITH may only contain SELECT queries.")

    # ---- what is read ----------------------------------------------------------------------
    def visit_RangeVar(self, ancestors, node):
        self.relations.append((node.schemaname, node.relname))

    def visit_FuncCall(self, ancestors, node):
        parts = [p.sval for p in node.funcname]
        if len(parts) > 2 or (len(parts) == 2 and parts[0] != "pg_catalog"):
            self.problems.append(f"Function {'.'.join(parts)} is not available.")
            return
        name = parts[-1].lower()
        if name not in ALLOWED_FUNCTIONS:
            self.problems.append(f"Function {name}() is not available to the assistant.")

    def visit_SQLValueFunction(self, ancestors, node):
        op = getattr(node.op, "name", str(node.op))
        if any(word in op for word in _REFUSED_VALUE_FUNCTIONS):
            self.problems.append("Connection information functions are not available.")

    def visit_ParamRef(self, ancestors, node):
        self.problems.append("Query parameters are not supported.")


def check_ai_sql(sql_query: str) -> str | None:
    """Return the SQL_ERROR text to give the model, or None when the query may run."""
    if len(sql_query) > MAX_SQL_CHARS:
        return f"SQL_ERROR: The query is longer than {MAX_SQL_CHARS} characters; make it shorter."
    try:
        statements = parse_sql(sql_query)
    except ParseError as exc:
        return f"SQL_ERROR: SQL syntax error: {str(exc).splitlines()[0][:200]}"
    except Exception as exc:  # noqa: BLE001 - anything the parser rejects is refused
        return f"SQL_ERROR: The query could not be parsed ({exc.__class__.__name__})."
    if len(statements) != 1:
        return "SQL_ERROR: Only a single read-only SELECT query is allowed."
    if type(statements[0].stmt).__name__ != "SelectStmt":
        return "SQL_ERROR: Only SELECT/WITH queries are allowed."

    check = _Check()
    check(statements)
    problems = list(dict.fromkeys(check.problems))
    # cte_names is collected over the whole query, not per WITH scope. That cannot expose anything: a
    # WITH name is refused when it equals an allow-listed, sensitive or application table name, and a
    # table with any other name is unreadable to the database role (least privilege, migration
    # f4a7c2d9e1b3), so a name that "borrows" one reaches nothing.
    for schema, relname in check.relations:
        if schema not in (None, "public"):
            problems.append(f"Schema {schema} is not available; use the table names from get_database_schema.")
        elif schema is None and relname in check.cte_names:
            continue
        elif relname not in ALLOWED_TABLES:
            problems.append(f"Access to table {relname} is not permitted. Only the analytical tables in the schema may be queried.")
    if problems:
        return "SQL_ERROR: " + " ".join(dict.fromkeys(problems))
    return None
