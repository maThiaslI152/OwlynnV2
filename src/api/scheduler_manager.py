import logging
import os
from typing import Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Use PostgreSQL for the job store to keep all state in one place.
# Falls back to SQLite if DATABASE_URL is not set (tests / local dev without Postgres).
_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/jobs.sqlite")
# APScheduler requires a synchronous URL — strip the async driver prefix if present
_JOBSTORE_URL = _DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://").replace(
    "sqlite+aiosqlite://", "sqlite://"
)


class JobScheduler:
    _instance: Optional["JobScheduler"] = None

    def __init__(self):
        jobstores = {"default": SQLAlchemyJobStore(url=_JOBSTORE_URL)}
        executors = {
            "default": ThreadPoolExecutor(10),
        }
        job_defaults = {"coalesce": False, "max_instances": 1}
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores, executors=executors, job_defaults=job_defaults
        )

    @classmethod
    def get_instance(cls) -> "JobScheduler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("APScheduler started (jobstore: %s).", _JOBSTORE_URL.split("@")[-1])

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("APScheduler shut down.")


scheduler_manager = JobScheduler.get_instance()
