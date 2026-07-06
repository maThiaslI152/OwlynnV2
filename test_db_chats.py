import asyncio
from sqlalchemy import select
from src.models.db import AsyncSessionLocal
from src.models.project import Chat
from src.memory.project import project_manager

async def run():
    await project_manager._ensure_default()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Chat))
        chats = result.scalars().all()
        for c in chats:
            print(f"Chat ID: {c.id}, Project ID: {c.project_id}")

asyncio.run(run())
