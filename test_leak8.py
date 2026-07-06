import asyncio, os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from src.models.db import engine
print("Engine URL is:", engine.url)
