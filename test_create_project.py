import asyncio
from src.memory.project import project_manager


async def test():
    try:
        res = await project_manager.create_project("test")
        print("Success:", res)
    except Exception as e:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
