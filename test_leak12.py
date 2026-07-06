import asyncio, os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
from src.memory.project import ProjectManager
from src.models.db import AsyncSessionLocal, engine
from src.models.project import Base, Chat

async def run():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    pm = ProjectManager()
    
    chat_info = {"id": "0000", "name": "test_name", "created_at": 0}
    project_id = "my_custom_id"
    
    # Simulate add_chat_to_project EXACTLY as it is written
    chat = Chat(
        id=chat_info["id"],
        project_id=project_id,
        name=chat_info["name"],
        created_at=chat_info["created_at"]
    )
    
    print("Chat BEFORE insert:", chat.id, chat.project_id)
    
    async with AsyncSessionLocal() as session:
        session.add(chat)
        await session.commit()
    
    print("Chat AFTER insert:", chat.id, chat.project_id)

asyncio.run(run())
