import asyncio
from src.memory.project import ProjectManager
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from src.models.db import AsyncSessionLocal
from src.models.project import Chat
import time

async def test_add(pm, pid, chat_id):
    chat_info = {'id': chat_id, 'name': '000', 'created_at': 1000000000}
    try:
        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(Chat).filter_by(id=chat_id))
            if existing.scalars().first():
                print(f"Chat {chat_id} already exists!")
                return
            chat = Chat(
                id=chat_id,
                project_id=pid,
                name=chat_info.get("name", "New Chat"),
                created_at=chat_info.get("created_at", time.time()),
            )
            session.add(chat)
            await session.commit()
            print(f"Chat {chat_id} committed successfully!")
    except IntegrityError as e:
        print(f"IntegrityError for {chat_id}: {e}")
    except Exception as e:
        print(f"Other Error for {chat_id}: {e}")

async def run():
    pm = ProjectManager()
    await pm._ensure_default()
    
    proj_a = await pm.create_project("Project A")
    proj_b = await pm.create_project("Project B")
    
    await test_add(pm, proj_a["id"], '1w91')
    await test_add(pm, proj_b["id"], '0000')
    
    proj_b_after = await pm.get_project(proj_b["id"])
    print(f"Proj B chats: {proj_b_after['chats']}")

asyncio.run(run())
