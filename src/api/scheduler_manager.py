import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class JobScheduler:
    _instance: Optional["JobScheduler"] = None

    def __init__(self):
        # Using SQLite for the jobstore to persist jobs across restarts.
        import os

        os.makedirs("data", exist_ok=True)
        jobstores = {"default": SQLAlchemyJobStore(url="sqlite:///data/jobs.sqlite")}
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
            logger.info("APScheduler started.")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("APScheduler shut down.")


scheduler_manager = JobScheduler.get_instance()
