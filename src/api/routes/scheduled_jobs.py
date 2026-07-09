from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import logging
from src.api.scheduler_manager import scheduler_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


class JobCreate(BaseModel):
    id: str
    cron_expression: str
    task_prompt: str
    tool_subsets: Optional[List[str]] = None


class JobResponse(BaseModel):
    id: str
    next_run_time: Optional[str]
    cron_expression: Optional[str]


async def execute_agent_job(task_prompt: str, tool_subsets: Optional[List[str]] = None):
    """Background task executed by APScheduler"""
    logger.info(f"Executing scheduled agent job with prompt: {task_prompt}")
    from src.agent.core.graph import build_graph

    # Set up basic agent state for a background run
    state = {
        "messages": [("user", task_prompt)],
        "mode": "api",
        "route": "complex-local",  # force local to avoid surprise cloud costs
        "selected_toolboxes": tool_subsets or ["all"],
        "scenario_id": "research",
    }
    graph = build_graph().compile()

    try:
        # Run graph without checking checkpoints to keep it isolated
        result = await graph.ainvoke(state)
        logger.info(
            f"Scheduled job completed. Agent response length: {len(result.get('messages', []))}"
        )
    except Exception as e:
        logger.error(f"Scheduled job failed: {e}")


@router.post("/", response_model=JobResponse)
async def create_job(job: JobCreate):
    from apscheduler.triggers.cron import CronTrigger

    try:
        trigger = CronTrigger.from_crontab(job.cron_expression)

        added_job = scheduler_manager.scheduler.add_job(
            execute_agent_job,
            trigger=trigger,
            id=job.id,
            replace_existing=True,
            kwargs={"task_prompt": job.task_prompt, "tool_subsets": job.tool_subsets},
        )

        return JobResponse(
            id=added_job.id,
            next_run_time=str(added_job.next_run_time)
            if added_job.next_run_time
            else None,
            cron_expression=job.cron_expression,
        )
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[JobResponse])
async def list_jobs():
    jobs = scheduler_manager.scheduler.get_jobs()
    return [
        JobResponse(
            id=job.id,
            next_run_time=str(job.next_run_time) if job.next_run_time else None,
            # Rough representation, actual cron str extraction requires inspecting the trigger
            cron_expression=str(job.trigger),
        )
        for job in jobs
    ]


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    try:
        scheduler_manager.scheduler.remove_job(job_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to delete job: {e}")
        raise HTTPException(status_code=404, detail="Job not found")
