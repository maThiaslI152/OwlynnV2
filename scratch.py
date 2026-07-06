import asyncio
from src.models.db import engine, DATABASE_URL
from src.models.base import Base


async def main():
    print("DATABASE_URL:", DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created.")

    # Try querying
    from sqlalchemy import select, text

    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table';")
        )
        print("Tables:", res.fetchall())


asyncio.run(main())
