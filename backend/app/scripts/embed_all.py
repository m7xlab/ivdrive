#!/usr/bin/env python3
"""
embed_all.py — Backfill all missing AI content types.

Usage:
    cd backend && poetry run python -m app.scripts.embed_all

Content types generated:
    vehicle_summary           — one doc per vehicle (make/model/year/specs)
    battery_health_summary    — latest SOH record per vehicle
    charging_curve_summary    — aggregated charging curve data per vehicle
    vehicle_state_summary     — aggregated door/window/light state per vehicle
    drive_consumption_summary — consumption stats per vehicle
    charging_session_summary  — aggregated charging stats per vehicle
    climate_penalty_summary   — aggregated HVAC heating/cooling penalties per vehicle

Existing (not re-generated):
    trip_summary, charging_event, location — already populated
"""
import asyncio
import hashlib
import json
import logging
import os
import uuid
import re
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

ENGINE = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=6)
AsyncSession = async_sessionmaker(ENGINE, expire_on_commit=False)

EMBEDDING_DIM = 768  # gemini-embedding-001 @ 768 (Matryoshka)
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini-embedding-001").lower()
BATCH_SIZE = 20


async def text_to_embedding(text: str, seed: int = 42) -> list[float]:
    """
    Dispatch to the configured embedding provider.
    Primary: gemini-embedding-001 (semantic, multilingual).
    Fallback: deterministic hash.
    """
    from app.services.ai_embeddings import generate_embedding, text_to_deterministic_embedding
    result = await generate_embedding(text)
    if result is not None:
        return result
    return text_to_deterministic_embedding(text, seed=seed)


def emb_str(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


async def upsert_embedding(
    session, user_id: str, vehicle_id: str | None,
    content_type: str, content_id: str, chunk: str,
    embedding: list[float], metadata: dict | None = None,
):
    ch = content_hash(chunk)
    emb = emb_str(embedding)
    meta_json = json.dumps(metadata) if metadata else None
    await session.execute(
        text("""
            INSERT INTO ai_embeddings
              (id, user_id, vehicle_id, content_type, content_id, content_hash,
               chunk_index, content_chunk, embedding, extra_metadata,
               embedding_provider, embedding_model,
               created_at, updated_at)
            VALUES
              (gen_random_uuid(), :user_id, :vehicle_id, :content_type, :content_id,
               :content_hash, 0, :chunk, CAST(:embedding AS vector(768)), :metadata,
               :provider, :model,
               NOW(), NOW())
            ON CONFLICT (content_type, content_id, chunk_index)
            DO UPDATE SET
              content_chunk = EXCLUDED.content_chunk,
              embedding = EXCLUDED.embedding,
              content_hash = EXCLUDED.content_hash,
              extra_metadata = EXCLUDED.extra_metadata,
              embedding_provider = EXCLUDED.embedding_provider,
              embedding_model = EXCLUDED.embedding_model,
              updated_at = NOW()
        """),
        {"user_id": user_id, "vehicle_id": vehicle_id, "content_type": content_type,
         "content_id": content_id, "content_hash": ch, "chunk": chunk,
         "embedding": emb, "metadata": meta_json,
         "provider": EMBEDDING_PROVIDER,
         "model": f"gemini-embedding-001@{EMBEDDING_DIM}"},
    )


async def embed_vehicle_summaries(session) -> int:
    logger.info("Embedding vehicle_summaries...")
    result = await session.execute(text("""
        SELECT id, user_id, display_name, manufacturer, model, model_year,
               body_type, trim_level, exterior_colour, battery_capacity_kwh,
               max_charging_power_kw, engine_power_kw, wltp_range_km,
               active_interval_seconds, parked_interval_seconds,
               charger_power_kw, ice_l_per_100km,
               uphill_kwh_per_100km_per_100m, downhill_kwh_per_100km_per_100m,
               speed_city_threshold_kmh, speed_highway_threshold_kmh,
               temp_cold_max_celsius, temp_optimal_min_celsius, temp_optimal_max_celsius
        FROM user_vehicles WHERE user_id IS NOT NULL
    """))
    rows = result.fetchall()
    count = 0
    for r in rows:
        vid, uid = str(r[0]), str(r[1])
        name, year = r[2] or "Unknown", r[4] or "?"
        body, trim, colour = r[6] or "?", r[7] or "", r[8] or ""
        batt, max_charge, power = r[9], r[10], r[11]
        wltp = r[12]
        charger_kw = r[15]
        ice = r[16]
        uphill, downhill = r[17], r[18]
        city_th, highway_th = r[19], r[20]
        cold_max, opt_min, opt_max = r[21], r[22], r[23]

        specs = []
        if batt: specs.append(f"{batt:.0f}kWh battery")
        if power: specs.append(f"{power}kW engine")
        if max_charge: specs.append(f"{max_charge}kW max charging")
        if wltp: specs.append(f"{wltp:.0f}km WLTP range")
        if charger_kw: specs.append(f"{charger_kw}kW home charger")
        if city_th and highway_th: specs.append(f"City <= {city_th:.0f}km/h, Highway <= {highway_th:.0f}km/h")
        if cold_max and opt_min and opt_max: specs.append(f"Optimal temp {opt_min:.0f}-{opt_max:.0f}C, cold max {cold_max:.0f}C")
        if uphill and downhill: specs.append(f"Uphill +{uphill:.2f}, downhill {downhill:.2f} kWh/100km/100m")
        if ice: specs.append(f"{ice}L/100km ICE consumption")
        specs_str = " | ".join(specs) if specs else "No specifications available"

        chunk = (f"Vehicle: {name} | {year} {r[3]} {r[2]} {trim} | {body} body | {colour} | {specs_str}")
        emb = await text_to_embedding(chunk)
        meta = {"source": "Vehicle Info", "vehicle_name": name, "year": year,
                "make": r[3], "model": r[2], "battery_kwh": batt, "power_kw": power}
        await upsert_embedding(session, uid, vid, "vehicle_summary", f"vehicle:{vid}", chunk, emb, meta)
        count += 1
    logger.info(f"  -> {count} vehicle_summary docs embedded")
    return count


async def embed_battery_health_summaries(session) -> int:
    logger.info("Embedding battery_health_summary...")
    result = await session.execute(text("""
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
            ORDER BY bh.user_vehicle_id, bh.captured_at DESC
        )
        SELECT * FROM latest
    """))
    rows = result.fetchall()
    count = 0
    for r in rows:
        vid, uid, name = str(r[0]), str(r[1]), r[2] or "Unknown"
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
        emb = await text_to_embedding(chunk)
        meta = {"source": "Battery Health", "vehicle_name": name, "soh": r[4], "captured_at": captured}
        await upsert_embedding(session, uid, vid, "battery_health_summary", f"battery:{vid}", chunk, emb, meta)
        count += 1
    logger.info(f"  -> {count} battery_health_summary docs embedded")
    return count


async def embed_charging_curve_summaries(session) -> int:
    logger.info("Embedding charging_curve_summary...")
    result = await session.execute(text("""
        SELECT
            cc.user_vehicle_id, v.user_id, v.display_name,
            COUNT(*) as pt_count, COUNT(DISTINCT cc.session_id) as sess_count,
            MIN(cc.captured_at) as first_cap, MAX(cc.captured_at) as last_cap,
            MAX(cc.power_kw) as max_pow, AVG(cc.power_kw) as avg_pow,
            MIN(cc.battery_temp_celsius) as min_t, MAX(cc.battery_temp_celsius) as max_t,
            AVG(cc.battery_temp_celsius) as avg_t,
            MIN(cc.soc_pct) as min_soc, MAX(cc.soc_pct) as max_soc,
            AVG(cc.current_a) as avg_curr
        FROM charging_curves cc
        JOIN user_vehicles v ON v.id = cc.user_vehicle_id
        GROUP BY cc.user_vehicle_id, v.user_id, v.display_name HAVING COUNT(*) > 0
    """))
    rows = result.fetchall()
    count = 0
    for r in rows:
        vid, uid, name = str(r[0]), str(r[1]), r[2] or "Unknown"
        first_s = r[5].strftime("%Y-%m-%d") if r[5] else "?"
        last_s = r[6].strftime("%Y-%m-%d") if r[6] else "?"
        chunk = (f"Charging curve data for {name}: {r[3]} data points across {r[4]} sessions "
                 f"({first_s} - {last_s}). Peak {r[7]:.1f}kW, avg {r[8]:.1f}kW. "
                 f"SOC range {r[12]:.0f}%-{r[13]:.0f}%. "
                 f"Battery temp range {r[9]:.1f}-{r[10]:.1f}C (avg {r[11]:.1f}C). Avg current {r[14]:.1f}A.")
        emb = await text_to_embedding(chunk)
        meta = {"source": "Charging Curves", "vehicle_name": name,
                "sessions": r[4], "max_power_kw": r[7], "avg_power_kw": r[8]}
        await upsert_embedding(session, uid, vid, "charging_curve_summary", f"curve:{vid}", chunk, emb, meta)
        count += 1
    logger.info(f"  -> {count} charging_curve_summary docs embedded")
    return count


async def embed_vehicle_state_summaries(session) -> int:
    logger.info("Embedding vehicle_state_summary...")
    result = await session.execute(text("""
        WITH recent AS (
            SELECT DISTINCT ON (vs.user_vehicle_id)
                   vs.user_vehicle_id, v.user_id, v.display_name,
                   vs.state, vs.doors_locked, vs.doors_open, vs.windows_open,
                   vs.lights_on, vs.trunk_open, vs.bonnet_open, vs.last_date
            FROM vehicle_states vs
            JOIN user_vehicles v ON v.id = vs.user_vehicle_id
            ORDER BY vs.user_vehicle_id, vs.last_date DESC
        ),
        state_dur AS (
            SELECT user_vehicle_id, state,
                   COUNT(*) as state_count,
                   SUM(EXTRACT(EPOCH FROM (last_date - first_date))) as total_seconds
            FROM vehicle_states
            WHERE first_date > NOW() - INTERVAL '30 days'
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
        ORDER BY r.user_vehicle_id, r.rn
    """))
    rows = result.fetchall()
    vehicle_data: dict = {}
    for r in rows:
        vid = str(r[0])
        if vid not in vehicle_data:
            vehicle_data[vid] = {
                "uid": str(r[1]), "name": r[2] or "Unknown",
                "top_states": [], "current_state": r[6],
                "doors_locked": r[7], "doors_open": r[8],
                "windows_open": r[9], "lights_on": r[10],
                "trunk_open": r[11], "bonnet_open": r[12], "last_date": r[13],
            }
        if r[4]:
            vehicle_data[vid]["top_states"].append(f"{r[4]} ({r[5]:.1f}h)")
    count = 0
    for vid, d in vehicle_data.items():
        states_str = "; ".join(d["top_states"]) if d["top_states"] else "No recent data"
        last_str = d["last_date"].strftime("%Y-%m-%d %H:%M") if d["last_date"] else "?"
        chunk = (f"Vehicle state summary for {d['name']} (last update {last_str}): "
                 f"Current state: {d['current_state'] or 'unknown'}. "
                 f"Doors: locked={d['doors_locked']}, open={d['doors_open'] or 'none'}. "
                 f"Windows: {d['windows_open'] or 'all closed'}. "
                 f"Lights: {d['lights_on'] or 'off'}. "
                 f"Trunk: {'open' if d['trunk_open'] else 'closed'}. "
                 f"Bonnet: {'open' if d['bonnet_open'] else 'closed'}. "
                 f"Top states last 30 days: {states_str}.")
        emb = await text_to_embedding(chunk)
        meta = {"source": "Vehicle State", "vehicle_name": d["name"], "current_state": d["current_state"]}
        await upsert_embedding(session, d["uid"], vid, "vehicle_state_summary", f"vstate:{vid}", chunk, emb, meta)
        count += 1
    logger.info(f"  -> {count} vehicle_state_summary docs embedded")
    return count


async def embed_drive_consumption_summaries(session) -> int:
    logger.info("Embedding drive_consumption_summary...")
    # drive_consumptions has drive_id -> drives.user_vehicle_id
    result = await session.execute(text("""
        SELECT dr.user_vehicle_id, v.user_id, v.display_name,
               COUNT(*) as rec_count, AVG(d.consumption) as avg_cons,
               MIN(d.consumption) as min_cons, MAX(d.consumption) as max_cons,
               AVG(d.temperature_celsius) as avg_t, MIN(d.temperature_celsius) as min_t,
               MAX(d.temperature_celsius) as max_t,
               MIN(d.first_date) as first_rec, MAX(d.last_date) as last_rec
        FROM drive_consumptions d
        JOIN drives dr ON dr.id = d.drive_id
        JOIN user_vehicles v ON v.id = dr.user_vehicle_id
        GROUP BY dr.user_vehicle_id, v.user_id, v.display_name HAVING COUNT(*) > 0
    """))
    rows = result.fetchall()
    count = 0
    for r in rows:
        vid, uid, name = str(r[0]), str(r[1]), r[2] or "Unknown"
        first_s = r[10].strftime("%Y-%m-%d") if r[10] else "?"
        last_s = r[11].strftime("%Y-%m-%d") if r[11] else "?"
        chunk = (f"Drive consumption for {name}: {r[3]} records ({first_s} - {last_s}). "
                 f"Average consumption {r[4]:.2f}kWh/100km (range {r[5]:.2f}-{r[6]:.2f}). "
                 f"Average ambient temp {r[7]:.1f}C (range {r[8]:.1f}-{r[9]:.1f}C).")
        emb = await text_to_embedding(chunk)
        meta = {"source": "Drive Consumption", "vehicle_name": name,
                "avg_consumption": r[4], "record_count": r[3]}
        await upsert_embedding(session, uid, vid, "drive_consumption_summary", f"drive:{vid}", chunk, emb, meta)
        count += 1
    logger.info(f"  -> {count} drive_consumption_summary docs embedded")
    return count


async def embed_charging_sessions_summaries(session) -> int:
    logger.info("Embedding charging_session_summary...")
    result = await session.execute(text("""
        SELECT
            cs.user_vehicle_id, v.user_id, v.display_name,
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
        GROUP BY cs.user_vehicle_id, v.user_id, v.display_name HAVING COUNT(*) > 0
    """))
    rows = result.fetchall()
    count = 0
    for r in rows:
        vid, uid, name = str(r[0]), str(r[1]), r[2] or "Unknown"
        first_s = r[10].strftime("%Y-%m-%d") if r[10] else "?"
        last_s = r[11].strftime("%Y-%m-%d") if r[11] else "?"
        chunk = (f"Charging summary for {name}: {r[3]} sessions total, {r[4]:.1f}kWh energy, "
                 f"EUR {r[6]:.2f} total cost. Avg per session: {r[5]:.1f}kWh, EUR {r[7]:.2f}. "
                 f"{r[8]} DC, {r[9]} AC sessions. Period: {first_s} - {last_s}. "
                 f"Avg ambient temp: {r[12]:.1f}C.")
        emb = await text_to_embedding(chunk)
        meta = {"source": "Charging Summary", "vehicle_name": name,
                "session_count": r[3], "total_cost": r[6]}
        await upsert_embedding(session, uid, vid, "charging_session_summary", f"charge_summary:{vid}", chunk, emb, meta)
        count += 1
    logger.info(f"  -> {count} charging_session_summary docs embedded")
    return count


async def embed_climate_penalty_summaries(session) -> int:
    logger.info("Embedding climate_penalty_summary...")
    result = await session.execute(text("SELECT id, user_id, display_name FROM user_vehicles WHERE user_id IS NOT NULL"))
    vehicles = result.fetchall()
    
    # Import the builder function we just created
    from app.services.embedding_builders import build_climate_penalty_summary
    
    count = 0
    for v in vehicles:
        vid, uid, name = str(v[0]), str(v[1]), v[2] or "Unknown"
        res = await build_climate_penalty_summary(session, vid)
        if res:
            chunk, meta = res
            emb = await text_to_embedding(chunk)
            await upsert_embedding(session, uid, vid, "climate_penalty_summary", f"climate_penalty:{vid}", chunk, emb, meta)
            count += 1
            
    logger.info(f"  -> {count} climate_penalty_summary docs embedded")
    return count

async def run():
    logger.info("Starting embed_all — backfilling all missing content types")
    async with AsyncSession() as session:
        n1 = await embed_vehicle_summaries(session)
        await session.commit()
        n2 = await embed_battery_health_summaries(session)
        await session.commit()
        n3 = await embed_charging_curve_summaries(session)
        await session.commit()
        n4 = await embed_vehicle_state_summaries(session)
        await session.commit()
        n5 = await embed_drive_consumption_summaries(session)
        await session.commit()
        n6 = await embed_charging_sessions_summaries(session)
        await session.commit()
        n7 = await embed_climate_penalty_summaries(session)
        await session.commit()
        logger.info(f"Done. vehicle={n1}, battery={n2}, curve={n3}, vstate={n4}, drive={n5}, charge_summary={n6}, climate_penalty={n7}")
        result = await session.execute(text("SELECT content_type, COUNT(*) FROM ai_embeddings GROUP BY content_type ORDER BY content_type"))
        logger.info("Embedding counts:")
        for row in result.fetchall():
            logger.info(f"  {row[0]}: {row[1]}")
    await ENGINE.dispose()


if __name__ == "__main__":
    asyncio.run(run())