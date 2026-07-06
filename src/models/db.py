import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Get DATABASE_URL from env, default to an sqlite in-memory for tests/dev if missing,
# but our docker-compose sets it to postgresql+asyncpg
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

if DATABASE_URL.endswith(":memory:"):
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
elif "sqlite" in DATABASE_URL:
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session
