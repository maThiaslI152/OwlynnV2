import asyncio, os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
from src.models.db import AsyncSessionLocal, engine
from src.models.project import Base, Chat
from sqlalchemy import select

async def run():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(Chat))
        chats = existing.scalars().all()
        for c in chats:
            print(f"Chat: id={c.id}, name={c.name}, pid={c.project_id}")

asyncio.run(run())
