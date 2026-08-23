import asyncio
import logging
import time
from pathlib import Path

from src.config.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


def _resolve_trace_dir() -> Path:
    raw = ConfigLoader.get("trace.output_dir", "~/.owlynn/traces")
    return Path(raw).expanduser().resolve()


async def trace_pruner_task(interval_hours: int = 24, max_age_days: int = 30):
    """Background task to delete old trace files in ~/.owlynn/traces."""
    trace_dir = _resolve_trace_dir()
    logger.info("Trace pruner started. max_age_days=%d", max_age_days)
    while True:
        try:
            if trace_dir.exists():
                now = time.time()
                cutoff = now - (max_age_days * 86400)
                count = 0
                for file_path in trace_dir.glob("*.jsonl"):
                    try:
                        if file_path.stat().st_mtime < cutoff:
                            file_path.unlink()
                            count += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to prune trace file %s: %s", file_path, e
                        )
                if count > 0:
                    logger.info("Pruned %d old trace files.", count)
        except Exception as e:
            logger.error("Trace pruner encountered an error: %s", e)

        await asyncio.sleep(interval_hours * 3600)


async def start_trace_pruner():
    import asyncio

    task = asyncio.create_task(trace_pruner_task())
    return task
