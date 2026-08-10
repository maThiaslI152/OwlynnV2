import logging
from typing import Optional

from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.models.db import DATABASE_URL

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[AsyncConnectionPool] = None


def _get_psycopg_url() -> str:
    """Converts the asyncpg SQLAlchemy URL to a standard psycopg URL."""
    # DATABASE_URL typically looks like postgresql+asyncpg://user:pass@host:port/db
    if DATABASE_URL.startswith("postgresql+asyncpg://"):
        return DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    return DATABASE_URL


def _get_pool() -> AsyncConnectionPool:
    """Returns the global connection pool, initializing it if necessary."""
    global _pool
    if _pool is None:
        url = _get_psycopg_url()
        _pool = AsyncConnectionPool(
            conninfo=url,
            kwargs={"autocommit": True, "row_factory": dict_row},
            max_size=20,
        )
    return _pool


async def get_postgres_saver() -> AsyncPostgresSaver:
    """
    Returns an initialized AsyncPostgresSaver.
    Ensures that the connection pool is open and the .setup() tables are created.
    """
    pool = _get_pool()
    checkpointer = AsyncPostgresSaver(pool)

    try:
        # LangGraph requires setup to be called once to create the checkpoints tables
        await checkpointer.setup()
    except Exception as e:
        logger.error("Failed to setup Postgres checkpointer tables: %s", e)
        raise

    return checkpointer
