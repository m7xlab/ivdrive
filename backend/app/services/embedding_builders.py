"""Content builders for AI embeddings.

Shared by:
- app.scripts.embed_all  (one-shot backfill, regenerates everything)
- app.services.embedding_worker  (incremental, processes ai_embeddings_queue)

Each builder takes (session, vehicle_id: str) and returns
(chunk_text: str, metadata: dict) or None if no source data exists.

content_type → (prefix_in_queue, builder_function)
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Public map: content_type -> (queue content_id prefix, builder)
BuilderFn = Callable[[AsyncSession, str], Awaitable[Optional[tuple[str, dict]]]]

CONTENT_TYPES: dict[str, tuple[str, BuilderFn]] = {}


def register(content_type: str, prefix: str) -> Callable[[BuilderFn], BuilderFn]:
    """Decorator to register a content builder."""
    def deco(fn: BuilderFn) -> BuilderFn:
        CONTENT_TYPES[content_type] = (prefix, fn)
        return fn
    return deco


# ─── builders ────────────────────────────────────────────────────────────────


@register("vehicle_summary", "vehicle")
async def build_vehicle_summary(session: AsyncSession, vid: str) -> Optional[tuple[str, dict]]:
    result = await session.execute(
        text("""
            SELECT id, user_id, display_name, manufacturer, model, model_year,
                   body_type, trim_level, exterior_colour, battery_capacity_kwh,
                   max_charging_power_kw, engine_power_kw, wltp_range_km,
                   active_interval_seconds, parked_interval_seconds,
                   charger_power_kw, ice_l_per_100km,
                   uphill_kwh_per_100km_per_100m, downhill_kwh_per_100km_per_100m,
                   speed_city_threshold_kmh, speed_highway_threshold_kmh,
                   temp_cold_max_celsius, temp_optimal_min_celsius, temp_optimal_max_celsius
            FROM user_vehicles WHERE id = :vid
        """),
        {"vid": vid},
    )
    r = result.first()
    if not r:
        return None
    name = r[2] or "Unknown"
    body, trim, colour = r[6] or "?", r[7] or "", r[8] or ""
    batt, max_charge, power = r[9], r[10], r[11]
    wltp = r[12]
    charger_kw = r[15]
    ice = r[16]
    uphill, downhill = r[17], r[18]
    city_th, highway_th = r[19], r[20]
    cold_max, opt_min, opt_max = r[21], r[22], r[23]

    specs = []
    if isinstance(batt, (int, float)): specs.append(f"{batt:.0f}kWh battery")
    if isinstance(power, (int, float)): specs.append(f"{power}kW engine")
    if isinstance(max_charge, (int, float)): specs.append(f"{max_charge}kW max charging")
    if isinstance(wltp, (int, float)): specs.append(f"{wltp:.0f}km WLTP range")
    if isinstance(charger_kw, (int, float)): specs.append(f"{charger_kw}kW home charger")
    if isinstance(city_th, (int, float)) and isinstance(highway_th, (int, float)): specs.append(f"City <= {city_th:.0f}km/h, Highway <= {highway_th:.0f}km/h")
    if all(isinstance(x, (int, float)) for x in (cold_max, opt_min, opt_max)): specs.append(f"Optimal temp {opt_min:.0f}-{opt_max:.0f}C, cold max {cold_max:.0f}C")
    if all(isinstance(x, (int, float)) for x in (uphill, downhill)): specs.append(f"Uphill +{uphill:.2f}, downhill {downhill:.2f} kWh/100km/100m")
    if isinstance(ice, (int, float)): specs.append(f"{ice}L/100km ICE consumption")
    specs_str = " | ".join(specs) if specs else "No specifications available"

    chunk = f"Vehicle: {name} | {r[5] or '?'} {r[3]} {r[2]} {trim} | {body} body | {colour} | {specs_str}"
    meta = {"source": "Vehicle Info", "vehicle_name": name, "year": r[5],
            "make": r[3], "model": r[2], "battery_kwh": batt, "power_kw": power}
    return chunk, meta


@register("battery_health_summary", "battery")
async def build_battery_health_summary(session: AsyncSession, vid: str) -> Optional[tuple[str, dict]]:
    result = await session.execute(
        text("""
            WITH latest AS (
                SELECT DISTINCT ON (bh.user_vehicle_id)
                       bh.user_vehicle_id, v.user_id, v.display_name,
                       bh.captured_at,
                       bh.hv_battery_soh, bh.hv_battery_degradation_pct,
                       bh.hv_battery_voltage, bh.hv_battery_current, bh.hv_battery_temperature,
                       bh.twelve_v_battery_voltage, bh.twelve_v_battery_soc, bh.twelve_v_battery_soh,
                       bh.cell_voltage_min, bh.cell_voltage_max, bh.cell_voltage_avg,
                       bh.cell_temperature_min, bh.cell_temperature_max, bh.cell_temperature_avg,
                       bh.imbalance_mv, v.battery_capacity_kwh
                FROM battery_health bh
                JOIN user_vehicles v ON v.id = bh.user_vehicle_id
                WHERE bh.user_vehicle_id = :vid
                ORDER BY bh.user_vehicle_id, bh.captured_at DESC
            )
            SELECT * FROM latest
        """),
        {"vid": vid},
    )
    r = result.first()
    if not r:
        return None
    name = r[2] or "Unknown"
    captured = r[3].strftime("%Y-%m-%d %H:%M") if r[3] else "unknown"
    parts = [f"Battery health for {name} (as of {captured})"]
    if r[4] is not None: parts.append(f"SOH {r[4]:.1f}%")
    if r[5] is not None: parts.append(f"degradation {r[5]:.1f}%")
    if r[6] is not None: parts.append(f"HV {r[6]:.1f}V")
    if r[7] is not None: parts.append(f"HV current {r[7]:.1f}A")
    if r[8] is not None: parts.append(f"battery temp {r[8]:.1f}C")
    if r[9] is not None: parts.append(f"12V battery {r[9]:.1f}V")
    if r[10] is not None: parts.append(f"12V SOC {r[10]:.0f}%")
    if r[19] is not None: parts.append(f"design capacity {r[19]:.0f}kWh")
    if r[12] is not None and r[13] is not None: parts.append(f"cell voltage {r[12]:.3f}-{r[13]:.3f}V (avg {r[14]:.3f}V)")
    if r[15] is not None and r[16] is not None: parts.append(f"cell temp {r[15]:.1f}-{r[16]:.1f}C (avg {r[17]:.1f}C)")
    if r[18] is not None: parts.append(f"cell imbalance {r[18]:.0f}mV")
    chunk = ". ".join(parts)
    meta = {"source": "Battery Health", "vehicle_name": name, "soh": r[4], "captured_at": captured}
    return chunk, meta


@register("charging_curve_summary", "curve")
async def build_charging_curve_summary(session: AsyncSession, vid: str) -> Optional[tuple[str, dict]]:
    result = await session.execute(
        text("""
            SELECT v.user_id, v.display_name,
                   COUNT(*) as pt_count, COUNT(DISTINCT cc.session_id) as sess_count,
                   MIN(cc.captured_at) as first_cap, MAX(cc.captured_at) as last_cap,
                   MAX(cc.power_kw) as max_pow, AVG(cc.power_kw) as avg_pow,
                   MIN(cc.battery_temp_celsius) as min_t, MAX(cc.battery_temp_celsius) as max_t,
                   AVG(cc.battery_temp_celsius) as avg_t,
                   MIN(cc.soc_pct) as min_soc, MAX(cc.soc_pct) as max_soc,
                   AVG(cc.current_a) as avg_curr
            FROM charging_curves cc
            JOIN user_vehicles v ON v.id = cc.user_vehicle_id
            WHERE cc.user_vehicle_id = :vid
            GROUP BY v.user_id, v.display_name HAVING COUNT(*) > 0
        """),
        {"vid": vid},
    )
    r = result.first()
    if not r:
        return None
    uid, name = r[0], r[1] or "Unknown"
    first_s = r[4].strftime("%Y-%m-%d") if r[4] else "?"
    last_s = r[5].strftime("%Y-%m-%d") if r[5] else "?"
    chunk = (f"Charging curve data for {name}: {r[2]} data points across {r[3]} sessions "
             f"({first_s} - {last_s}). Peak {r[6]:.1f}kW, avg {r[7]:.1f}kW. "
             f"SOC range {r[11]:.0f}%-{r[12]:.0f}%. "
             f"Battery temp range {r[8]:.1f}-{r[9]:.1f}C (avg {r[10]:.1f}C). Avg current {r[13]:.1f}A.")
    meta = {"source": "Charging Curves", "vehicle_name": name,
            "sessions": r[3], "max_power_kw": r[6], "avg_power_kw": r[7]}
    return chunk, meta


@register("vehicle_state_summary", "vstate")
async def build_vehicle_state_summary(session: AsyncSession, vid: str) -> Optional[tuple[str, dict]]:
    result = await session.execute(
        text("""
            WITH recent AS (
                SELECT DISTINCT ON (vs.user_vehicle_id)
                       vs.user_vehicle_id, v.user_id, v.display_name,
                       vs.state, vs.doors_locked, vs.doors_open, vs.windows_open,
                       vs.lights_on, vs.trunk_open, vs.bonnet_open, vs.last_date
                FROM vehicle_states vs
                JOIN user_vehicles v ON v.id = vs.user_vehicle_id
                WHERE vs.user_vehicle_id = :vid
                ORDER BY vs.user_vehicle_id, vs.last_date DESC
            ),
            state_dur AS (
                SELECT user_vehicle_id, state,
                       COUNT(*) as state_count,
                       SUM(EXTRACT(EPOCH FROM (last_date - first_date))) as total_seconds
                FROM vehicle_states
                WHERE user_vehicle_id = :vid
                  AND first_date > NOW() - INTERVAL '30 days'
                GROUP BY user_vehicle_id, state
            ),
            ranked AS (
                SELECT user_vehicle_id, state, state_count, total_seconds,
                       ROW_NUMBER() OVER (PARTITION BY user_vehicle_id ORDER BY total_seconds DESC) as rn
                FROM state_dur
            )
            SELECT
                r.user_vehicle_id, v.user_id, v.display_name,
                r.state, r.state_count, ROUND(r.total_seconds / 3600.0, 1) as hours,
                rec.state as current_state, rec.doors_locked, rec.doors_open,
                rec.windows_open, rec.lights_on, rec.trunk_open, rec.bonnet_open, rec.last_date
            FROM ranked r
            JOIN user_vehicles v ON v.id = r.user_vehicle_id
            JOIN recent rec ON rec.user_vehicle_id = r.user_vehicle_id
            WHERE r.rn <= 3
            ORDER BY r.rn
        """),
        {"vid": vid},
    )
    rows = result.fetchall()
    if not rows:
        return None
    uid = str(rows[0][1])
    name = rows[0][2] or "Unknown"
    top_states = [f"{r[3]} ({r[4]:.1f}h)" for r in rows if r[3] is not None]
    r0 = rows[0]
    states_str = "; ".join(top_states) if top_states else "No recent data"
    last_str = r0[12].strftime("%Y-%m-%d %H:%M") if r0[12] else "?"
    chunk = (f"Vehicle state summary for {name} (last update {last_str}): "
             f"Current state: {r0[6] or 'unknown'}. "
             f"Doors: locked={r0[7]}, open={r0[8] or 'none'}. "
             f"Windows: {r0[9] or 'all closed'}. "
             f"Lights: {r0[10] or 'off'}. "
             f"Trunk: {'open' if r0[11] else 'closed'}. "
             f"Bonnet: {'open' if r0[12] else 'closed'}. "
             f"Top states last 30 days: {states_str}.")
    meta = {"source": "Vehicle State", "vehicle_name": name, "current_state": r0[6]}
    return chunk, meta


@register("drive_consumption_summary", "drive")
async def build_drive_consumption_summary(session: AsyncSession, vid: str) -> Optional[tuple[str, dict]]:
    result = await session.execute(
        text("""
            SELECT v.user_id, v.display_name,
                   COUNT(*) as rec_count, AVG(d.consumption) as avg_cons,
                   MIN(d.consumption) as min_cons, MAX(d.consumption) as max_cons,
                   AVG(d.temperature_celsius) as avg_t, MIN(d.temperature_celsius) as min_t,
                   MAX(d.temperature_celsius) as max_t,
                   MIN(d.first_date) as first_rec, MAX(d.last_date) as last_rec
            FROM drive_consumptions d
            JOIN drives dr ON dr.id = d.drive_id
            JOIN user_vehicles v ON v.id = dr.user_vehicle_id
            WHERE dr.user_vehicle_id = :vid
            GROUP BY v.user_id, v.display_name HAVING COUNT(*) > 0
        """),
        {"vid": vid},
    )
    r = result.first()
    if not r:
        return None
    uid, name = r[0], r[1] or "Unknown"
    first_s = r[9].strftime("%Y-%m-%d") if r[9] else "?"
    last_s = r[10].strftime("%Y-%m-%d") if r[10] else "?"
    chunk = (f"Drive consumption for {name}: {r[2]} records ({first_s} - {last_s}). "
             f"Average consumption {r[3]:.2f}kWh/100km (range {r[4]:.2f}-{r[5]:.2f}). "
             f"Average ambient temp {r[6]:.1f}C (range {r[7]:.1f}-{r[8]:.1f}C).")
    meta = {"source": "Drive Consumption", "vehicle_name": name,
            "avg_consumption": r[3], "record_count": r[2]}
    return chunk, meta


@register("charging_session_summary", "charge_summary")
async def build_charging_session_summary(session: AsyncSession, vid: str) -> Optional[tuple[str, dict]]:
    result = await session.execute(
        text("""
            SELECT
                v.user_id, v.display_name,
                COUNT(*)::int as sess_count,
                COALESCE(SUM(cs.energy_kwh), 0)::float as total_en,
                COALESCE(AVG(cs.energy_kwh), 0)::float as avg_en,
                COALESCE(SUM(COALESCE(cs.actual_cost_eur, cs.base_cost_eur)), 0)::float as total_cost,
                COALESCE(AVG(COALESCE(cs.actual_cost_eur, cs.base_cost_eur)), 0)::float as avg_cost,
                COUNT(CASE WHEN cs.charging_type = 'DC' THEN 1 END)::int as dc_count,
                COUNT(CASE WHEN cs.charging_type = 'AC' THEN 1 END)::int as ac_count,
                MIN(cs.session_start) as first_s, MAX(cs.session_start) as last_s,
                COALESCE(AVG(cs.avg_temp_celsius), 0)::float as avg_t
            FROM charging_sessions cs
            JOIN user_vehicles v ON v.id = cs.user_vehicle_id
            WHERE cs.user_vehicle_id = :vid
            GROUP BY v.user_id, v.display_name HAVING COUNT(*) > 0
        """),
        {"vid": vid},
    )
    r = result.first()
    if not r:
        return None
    uid, name = r[0], r[1] or "Unknown"
    first_s = r[9].strftime("%Y-%m-%d") if r[9] else "?"
    last_s = r[10].strftime("%Y-%m-%d") if r[10] else "?"
    chunk = (f"Charging summary for {name}: {r[2]} sessions total, {r[3]:.1f}kWh energy, "
             f"EUR {r[5]:.2f} total cost. Avg per session: {r[4]:.1f}kWh, EUR {r[6]:.2f}. "
             f"{r[7]} DC, {r[8]} AC sessions. Period: {first_s} - {last_s}. "
             f"Avg ambient temp: {r[11]:.1f}C.")
    meta = {"source": "Charging Summary", "vehicle_name": name,
            "session_count": r[2], "total_cost": r[5]}
    return chunk, meta



@register("climate_penalty_summary", "climate_penalty")
async def build_climate_penalty_summary(session: AsyncSession, vid: str) -> Optional[tuple[str, dict]]:
    result = await session.execute(
        text('''
            SELECT v.user_id, v.display_name,
                   COUNT(c.user_vehicle_id) as rec_count,
                   MAX(CASE WHEN c.hvac_state = 'HEATING' THEN c.avg_consumption_kwh_100km END) as heating_cost,
                   MAX(CASE WHEN c.hvac_state = 'COOLING' THEN c.avg_consumption_kwh_100km END) as cooling_cost,
                   MAX(CASE WHEN c.hvac_state = 'OFF' THEN c.avg_consumption_kwh_100km END) as baseline_cost
            FROM user_vehicles v
            LEFT JOIN v_climate_penalty_breakdown c ON c.user_vehicle_id = v.id
            WHERE v.id = :vid
            GROUP BY v.user_id, v.display_name
        '''),
        {"vid": vid},
    )
    r = result.first()
    if not r or r[2] == 0:
        return None
    uid, name = r[0], r[1] or "Unknown"
    
    # We will compute the average penalty across all temperature buckets for this summary.
    # The view groups by temp and state. For a simple text summary, we can just take the averages:
    result_avg = await session.execute(
        text('''
            SELECT hvac_state, SUM(trip_count) as trips, 
                   ROUND(SUM(avg_consumption_kwh_100km * trip_count) / SUM(trip_count), 2) as avg_cost
            FROM v_climate_penalty_breakdown
            WHERE user_vehicle_id = :vid
            GROUP BY hvac_state
        '''),
        {"vid": vid},
    )
    rows = result_avg.fetchall()
    
    state_costs = {}
    total_trips = 0
    for row in rows:
        state_costs[row[0]] = (row[1], row[2]) # trips, avg_cost
        total_trips += row[1]
    
    if not state_costs:
        return None
        
    baseline = state_costs.get("OFF", (0, None))[1]
    baseline_trips = state_costs.get("OFF", (0, None))[0]
    heating = state_costs.get("HEATING", (0, None))[1]
    heating_trips = state_costs.get("HEATING", (0, None))[0]
    cooling = state_costs.get("COOLING", (0, None))[1]
    cooling_trips = state_costs.get("COOLING", (0, None))[0]
    
    parts = [f"Climate penalty data for {name}: {total_trips} trips analyzed."]
    if baseline is not None:
        parts.append(f"Baseline consumption (Climate OFF) is {baseline} kWh/100km over {baseline_trips} trips.")
    if heating is not None and baseline is not None:
        penalty = round(heating - baseline, 2)
        parts.append(f"Heating consumption is {heating} kWh/100km over {heating_trips} trips (Heating Penalty: {penalty} kWh/100km).")
    if cooling is not None and baseline is not None:
        penalty = round(cooling - baseline, 2)
        parts.append(f"Cooling consumption is {cooling} kWh/100km over {cooling_trips} trips (Cooling Penalty: {penalty} kWh/100km).")
        
    chunk = " ".join(parts)
    meta = {"source": "Climate Penalty Breakdown", "vehicle_name": name}
    return chunk, meta

def parse_queue_content_id(content_id: str) -> tuple[str, str]:
    """Parse '<prefix>:<vehicle_id>' into (prefix, vehicle_id)."""
    if ":" in content_id:
        prefix, vid = content_id.split(":", 1)
        return prefix, vid
    return "", content_id
