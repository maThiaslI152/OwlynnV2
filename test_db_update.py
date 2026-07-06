import asyncio
from src.memory.project import ProjectManager

async def run():
    pm = ProjectManager()
    await pm.update_chat_in_project("zz_fake_", "some-chat-id", name="x")
    print("Success")

asyncio.run(run())
