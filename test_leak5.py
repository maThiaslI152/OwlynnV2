import asyncio, os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from src.memory.project import ProjectManager
from src.models.db import AsyncSessionLocal, engine
from src.models.project import Base, Chat
from sqlalchemy import select

async def run():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    pm = ProjectManager()
    await pm.add_chat_to_project(
        "zz_fake_", {"id": "0000", "name": "test_name", "created_at": 0}
    )
    
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(Chat).filter_by(id="0000"))
        print("After insert:", len(existing.scalars().all()))

    await pm.delete_chat_from_project("zz_fake_", "0000")
    
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(Chat).filter_by(id="0000"))
        print("After delete:", len(existing.scalars().all()))

asyncio.run(run())
