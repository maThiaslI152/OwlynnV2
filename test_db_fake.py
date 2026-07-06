import asyncio
from src.memory.project import ProjectManager
from src.models.db import AsyncSessionLocal, engine
from src.models.project import Base, Chat
from sqlalchemy import select

async def run():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    pm = ProjectManager()
    await pm.add_chat_to_project(
        "zz_fake_", {"id": "test_id", "name": "test_name", "created_at": 0}
    )
    
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(Chat).filter_by(id="test_id"))
        print("After insert:", existing.scalars().all())

    await pm.delete_chat_from_project("zz_fake_", "test_id")
    
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(Chat).filter_by(id="test_id"))
        print("After delete:", existing.scalars().all())

asyncio.run(run())
