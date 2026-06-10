import re

with open("backend/app/services/embedding_builders.py", "r") as f:
    content = f.read()

new_builder = """
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

def parse_queue_content_id"""

content = content.replace("def parse_queue_content_id", new_builder)

with open("backend/app/services/embedding_builders.py", "w") as f:
    f.write(content)
