import asyncio
import logging
from src.config.settings import normalize_project_id
from src.tools.workspace_context import (
    set_active_project_for_run,
    reset_active_project,
    set_active_scenario_for_run,
    reset_active_scenario,
)
from src.config.audit_log import set_thread_id

logger = logging.getLogger(__name__)


class GraphSession:
    """Manages the graph execution for a specific thread in a background task."""

    def __init__(self, thread_id, agent, sessions_registry):
        self.thread_id = thread_id
        self.agent = agent
        self.sessions_registry = sessions_registry
        self.listeners = set()  # asyncio.Queues
        self.task = None
        self.event_buffer = []  # Store all events for the current turn
        self.is_running = False
        self.last_project_id = "default"
        self.last_scenario_id = None
        self._run_queue = asyncio.Queue()
        self._queue_processor = asyncio.create_task(self._process_queue())

    async def _process_queue(self):
        while True:
            try:
                input_data, config, correlation_id = await self._run_queue.get()
                self.is_running = True
                self.event_buffer = []
                self.task = asyncio.current_task()
                try:
                    await self._execute(input_data, config, correlation_id)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error("Error in queued run: %s", e, exc_info=True)
                finally:
                    self.is_running = False
                    self._run_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in queue processor: %s", e, exc_info=True)

    async def add_listener(self):
        q = asyncio.Queue()
        self.listeners.add(q)
        # Replay all events of the current turn to catch up
        for event in self.event_buffer:
            await q.put(event)
        return q

    def remove_listener(self, q: asyncio.Queue):
        self.listeners.discard(q)

    def is_active(self):
        return self.is_running or len(self.listeners) > 0 or not self._run_queue.empty()

    async def start_run(self, input_data, config, correlation_id=None):
        if isinstance(input_data, dict):
            pid = input_data.get("project_id")
            if pid is not None:
                self.last_project_id = normalize_project_id(pid)
            sid = input_data.get("scenario_id")
            if sid is not None:
                self.last_scenario_id = str(sid).strip() or None
        await self._run_queue.put((input_data, config, correlation_id))

    async def _execute(self, input_data, config, correlation_id=None):
        # Propagate thread_id into audit context for this graph run
        set_thread_id(self.thread_id)

        from src.agent.local_llm_scheduler import LocalLLMScheduler

        LocalLLMScheduler.graph_run_started()
        token = set_active_project_for_run(self.last_project_id)
        scenario_token = set_active_scenario_for_run(self.last_scenario_id)
        try:
            # Initial status
            start_msg = {"type": "status", "content": "reasoning"}
            self.event_buffer.append((start_msg, correlation_id))
            for q in list(self.listeners):
                await q.put((start_msg, correlation_id))

            async for event in self.agent.astream_events(
                input_data, config=config, version="v2"
            ):
                self.event_buffer.append((event, correlation_id))
                if len(self.event_buffer) > 2000:
                    self.event_buffer.pop(0)
                # Broadcast
                for q in list(self.listeners):
                    await q.put((event, correlation_id))
        except asyncio.CancelledError:
            logger.info("GraphExecution cancelled for thread %s", self.thread_id)
            err_msg = {"type": "status", "content": "stopped"}
            self.event_buffer.append((err_msg, correlation_id))
            for q in list(self.listeners):
                q.put_nowait((err_msg, correlation_id))
            raise
        except Exception as e:
            logger.error(
                "Graph execution error for thread %s: %s",
                self.thread_id,
                e,
                exc_info=True,
            )
            err_msg = {"type": "error", "content": f"Graph Execution Error: {str(e)}"}
            self.event_buffer.append((err_msg, correlation_id))
            for q in list(self.listeners):
                await q.put((err_msg, correlation_id))
        finally:
            LocalLLMScheduler.graph_run_finished()
            reset_active_project(token)
            reset_active_scenario(scenario_token)
            self.is_running = False

            # Verify checkpoint was persisted (non-blocking)
            try:
                from src.config.settings import REDIS_URL
                import redis.asyncio as aioredis

                async def _check_checkpoint():
                    client = aioredis.from_url(REDIS_URL)
                    count = 0
                    async for _ in client.scan_iter(
                        match=f"checkpoint:{self.thread_id}:*", count=10
                    ):
                        count += 1
                        if count > 0:
                            break
                    await client.aclose()
                    if count == 0:
                        logger.warning(
                            "No checkpoint found for thread %s after graph run — "
                            "history may not persist across restarts",
                            self.thread_id,
                        )

                import asyncio as _asyncio

                _asyncio.ensure_future(_check_checkpoint())
            except Exception:
                pass  # best-effort, non-critical

            # Final status update
            done_msg = {"type": "status", "content": "idle"}
            logger.debug(
                "GraphSession._execute for thread %s FINISHED. Putting done_msg.",
                self.thread_id,
            )
            self.event_buffer.append((done_msg, correlation_id))
            for q in list(self.listeners):
                q.put_nowait((done_msg, correlation_id))

            # If no one is listening anymore, remove from registry
            if not self.listeners and self.thread_id in self.sessions_registry:
                del self.sessions_registry[self.thread_id]
