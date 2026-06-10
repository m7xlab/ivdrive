import re

with open("backend/app/scripts/embed_all.py", "r") as f:
    content = f.read()

new_embedder = """async def embed_climate_penalty_summaries(session) -> int:
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
            emb = text_to_embedding(chunk)
            await upsert_embedding(session, uid, vid, "climate_penalty_summary", f"climate_penalty:{vid}", chunk, emb, meta)
            count += 1
            
    logger.info(f"  -> {count} climate_penalty_summary docs embedded")
    return count

async def run():"""

content = content.replace("async def run():", new_embedder)

new_run = """        n6 = await embed_charging_sessions_summaries(session)
        await session.commit()
        n7 = await embed_climate_penalty_summaries(session)
        await session.commit()
        logger.info(f"Done. vehicle={n1}, battery={n2}, curve={n3}, vstate={n4}, drive={n5}, charge_summary={n6}, climate_penalty={n7}")"""

old_run = """        n6 = await embed_charging_sessions_summaries(session)
        await session.commit()
        logger.info(f"Done. vehicle={n1}, battery={n2}, curve={n3}, vstate={n4}, drive={n5}, charge_summary={n6}")"""

content = content.replace(old_run, new_run)

# Also update docstring
content = content.replace("charging_session_summary  — aggregated charging stats per vehicle", "charging_session_summary  — aggregated charging stats per vehicle\n    climate_penalty_summary   — aggregated HVAC heating/cooling penalties per vehicle")

with open("backend/app/scripts/embed_all.py", "w") as f:
    f.write(content)
