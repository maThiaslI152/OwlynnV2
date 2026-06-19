"""
FastAPI Backend Server for Local Cowork Agent.

This module defines the API endpoints and WebSocket handlers for interacting
with the LangGraph agent, managing user profiles, and serving the frontend.
It supports streaming responses and handling multimodal file uploads.
"""

from src.api.routes import (
    profile,
    settings,
    memory,
    project,
    files,
    openai,
    browser_extension,
    study,
    notebook,
)
from src.api.ws import handler as ws_handler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException
from src.api.routes.files import notify_file_processed
from src.api.shared import _stringify_lc_message_content
import json
import asyncio
import os
from langchain_core.messages import HumanMessage

from src.agent.graph import init_agent
from src.agent.llm import LLMPool
from src.memory.user_profile import get_profile
from src.memory.project import project_manager
from src.memory.personal_assistant import (
    get_memory_context_for_prompt,
)
from src.config.settings import WORKSPACE_DIR
from src.api.file_processor import start_watcher

from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

from src.api.shared import _session_usage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize centralized logging
    from src.config.logging_config import setup_logging

    setup_logging()

    from src.api.local_auth import init_local_run_token

    init_local_run_token(app)

    # Preserve loop for async dispatchs from sync threads
    app.state.loop = asyncio.get_running_loop()

    # Initialize the LangGraph Agent Engine Singleton asynchronously
    app.state.agent = await init_agent()
    app.state.sessions = {}  # thread_id -> GraphSession

    # Preload router + embedding at startup; medium only when cloud unavailable.
    async def _preload_llms():
        if os.getenv("OWLYNN_NO_PRELOAD") == "1":
            return
        import asyncio as _asyncio

        from src.config.config_loader import config
        from src.config.secret_store import resolve_deepseek_api_key

        profile = get_profile()
        cloud_key = resolve_deepseek_api_key()
        cloud_on = bool(cloud_key) and profile.get("cloud_escalation_enabled", True)

        preload_slots = config.get("startup.preload") or ["small", "embedding"]
        warmup = bool(config.get("startup.warmup", True))

        # 1. Router (small) — always required
        try:
            await LLMPool.get_small_llm()
            logger.info("[startup] Small LLM client created")
        except Exception as e:
            logger.warning("[startup] Small LLM preload failed: %s", e)
            return

        # 2. Embedding — lightweight ping (no LM Studio model swap)
        if "embedding" in preload_slots:
            try:
                import httpx

                embed_url = config.get(
                    "models.embedding.base_url", "http://127.0.0.1:1234/v1"
                ).rstrip("/")
                embed_model = config.get(
                    "models.embedding.model_name",
                    "text-embedding-nomic-embed-text-v1.5-embedding",
                )
                timeout = float(config.get("models.embedding.timeout", 30.0))
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{embed_url}/embeddings",
                        json={"model": embed_model, "input": "warmup"},
                    )
                    resp.raise_for_status()
                logger.info("[startup] Embedding endpoint warmup complete")
            except Exception as e:
                logger.warning("[startup] Embedding warmup skipped: %s", e)

        # 3. Extraction (gemma-4-e2b) — always available for background work
        if "extraction" in preload_slots:
            try:
                await LLMPool.get_extraction_llm()
                logger.info("[startup] Extraction LLM client created")
            except Exception as e:
                logger.warning("[startup] Extraction LLM preload failed: %s", e)

        if warmup:
            await _asyncio.sleep(2)
            warmup_text = [HumanMessage(content="hi")]
            try:
                small_llm = await LLMPool.get_small_llm()
                await _asyncio.wait_for(
                    small_llm.ainvoke(warmup_text),
                    timeout=30,
                )
                logger.info("[startup] Small LLM warmup complete")
            except Exception as e:
                logger.warning("[startup] Small LLM warmup failed: %s", e)

        logger.info("[startup] LLM preload complete (cloud_on=%s)", cloud_on)

    await _preload_llms()
    app.state.llms_ready = True

    from src.memory.extraction.worker import (
        start_extraction_worker,
        stop_extraction_worker,
    )

    await start_extraction_worker()
    app.state.memory_extraction_worker = True

    from src.agent.nodes.complex_utils.vision_model_manager import (
        start_vision_manager,
        stop_vision_manager,
    )

    await start_vision_manager()
    app.state.vision_manager = True

    # Embedding models are pre-pulled manually via `ollama pull` or LM Studio UI.
    # The app relies on them being already available; no auto-load at startup.

    # Start background file watcher with WebSocket callback
    try:
        app.state.file_watcher = start_watcher(
            WORKSPACE_DIR, on_processed_callback=notify_file_processed
        )
    except Exception as e:
        logger.warning("Failed to start file watcher: %s", e)
        app.state.file_watcher = None

    yield
    if getattr(app.state, "memory_extraction_worker", False):
        await stop_extraction_worker()
    if getattr(app.state, "vision_manager", False):
        await stop_vision_manager()
    # Cleanup: cancel all background tasks
    if getattr(app.state, "file_watcher", None):
        try:
            app.state.file_watcher.stop()
            app.state.file_watcher.join()
        except Exception as e:
            logger.warning("Error suppressed: %s", e)
            pass

    for session in app.state.sessions.values():
        if session.task:
            session.task.cancel()


app = FastAPI(title="Local Cowork Agent API", lifespan=lifespan)

app.include_router(profile.router)
app.include_router(settings.router)
app.include_router(memory.router)
app.include_router(project.router)
app.include_router(files.router)
app.include_router(openai.router)
app.include_router(browser_extension.router)
app.include_router(study.router)
app.include_router(notebook.router)
app.include_router(ws_handler.router)

from src.api.local_auth import cors_allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Audit logging middleware (HTTP request logging)
from src.config.log_middleware import AuditLogMiddleware

app.add_middleware(AuditLogMiddleware)

# Serve frontend static files from frontend-v2 dist only.
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
FRONTEND_V2_DIST_DIR = os.path.join(_ROOT_DIR, "frontend-v2", "dist")
FRONTEND_DIR = FRONTEND_V2_DIST_DIR


@app.get("/")
async def serve_ui():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(
            status_code=503,
            detail="frontend-v2 build is missing (expected frontend-v2/dist/index.html)",
        )
    return FileResponse(index_path)


# Mount static roots for frontend assets.
app.mount(
    "/static", StaticFiles(directory=FRONTEND_DIR, check_dir=False), name="static"
)
_ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")
app.mount("/assets", StaticFiles(directory=_ASSETS_DIR, check_dir=False), name="assets")


@app.get("/script.js")
async def serve_script():
    raise HTTPException(
        status_code=410,
        detail="Legacy script.js endpoint retired; use frontend-v2 assets",
    )


@app.get("/style.css")
async def serve_style():
    raise HTTPException(
        status_code=410,
        detail="Legacy style.css endpoint retired; use frontend-v2 assets",
    )


@app.get("/vendor/{path:path}")
async def serve_vendor_retired(path: str):
    raise HTTPException(
        status_code=410,
        detail="Legacy vendor endpoint retired; use frontend-v2 bundled assets",
    )


# ─── REST API endpoints ──────────────────────────────────────────────────────

# Track cumulative session token usage
# (Imported from src.api.shared)

# Profile fields that require clearing cached LLM instances when changed


# Canonical websocket event envelope contract.
# Required minimum shapes emitted by this server:
# - status: {"type":"status","content":str}
# - chunk: {"type":"chunk","content":str}
# - message: {"type":"message","message":{"type":str,"content":str,...}}
# - tool_execution: {"type":"tool_execution","status":str,"tool_name":str,...}
# - model_info: {"type":"model_info","model":str,"swapping":bool}
# - interrupt: {"type":"interrupt","interrupts":list}
# - error: {"type":"error","content":str}
# - file_status: {"type":"file_status","name":str,"status":str}


@app.get("/api/usage")
async def api_get_usage():
    """Return cumulative cloud token usage and cost for the current session."""
    from src.agent.cloud_cost_tracker import build_cloud_usage_payload, get_cost_tracker
    from src.memory.user_profile import get_profile
    from src.config.config_loader import config

    tracker = get_cost_tracker()
    profile = get_profile()
    daily_limit = int(
        profile.get("cloud_daily_token_limit")
        or config.get("cloud.budget.daily_token_limit", 500_000)
    )
    payload = build_cloud_usage_payload()
    summary = tracker.summary()
    return {
        "session": {**summary, **_session_usage},
        "cost": summary,
        "budget": payload["budget"],
        "warning_thresholds": payload["warning_thresholds"],
        "last_turn": tracker.last_turn,
    }


@app.get("/api/cloud-status")
async def api_cloud_status():
    """Return cloud LLM connectivity status.

    Response::

        {
            "available": true,       // API reachable
            "key_valid": true,       // Key accepted (200 or 429)
            "model": "deepseek-v4",  // Configured model
            "error": ""              // Diagnostic message if false
        }
    """
    from src.agent.graph import _check_cloud_connectivity

    return await _check_cloud_connectivity()


@app.post("/api/cloud-verify-key")
async def api_cloud_verify_key(body: dict):
    """Verify a DeepSeek API key without persisting it.

    Request body: ``{"api_key": "sk-..."}``

    Response::

        {"valid": true, "message": "Key is valid"}
    """
    from src.config.secret_store import verify_deepseek_api_key

    api_key = (body.get("api_key") or "").strip()
    valid, message = verify_deepseek_api_key(api_key)
    return {"valid": valid, "message": message}


@app.get("/api/health")
async def api_health():
    """Check if the agent graph and LLMs are fully initialized."""
    agent_ready = False
    try:
        agent_ready = (
            hasattr(app, "state")
            and getattr(app.state, "agent", None) is not None
            and getattr(app.state, "llms_ready", False) is True
        )
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        pass

    return {"status": "ok", "agent": "ready" if agent_ready else "initializing"}


# ─── Dev API: HITL preview triggers ──────────────────────────────────────


@app.post("/api/dev/hitl/trigger")
async def api_dev_hitl_trigger(body: dict):
    """
    Dev-only endpoint to push a synthetic HITL interrupt over the active WS
    session for preview/demo purposes. Gated by OWLYNN_DEV=1 or debug flag.
    """
    import os

    dev_mode = os.environ.get("OWLYNN_DEV") == "1"
    if not dev_mode:
        profile = get_profile()
        dev_mode = profile.get("debug_mode", False)
    if not dev_mode:
        raise HTTPException(
            status_code=403,
            detail="Dev API requires OWLYNN_DEV=1 or debug_mode enabled in profile",
        )

    variant = (body.get("variant") or "router").strip()
    thread_id = body.get("thread_id")

    # Map variant to fixture name
    variant_map = {
        "router": "router_skill_ambiguity",
        "security": "security_delete_file",
        "plan_review": "plan_review_write_file",
        "scope_clarify": "scope_clarification_calculator",
        "ask_user": "ask_user_mid_task",
    }
    fixture_name = variant_map.get(variant, "router_skill_ambiguity")

    try:
        from src.hitl.fixtures import load_fixture

        fixture = load_fixture(fixture_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Try to push to active WS
    if thread_id and thread_id in app.state.sessions:
        session = app.state.sessions[thread_id]
        ws = getattr(session, "_ws", None)
        if ws:
            try:
                await ws.send_json({"type": "interrupt", "interrupts": [fixture]})
                return {"status": "pushed", "variant": variant, "fixture": fixture_name}
            except Exception as e:
                logger.warning("[dev_hitl] WS push failed: %s", e)

    # Return fixture JSON for inspection
    return {
        "status": "fixture_only",
        "variant": variant,
        "fixture_name": fixture_name,
        "payload": fixture,
    }


@app.get("/api/memory-context")
async def api_get_memory_context():
    """Get comprehensive memory context for UI display."""
    try:
        context = get_memory_context_for_prompt()
        return {
            "status": "ok",
            "memory_context": context,
        }
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return {"status": "error", "message": str(e)}


async def _auto_index_project_file(
    project_id: str, filename: str, filepath: str, file_bytes: bytes
):
    """
    Background task: extract text from an uploaded file and index it into
    the project's Qdrant knowledge base.
    """
    import asyncio

    from src.api.attachment_intake import is_vision_filename

    if is_vision_filename(filename):
        logger.info("Skipped auto-index for vision-only file %s", filename)
        return

    # Wait for file processor to finish
    await asyncio.sleep(3)

    text = ""
    ext = os.path.splitext(filename)[1].lower()

    try:
        # Try reading the processed cache — check both project-local and root workspace
        project_processed_dir = os.path.join(os.path.dirname(filepath), ".processed")
        root_processed_dir = os.path.join(
            os.path.abspath(str(WORKSPACE_DIR)), ".processed"
        )

        for pdir in [project_processed_dir, root_processed_dir]:
            if text:
                break
            for cache_ext in [".txt", ".md"]:
                cache_path = os.path.join(pdir, filename + cache_ext)
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    break

        # Fallback: try reading as plain text
        if not text and ext in {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".json",
            ".csv",
            ".html",
            ".xml",
            ".yaml",
            ".yml",
        }:
            try:
                text = file_bytes.decode("utf-8", errors="ignore")
            except Exception as e:
                logger.warning("Error suppressed: %s", e)
                pass

        if text and len(text.strip()) > 50:
            from src.memory.vector_lifecycle import VectorLifecycleManager

            await VectorLifecycleManager.index_processed_file(
                project_id, filename, text.strip()
            )
            logger.info(
                "Auto-indexed %s into project %s knowledge base", filename, project_id
            )
        else:
            logger.info("Skipped indexing %s — no extractable text", filename)
    except Exception as e:
        logger.error("Failed to auto-index %s: %s", filename, e)

    return {"status": "ok"}


async def openai_stream_generator(
    lc_messages, project_id, persona_id, auto_approve_sensitive
):
    """Generator for streaming OpenAI SSE format completion chunks."""
    import time
    import uuid

    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_time = int(time.time())

    thread_id = f"api-{uuid.uuid4().hex[:8]}"
    from src.config.config_loader import config as app_config

    stream_model_id = str(
        app_config.get("models.router.id")
        or app_config.get("models.medium.id")
        or "owlynn-local"
    )

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": int(app_config.get("complex.recursion_limit", 100)),
    }
    inputs = {
        "messages": lc_messages,
        "project_id": project_id,
        "persona_id": persona_id,
        "mode": "api",
        "auto_approve_sensitive": auto_approve_sensitive,
    }

    try:
        async for event in app.state.agent.astream_events(
            inputs, config=config, version="v2"
        ):
            kind = event.get("event")
            metadata = event.get("metadata", {})
            node = metadata.get("langgraph_node")

            if kind == "on_chat_model_stream" and node in ["simple", "complex_llm"]:
                chunk = event["data"]["chunk"]
                if chunk.content:
                    text = _stringify_lc_message_content(chunk.content)
                    if text and not text.strip().startswith("[Internal reminder"):
                        # Format as SSE chunk
                        chunk_payload = {
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": stream_model_id,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(chunk_payload, ensure_ascii=False)}\n\n"

        # Final finish reason stop chunk
        stop_payload = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": stream_model_id,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(stop_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error("Error in OpenAI stream generator: %s", e)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
