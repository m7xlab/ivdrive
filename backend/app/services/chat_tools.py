import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid
import json
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

LLM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_missing_capability",
            "description": "Call this ONLY if the user asks for vehicle data, metrics, or capabilities that NONE of the other tools can answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "unanswered_query": {"type": "string"}
                },
                "required": ["unanswered_query"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": "Get the list of available database tables and columns for writing SQL queries.",
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_read_only_sql",
            "description": "Execute a PostgreSQL query to retrieve data safely. Connection is pre-filtered to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_query": {"type": "string", "description": "The SQL query to run"}
                },
                "required": ["sql_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fleet_overview",
            "description": "Returns high-level stats for all vehicles owned by the user."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_battery_state",
            "description": "Get the current State of Charge (SOC), estimated remaining range, and charging status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vehicle_name": {"type": "string"}
                },
                "required": ["vehicle_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_battery_health",
            "description": "Get the latest battery State of Health (SOH), voltages, and temperatures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vehicle_name": {"type": "string"}
                },
                "required": ["vehicle_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trip_and_charging_stats",
            "description": "Get aggregated trip distance, efficiency, and charging costs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vehicle_name": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["vehicle_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_longest_trip",
            "description": "Get the longest trip recorded for a specific vehicle.",
            "parameters": {
                "type": "object",
                "properties": {"vehicle_name": {"type": "string"}},
                "required": ["vehicle_name"]
            }
        }
    }
]

async def run_query(db: AsyncSession, sql: text, params: dict) -> list:
    try:
        result = await db.execute(sql, params)
        return result.fetchall()
    except Exception as e:
        logger.error(f"Tool query error: {e}")
        try:
            await db.rollback()
        except:
            pass
        return []


async def log_missing_capability(db: AsyncSession, user_id: uuid.UUID, query: str) -> str:
    """Logs questions we don't have tools for yet, preventing hallucinations."""
    sql = text("INSERT INTO ai_missed_intents (user_id, query) VALUES (:uid, :q)")
    try:
        await db.execute(sql, {"uid": str(user_id), "q": query})
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to log missed intent: {e}")
        await db.rollback()
    return "I don't currently have the ability to calculate or fetch that specific data. However, I have automatically logged this exact question to my developers so they can build this capability for you in a future update."


async def get_database_schema(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Returns the curated database schema for the LLM."""
    return """
TABLES & COLUMNS:
- user_vehicles (id, display_name, battery_capacity_kwh, manufacturer, model, wltp_range_km)
- trips (id, user_vehicle_id, start_date, end_date, distance_km, start_soc, end_soc, kwh_consumed, avg_temp_celsius)
- charging_sessions (id, user_vehicle_id, session_start, session_end, start_level, end_level, energy_kwh, actual_cost_eur, provider_name, avg_temp_celsius)
- charging_states (id, user_vehicle_id, last_date, battery_pct, remaining_range_m, charge_power_kw, remaining_time_min, target_soc_pct)
- vehicle_states (id, user_vehicle_id, last_date, doors_locked, windows_open, trunk_open, bonnet_open)
- battery_health (id, user_vehicle_id, captured_at, hv_battery_soh, hv_battery_degradation_pct, hv_battery_voltage, hv_battery_temperature)
- vehicle_positions (id, user_vehicle_id, recorded_at, latitude, longitude, speed_kmh, heading, altitude)

IMPORTANT RULES:
1. Row-Level Security (RLS) is ACTIVE. The database automatically filters ALL rows to only show data for the current user.
2. You DO NOT need to filter by `user_id`. You DO NOT need to `JOIN user_vehicles` just to verify ownership.
3. If the user mentions a vehicle by name (e.g., 'BlackMagic'), use exact matching: `JOIN user_vehicles v ON t.user_vehicle_id = v.id WHERE v.display_name = 'BlackMagic'`. Do not use ILIKE '%...%' because it will accidentally mix data from similar vehicle names (e.g. 'BlackMagic' vs 'BlackMagic80').
4. Always use aggregate functions (SUM, AVG, COUNT) or LIMIT your queries to 50 rows max.
"""

async def execute_read_only_sql(db: AsyncSession, user_id: uuid.UUID, sql_query: str) -> str:
    lower_sql = sql_query.lower()
    if any(forbidden in lower_sql for forbidden in ["insert ", "update ", "delete ", "drop ", "create ", "alter ", "truncate ", "grant ", "revoke ", "commit", "rollback"]):
        return "SQL_ERROR: Only SELECT queries are allowed."
        
    try:
        async with db.bind.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SET LOCAL ROLE ivdrive_ai_readonly;"))
                await conn.execute(text(f"SET LOCAL app.current_user_id = '{user_id}';"))
                result = await conn.execute(text(sql_query))
                rows = result.fetchall()
                keys = list(result.keys())
                
                dict_rows = [dict(zip(keys, row)) for row in rows]
                for row in dict_rows:
                    for k, v in row.items():
                        if isinstance(v, datetime):
                            row[k] = v.isoformat()
                        elif isinstance(v, uuid.UUID):
                            row[k] = str(v)
                            
                json_res = json.dumps(dict_rows[:50])
                return f"SQL SUCCESS! Rows returned:\n{json_res}"
    except Exception as e:
        return f"SQL_ERROR: {str(e)}"

async def get_fleet_overview(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Returns high-level stats for all vehicles owned by the user."""
    sql = text("""
        SELECT
            v.id, v.display_name, v.battery_capacity_kwh,
            (SELECT MAX(t.start_date) FROM trips t WHERE t.user_vehicle_id = v.id) as last_trip,
            (SELECT MAX(c.session_start) FROM charging_sessions c WHERE c.user_vehicle_id = v.id) as last_charge,
            (SELECT COUNT(*) FROM trips t WHERE t.user_vehicle_id = v.id) as trip_count,
            (SELECT COALESCE(SUM(COALESCE(c.actual_cost_eur, c.base_cost_eur)), 0) FROM charging_sessions c WHERE c.user_vehicle_id = v.id) as total_cost
        FROM user_vehicles v
        WHERE v.user_id = :uid
        ORDER BY v.display_name
    """)
    rows = await run_query(db, sql, {"uid": str(user_id)})
    if not rows:
        return "No vehicles found for this user."
    
    parts = [f"### FLEET OVERVIEW ({len(rows)} Vehicles Total)"]
    sorted_rows = sorted(rows, key=lambda x: x[3].timestamp() if x[3] else 0, reverse=True)
    
    for r in sorted_rows:
        name = r[1] or "?"
        batt = r[2] or 0
        last_t = r[3].strftime("%Y-%m-%d") if r[3] else "no trips"
        last_c = r[4].strftime("%Y-%m-%d") if r[4] else "no charges"
        tc = r[5] or 0
        cost = r[6] or 0.0
        parts.append(f"- **{name}**: {batt:.0f}kWh | {tc} trips (last {last_t}) | Charge spend: €{cost:.2f} (last {last_c})")
    
    return "\n".join(parts)


async def get_current_battery_state(db: AsyncSession, user_id: uuid.UUID, vehicle_name: str) -> str:
    """Get the current State of Charge (SOC) and estimated remaining range."""
    sql = text("""
        SELECT
            cs.last_date,
            cs.battery_pct,
            cs.remaining_range_m,
            cs.state,
            cs.charge_power_kw,
            v.display_name
        FROM charging_states cs
        JOIN user_vehicles v ON v.id = cs.user_vehicle_id
        WHERE v.user_id = :uid AND v.display_name ILIKE :vname
        ORDER BY cs.last_date DESC
        LIMIT 1
    """)
    rows = await run_query(db, sql, {"uid": str(user_id), "vname": f"%{vehicle_name}%"})
    if not rows:
        return f"No current battery state found for '{vehicle_name}'."
    
    r = rows[0]
    date_str = r[0].strftime("%Y-%m-%d %H:%M") if r[0] else "?"
    soc = r[1]
    range_km = (r[2] / 1000) if r[2] is not None else 0
    state = r[3] or "Unknown"
    power = r[4] or 0.0
    
    parts = [f"Current battery state for {r[5]} (as of {date_str}):"]
    if soc is not None: parts.append(f"- State of Charge (SOC): {soc}%")
    if range_km > 0: parts.append(f"- Estimated remaining range: {range_km:.1f} km")
    parts.append(f"- Charging state: {state}")
    if state.lower() == "charging": parts.append(f"- Charging power: {power:.1f} kW")
    
    return "\n".join(parts)

async def get_battery_health(db: AsyncSession, user_id: uuid.UUID, vehicle_name: str) -> str:
    """Get the latest battery State of Health (SOH), voltages, and temperatures for a specific vehicle."""
    sql = text("""
        SELECT
            bh.captured_at,
            bh.hv_battery_soh,
            bh.hv_battery_degradation_pct,
            bh.hv_battery_voltage,
            bh.hv_battery_current,
            bh.hv_battery_temperature,
            bh.twelve_v_battery_voltage,
            bh.twelve_v_battery_soc,
            bh.cell_voltage_min,
            bh.cell_voltage_max,
            bh.cell_voltage_avg,
            bh.cell_temperature_min,
            bh.cell_temperature_max,
            bh.cell_temperature_avg,
            bh.imbalance_mv,
            v.battery_capacity_kwh,
            v.display_name
        FROM battery_health bh
        JOIN user_vehicles v ON v.id = bh.user_vehicle_id
        WHERE v.user_id = :uid AND v.display_name ILIKE :vname
        ORDER BY bh.captured_at DESC
        LIMIT 1
    """)
    rows = await run_query(db, sql, {"uid": str(user_id), "vname": f"%{vehicle_name}%"})
    if not rows:
        return f"No battery health data found for vehicle matching '{vehicle_name}'."
    
    r = rows[0]
    captured_str = r[0].strftime("%Y-%m-%d %H:%M") if r[0] else "?"
    parts = [f"Battery health for {r[16]} (as of {captured_str})"]
    if r[1] is not None: 
        parts.append(f"HV SOH {r[1]:.1f}%")
        # Anomaly detection for SOH
        if abs(r[1] - 95.0) < 0.01:
            parts.append("[ANOMALY: SOH is exactly 95.0%. This is likely a hardcoded/stale default from the Škoda API.]")
    if r[2] is not None: parts.append(f"degradation {r[2]:.1f}%")
    if r[3] is not None: parts.append(f"HV voltage {r[3]:.1f}V")
    if r[4] is not None: parts.append(f"HV current {r[4]:.1f}A")
    if r[5] is not None: parts.append(f"battery temp {r[5]:.1f}C")
    if r[6] is not None: parts.append(f"12V battery {r[6]:.1f}V")
    if r[7] is not None: parts.append(f"12V SOC {r[7]:.0f}%")
    if r[14] is not None: parts.append(f"cell imbalance {r[14]:.0f}mV")
    if r[15] is not None: parts.append(f"design capacity {r[15]:.0f}kWh")
    if r[8] is not None and r[9] is not None:
        parts.append(f"cell voltage {r[8]:.3f}-{r[9]:.3f}V (avg {r[10]:.3f}V)")
    if r[11] is not None and r[12] is not None:
        parts.append(f"cell temp {r[11]:.1f}-{r[12]:.1f}C (avg {r[13]:.1f}C)")
    
    return ". ".join(parts)

async def get_trip_and_charging_stats(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    vehicle_name: str, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None
) -> str:
    """Get aggregated trip distance, efficiency, and charging costs for a vehicle over an optional date range."""
    v_sql = text("SELECT id, display_name FROM user_vehicles WHERE user_id = :uid AND display_name ILIKE :vname LIMIT 1")
    v_rows = await run_query(db, v_sql, {"uid": str(user_id), "vname": f"%{vehicle_name}%"})
    if not v_rows:
        return f"No vehicle found matching '{vehicle_name}'."
    
    vid = v_rows[0][0]
    actual_vname = v_rows[0][1]

    date_filter_t = ""
    date_filter_c = ""
    params = {"vid": vid}
    
    if start_date:
        date_filter_t += " AND t.start_date >= :start_dt"
        date_filter_c += " AND c.session_start >= :start_dt"
        params["start_dt"] = datetime.strptime(f"{start_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
    if end_date:
        date_filter_t += " AND t.start_date <= :end_dt"
        date_filter_c += " AND c.session_start <= :end_dt"
        params["end_dt"] = datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")

    trip_sql = text(f"""
        SELECT
            COUNT(*)::int AS trip_count,
            COALESCE(MAX(t.end_odometer) - MIN(t.start_odometer), COALESCE(SUM(t.distance_km), 0))::float AS total_km,
            COALESCE(SUM(t.kwh_consumed), 0)::float AS total_kwh,
            COALESCE(AVG(t.avg_temp_celsius), 0)::float AS avg_temp,
            MAX(t.start_date) AS last_trip,
            SUM(CASE WHEN t.distance_km = 0 OR t.distance_km IS NULL THEN 1 ELSE 0 END)::int AS zero_km_trips
        FROM trips t
        WHERE t.user_vehicle_id = :vid AND t.end_date IS NOT NULL {date_filter_t}
    """)
    t_rows = await run_query(db, trip_sql, params)
    
    charge_sql = text(f"""
        SELECT
            COUNT(*)::int AS charge_count,
            COALESCE(SUM(c.energy_kwh), 0)::float AS total_kwh,
            COALESCE(SUM(COALESCE(c.actual_cost_eur, c.base_cost_eur)), 0)::float AS total_cost,
            MAX(c.session_start) AS last_charge
        FROM charging_sessions c
        WHERE c.user_vehicle_id = :vid AND c.session_end IS NOT NULL {date_filter_c}
    """)
    c_rows = await run_query(db, charge_sql, params)

    res = [f"Stats for {actual_vname} (Period: {start_date or 'All-time'} to {end_date or 'Present'}):"]
    if t_rows and t_rows[0] and t_rows[0][0] > 0:
        r = t_rows[0]
        last_t = r[4].strftime("%Y-%m-%d") if r[4] else "N/A"
        avg_kwh_100 = (r[2] / r[1] * 100) if r[1] > 0 else 0
        res.append(f"- Trips: {r[0]} trips, {r[1]:.0f} km total, {r[2]:.1f} kWh consumed (avg {avg_kwh_100:.1f} kWh/100km). Average temp: {r[3]:.1f}°C. Last trip: {last_t}.")
        if r[5] > 0:
            res.append(f"  [ANOMALY: Detected {r[5]} zero-km phantom trips which may inflate trip counts.]")
    else:
        res.append(f"- Trips: No trips found in this period.")
        
    if c_rows and c_rows[0] and c_rows[0][0] > 0:
        r = c_rows[0]
        last_c = r[3].strftime("%Y-%m-%d") if r[3] else "N/A"
        res.append(f"- Charging: {r[0]} sessions, {r[1]:.1f} kWh total added, €{r[2]:.2f} total cost. Last charge: {last_c}.")
    else:
        res.append(f"- Charging: No charging sessions found in this period.")

    return "\n".join(res)

async def get_longest_trip(db: AsyncSession, user_id: uuid.UUID, vehicle_name: str) -> str:
    """Get the longest trip recorded for a vehicle."""
    v_sql = text("SELECT id, display_name FROM user_vehicles WHERE user_id = :uid AND display_name ILIKE :vname LIMIT 1")
    v_rows = await run_query(db, v_sql, {"uid": str(user_id), "vname": f"%{vehicle_name}%"})
    if not v_rows:
        return f"No vehicle found matching '{vehicle_name}'."
    
    vid = v_rows[0][0]
    actual_vname = v_rows[0][1]

    sql = text("""
        SELECT COALESCE(t.distance_km, 0)::float, t.start_date, COALESCE(t.avg_temp_celsius, 0)::float
        FROM trips t
        WHERE t.user_vehicle_id = :vid
        ORDER BY t.distance_km DESC NULLS LAST LIMIT 1
    """)
    rows = await run_query(db, sql, {"vid": vid})
    if not rows:
        return f"No trips found for {actual_vname}."
    
    r = rows[0]
    date_str = r[1].strftime("%Y-%m-%d") if r[1] else "?"
    return f"The longest trip for {actual_vname} was {r[0]:.1f} km on {date_str} (avg temp {r[2]:.1f}°C)."

async def dispatch_tool_call_extended(db: AsyncSession, user_id: uuid.UUID, tool_call: dict) -> dict:
    tool_name = tool_call.get("tool") or tool_call.get("tool_code") or tool_call.get("name")
    args = tool_call.get("args") or tool_call.get("parameters") or tool_call.get("arguments") or {}
    try:
        if tool_name == "get_fleet_overview":
            chunk = await get_fleet_overview(db, user_id)
            return {"type": "all_vehicles_summary", "id": "aggregate", "chunk": chunk}
        elif tool_name == "get_current_battery_state":
            chunk = await get_current_battery_state(db, user_id, args.get("vehicle_name", ""))
            return {"type": "battery_health_summary", "id": "aggregate", "chunk": chunk}
        elif tool_name == "get_battery_health":
            chunk = await get_battery_health(db, user_id, args.get("vehicle_name", ""))
            return {"type": "battery_health_summary", "id": "aggregate", "chunk": chunk}
        elif tool_name == "get_trip_and_charging_stats":
            chunk = await get_trip_and_charging_stats(
                db, 
                user_id, 
                args.get("vehicle_name", ""), 
                args.get("start_date"), 
                args.get("end_date")
            )
            return {"type": "trip_summary", "id": "aggregate", "chunk": chunk}
        elif tool_name == "get_database_schema":
            chunk = await get_database_schema(db, user_id)
            return {"type": "schema", "id": "aggregate", "chunk": chunk}
        elif tool_name == "execute_read_only_sql":
            chunk = await execute_read_only_sql(db, user_id, args.get("sql_query", ""))
            return {"type": "sql_result", "id": "aggregate", "chunk": chunk}
        elif tool_name == "log_missing_capability":
            chunk = await log_missing_capability(db, user_id, args.get("unanswered_query", ""))
            return {"type": "system_fallback", "id": "aggregate", "chunk": chunk}
        elif tool_name == "get_longest_trip":
            chunk = await get_longest_trip(db, user_id, args.get("vehicle_name", ""))
            return {"type": "trip_summary", "id": "aggregate", "chunk": chunk}
        else:
            return None
    except Exception as e:
        logger.error(f"Tool dispatch error: {e}")
        return None

async def route_intent_via_llm(
    query: str,
    vehicle_names: list[str],
    call_llm_func,
    conversation_history: list[dict] | None = None,
    detected_vehicle_name: str | None = None,
    usage_stats: dict | None = None,
) -> list[dict]:
    """
    Uses the primary LLM to determine which tools to run.

    Multi-turn support:
      - If conversation_history is provided, the LLM can resolve pronouns
        like "that", "it", "the last one", "how much did that cost?" by
        reading the prior turns.
      - If detected_vehicle_name is provided (resolved by chat.py from the
        current message OR history), the LLM uses it as a hint and the
        caller back-fills any empty `vehicle_name` arg from it.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Build compact conversation context for the router prompt.
    # Only inject the most recent turns (cap at 6) and truncate each to 200 chars
    # so the router prompt stays small and the LLM can resolve references cheaply.
    history_block = ""
    if conversation_history:
        recent = conversation_history[-6:]
        if recent:
            history_lines = ["Previous conversation (use to resolve pronouns like 'that', 'it', 'last one'):"]
            for msg in recent:
                role = msg.get("role", "?").capitalize()
                content = (msg.get("content", "") or "")[:200]
                history_lines.append(f"- {role}: {content}")
            history_block = "\n".join(history_lines) + "\n\n"

    vehicle_hint = ""
    if detected_vehicle_name:
        vehicle_hint = (
            f"\nThe user's current question most likely refers to vehicle: "
            f"'{detected_vehicle_name}'. If the question is ambiguous (e.g. 'how much did that cost?'), "
            f"use this vehicle. Pass this exact name as the `vehicle_name` argument to vehicle-specific tools.\n"
        )

    prompt = f"""
    You are an intent router for a vehicle telemetry database.
    Today is {today}.
    The user owns these vehicles: {', '.join(vehicle_names) if vehicle_names else 'None'}.{vehicle_hint}
    {history_block}
    Available tools:
    1. get_database_schema(): use this to see exactly which tables and columns exist in the database.
    2. execute_read_only_sql(sql_query): use this to write custom SQL to answer analytical questions.
    3. get_fleet_overview(): returns fleet summary
    4. get_battery_health(vehicle_name): returns SOH and battery data
    5. get_trip_and_charging_stats(vehicle_name, start_date, end_date): returns aggregated trips and charges.
    6. get_longest_trip(vehicle_name): returns longest trip.
    7. get_current_battery_state(vehicle_name): returns current SOC and remaining range (use this if user asks how many kilometers they can drive).
    8. log_missing_capability(unanswered_query): use this ONLY if the tables in the schema do not contain the data needed.

    User query: "{query}"

    CRITICAL RULES:
    - If the user asks an analytical question that manual tools (3-7) cannot answer, you MUST use `get_database_schema` to check if the data exists, and then write a SQL query using `execute_read_only_sql`. Only use `log_missing_capability` if the schema confirms we do not have the data.
    - If a previous conversation turn already established which vehicle the user is discussing, ALWAYS pass that exact `vehicle_name` to vehicle-specific tools. NEVER pass an empty string or omit the vehicle when context makes it clear.
    - For follow-up questions ("how much did that cost?", "what was the last trip?", "is that recent?"), prefer tools 5, 6, or 7 with the previously discussed vehicle — DO NOT call `log_missing_capability` just because the current question is short.

    Return ONLY a JSON array of tools to call. E.g.:
    [
      {{"tool": "log_missing_capability", "args": {{"unanswered_query": "{query}"}}}}
    ]
    """

    try:
        response_text = await call_llm_func(
            prompt=prompt,
            context_chunks=[],
            provider="gemini",
            system_override="You are a JSON-only router. Return only valid JSON array.",
            usage_stats=usage_stats,
        )
        
        # Extract the JSON array using regex just in case LLM added conversational text
        import re
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            cleaned = match.group(0)
            return json.loads(cleaned)
            
        return []
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Intent routing failed: {e}")
        return []
