import asyncio, os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
from src.models.db import AsyncSessionLocal, engine
from src.models.project import Base, Chat
from sqlalchemy import select

async def run():
    print("Engine URL:", engine.url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(Chat))
        print("Total chats in DB:", len(existing.scalars().all()))

asyncio.run(run())
