import asyncio, os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
from src.memory.project import ProjectManager
from src.models.db import AsyncSessionLocal, engine
from src.models.project import Base, Chat

async def run():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    chat = Chat(
        id="0000",
        project_id="my_custom_id",
        name="test_name",
        created_at=0
    )
    
    async with AsyncSessionLocal() as session:
        session.add(chat)
        await session.commit()
    
    print("SUCCESS")

asyncio.run(run())
