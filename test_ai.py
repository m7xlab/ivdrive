import asyncio
from uuid import UUID
from app.database import async_session
from app.services.ai_embeddings import search_similar

async def run():
    async with async_session() as db:
        # BlackMagic vehicle UUID: 023b3fdc-40a8-457b-a3c6-d671a3b7168f
        # User UUID: 98003d25-18a0-42e0-a1cf-55cd3cb8a9ad
        results = await search_similar(
            db,
            user_id=UUID("98003d25-18a0-42e0-a1cf-55cd3cb8a9ad"),
            query="climate penalty",
            vehicle_id=UUID("023b3fdc-40a8-457b-a3c6-d671a3b7168f"),
            limit=3
        )
        for r in results:
            print(f"[{r['content_type']}] score={r['similarity']:.2f}")
            print(r['chunk'])
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(run())
