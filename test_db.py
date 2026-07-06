import asyncio
from src.memory.project import project_manager

async def run():
    print(await project_manager.list_projects())

asyncio.run(run())
