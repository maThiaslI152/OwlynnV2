import asyncio, os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from src.memory.project import ProjectManager
from src.models.db import AsyncSessionLocal, engine
from src.models.project import Base, Chat
from sqlalchemy import select

async def run():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(Chat))
        print("All chats before insert:", existing.scalars().all())

asyncio.run(run())
