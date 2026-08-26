"""
FastAPI Backend Server for Local Cowork Agent.

This module defines the API endpoints and WebSocket handlers for interacting
with the LangGraph agent, managing user profiles, and serving the frontend.
It supports streaming responses and handling multimodal file uploads.
"""

import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage

from src.agent.core.graph import init_agent
from src.agent.llm import LLMPool
from src.api.file_processor import start_watcher as start_watcher
from src.api.routes import (
    browser_extension,
    config,
    export,
    files,
    memory,
    notebook,
    openai,
    pentest,
    profile,
    project,
    scheduled_jobs,
    settings,
    study,
    thought_graph,
)
from src.api.shared import _stringify_lc_message_content
from src.api.ws import handler as ws_handler
from src.config.settings import WORKSPACE_DIR
from src.memory.personal_assistant import (
    get_memory_context_for_prompt,
)
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

from src.api.shared import _session_usage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize centralized logging
    from src.config.logging_config import setup_logging

    setup_logging()

    # ── Background Worker Init ────────────────────────────────────────────────
    try:
        from src.api.scheduler_manager import scheduler_manager

        scheduler_manager.start()
    except Exception as e:
        logger.error(f"Failed to start APScheduler: {e}")

    # ── Crash logging infrastructure ────────────────────────────────────────
    import faulthandler
    import sys
    import threading
    from pathlib import Path

    _crash_log_dir = Path.home() / ".owlynn" / "logs"
    _crash_log_path = _crash_log_dir / "crash.log"
    _crash_file = None
    _crash_log_writable = False

    try:
        _crash_log_dir.mkdir(parents=True, exist_ok=True)
        _crash_file = open(str(_crash_log_path), "a")
        faulthandler.enable(file=_crash_file)
        _crash_log_writable = True
    except OSError as e:
        # Sandboxed pytest / read-only home: keep process alive; fall back to stderr.
        logger.warning(
            "Crash log unavailable at %s (%s); faulthandler using default stderr",
            _crash_log_path,
            e,
        )
        try:
            faulthandler.enable()
        except Exception:
            pass

    def _append_crash_log(header: str, write_fn) -> None:
        if not _crash_log_writable:
            return
        try:
            with open(str(_crash_log_path), "a") as f:
                f.write(header)
                write_fn(f)
        except OSError:
            pass

    # 2.2 sys.excepthook — captures unhandled exceptions on the main thread
    _crash_logger = logging.getLogger("system.crash")

    def _crash_excepthook(exc_type, exc_value, exc_tb):
        import datetime
        import traceback as _tb

        if exc_type is KeyboardInterrupt:
            return
        _append_crash_log(
            f"\n--- {datetime.datetime.now()} [main thread] ---\n",
            lambda f: _tb.print_exception(exc_type, exc_value, exc_tb, file=f),
        )
        _crash_logger.critical(
            "Unhandled exception on main thread", exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = _crash_excepthook

    def _threading_excepthook(args):
        import datetime
        import traceback as _tb

        _append_crash_log(
            f"\n--- {datetime.datetime.now()} [background thread] ---\n",
            lambda f: _tb.print_exception(
                args.exc_type, args.exc_value, args.exc_traceback, file=f
            ),
        )
        _crash_logger.critical(
            "Unhandled exception in background thread",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _threading_excepthook

    # 2.3 asyncio exception handler — captures unhandled async task exceptions
    def _async_exception_handler(loop, context):
        import datetime
        import traceback as _tb

        exc = context.get("exception")
        msg = context.get("message", "Unhandled async exception")
        _crash_logger.error(
            "Async error: %s | exception: %s", msg, exc, exc_info=True if exc else None
        )

        def _write(f):
            f.write(f"message: {msg}\n")
            if exc:
                _tb.print_exception(type(exc), exc, exc.__traceback__, file=f)

        _append_crash_log(f"\n--- {datetime.datetime.now()} [asyncio] ---\n", _write)

    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_async_exception_handler)

    from src.api.local_auth import init_local_run_token

    init_local_run_token(app)

    # Preserve loop for async dispatchs from sync threads
    app.state.loop = asyncio.get_running_loop()

    # Initialize the LangGraph Agent Engine Singleton asynchronously
    app.state.agent = await init_agent()
    app.state.sessions = {}  # thread_id -> GraphSession

    # Start power monitor loop
    from src.api.power_monitor import is_on_battery, power_monitor_loop

    app.state.power_monitor_task = asyncio.create_task(power_monitor_loop())

    # Start idle resource manager (LLM unload + StirlingPDF idle shutdown)
    from src.api.idle_manager import idle_watcher_loop

    app.state.idle_watcher_task = asyncio.create_task(idle_watcher_loop())

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

        if await is_on_battery():
            logger.info("[startup] Eco-Mode active: Skipping heavy LLM preloads.")
            preload_slots = []
            warmup = False

        # 1. Router (small) — always required
        try:
            from src.agent.model_swap import swap_to_default

            # Ensure LM Studio is in the default state (unloads pentest model if stuck in VRAM)
            await swap_to_default()

            await LLMPool.get_main_llm()
            logger.info("[startup] Main LLM client created")
        except Exception as e:
            logger.warning("[startup] Main LLM preload failed: %s", e)
            return

        # 2. Embedding — lightweight ping (no LM Studio model swap)
        if "embedding" in preload_slots:
            try:
                import httpx

                embed_url = config.get_embedding_base_url().rstrip("/")
                embed_model = config.get_embedding_model_name()
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

        # 3. Extraction (google/gemma-4-26b-a4b-qat) — always available for background work
        if "extraction" in preload_slots:
            try:
                await LLMPool.get_extraction_llm()
                logger.info("[startup] Extraction LLM client created")
            except Exception as e:
                logger.warning("[startup] Extraction LLM preload failed: %s", e)

        # 4. Vision — (e.g. Baidu OCR)
        if "vision" in preload_slots:
            try:
                from src.agent.core.complex_utils.vision_model_manager import (
                    get_vision_llm,
                )

                await get_vision_llm()
                logger.info("[startup] Vision LLM client created")
            except Exception as e:
                logger.warning("[startup] Vision LLM preload failed: %s", e)

        if warmup:
            await _asyncio.sleep(2)
            warmup_text = [HumanMessage(content="hi")]
            try:
                main_llm = await LLMPool.get_main_llm()
                await _asyncio.wait_for(
                    main_llm.ainvoke(warmup_text),
                    timeout=30,
                )
                logger.info("[startup] Main LLM warmup complete")
            except Exception as e:
                logger.warning("[startup] Main LLM warmup failed: %s", e)

        logger.info("[startup] LLM preload complete (cloud_on=%s)", cloud_on)

    await _preload_llms()
    app.state.llms_ready = True

    from src.memory.extraction.worker import (
        start_extraction_worker,
        stop_extraction_worker,
    )

    await start_extraction_worker()
    app.state.memory_extraction_worker = True

    from src.agent.core.complex_utils.vision_model_manager import (
        start_vision_manager,
        stop_vision_manager,
    )

    await start_vision_manager()
    app.state.vision_manager = True

    # Embedding models are pre-pulled manually via `ollama pull` or LM Studio UI.
    # The app relies on them being already available; no auto-load at startup.

    # Chat-only organic map: no persistent workspace file watcher.
    app.state.file_watcher = None

    from src.config.trace_pruner import start_trace_pruner

    app.state.trace_pruner = await start_trace_pruner()

    # Check which existing chats have checkpoint data (non-blocking)
    async def _check_legacy_chats():
        try:
            import asyncio as _asyncio

            from src.agent.core.checkpointer import get_postgres_saver
            from src.memory.project import project_manager

            await _asyncio.sleep(5)  # let the system stabilize
            try:
                saver = await get_postgres_saver()
            except Exception:
                return

            legacy_count = 0
            total_count = 0
            for proj in await project_manager.list_projects():
                for chat in proj.get("chats", []):
                    chat_id = chat.get("id")
                    if not chat_id:
                        continue
                    total_count += 1
                    config = {"configurable": {"thread_id": chat_id}}
                    result = await saver.aget_tuple(config)
                    if result is None:
                        legacy_count += 1
            if legacy_count > 0:
                logger.warning(
                    "[startup] %d/%d chats have no checkpoint data (created before Postgres checkpointer). "
                    "These chats will show 'history unavailable' when opened.",
                    legacy_count,
                    total_count,
                )
        except Exception as e:
            logger.debug("[startup] Legacy chat check skipped: %s", e)

    import asyncio as _asyncio

    _asyncio.ensure_future(_check_legacy_chats())

    yield
    # ── Graceful Shutdown ─────────────────────────────────────────────────────
    try:
        from src.api.scheduler_manager import scheduler_manager

        scheduler_manager.shutdown()
    except Exception as e:
        logger.error(f"Failed to shutdown APScheduler: {e}")

    if getattr(app.state, "memory_extraction_worker", False):
        await stop_extraction_worker()
    if getattr(app.state, "vision_manager", False):
        await stop_vision_manager()
    watcher = getattr(app.state, "file_watcher", None)
    if watcher:
        try:
            watcher.stop()
            watcher.join(timeout=2.0)
        except Exception as e:
            logger.warning("Failed to stop file watcher: %s", e)
    if getattr(app.state, "power_monitor_task", None):
        app.state.power_monitor_task.cancel()

    if getattr(app.state, "idle_watcher_task", None):
        app.state.idle_watcher_task.cancel()

    if getattr(app.state, "trace_pruner", None):
        app.state.trace_pruner.cancel()

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
app.include_router(pentest.router)
app.include_router(ws_handler.router)
app.include_router(scheduled_jobs.router)
app.include_router(config.router)
app.include_router(export.router)
app.include_router(thought_graph.router)

from src.api.local_auth import cors_allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_origin_regex=r"^(chrome-extension|moz-extension)://.*$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Owlynn-Run-Token", "Accept"],
)

# Audit logging middleware (HTTP request logging)
from src.config.log_middleware import AuditLogMiddleware

app.add_middleware(AuditLogMiddleware)


# ── Local run token authentication middleware ─────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


class LocalAuthMiddleware(BaseHTTPMiddleware):
    """Require X-Owlynn-Run-Token header on all /api/* requests.

    Exemptions:
    - /api/health (used by frontend to check readiness)
    - /api/local-run-token (used by frontend to fetch the token)
    - /api/browser_extension/status (read-only connection poll)
    - /api/browser_extension/token (Origin-gated; extension bootstrap)
    - /api/study/* (read-only dashboard, no sensitive data)
    - /api/usage (read-only stats)
    - /api/cloud-status (read-only)

    Privileged browser_extension REST (/search|/fetch|/screenshot|/reload)
    accepts the local run token OR the extension WS token.
    """

    _EXEMPT_PATHS = {
        "/api/health",
        "/api/local-run-token",
        "/api/cloud-status",
        "/api/usage",
        "/api/browser_extension/status",
        "/api/browser_extension/token",
    }
    _EXEMPT_PREFIXES = ("/api/study",)
    _EXTENSION_REST_PREFIX = "/api/browser_extension/"

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only gate /api/* routes
        if not path.startswith("/api/"):
            return await call_next(request)

        # Exempt paths
        if path in self._EXEMPT_PATHS:
            return await call_next(request)

        # Exempt prefixes
        if any(path.startswith(p) for p in self._EXEMPT_PREFIXES):
            return await call_next(request)

        # Verify token
        from src.api.local_auth import get_local_run_token, is_loopback_client

        # Allow test clients (TestClient uses "testclient" as host)
        client_host = ""
        if request.client:
            client_host = request.client.host or ""
        if client_host == "testclient":
            return await call_next(request)

        if not is_loopback_client(request):
            return JSONResponse(
                status_code=403,
                content={"detail": "API only accessible from localhost"},
            )

        token = request.headers.get("X-Owlynn-Run-Token") or request.query_params.get(
            "token"
        )
        expected = get_local_run_token(request.app)
        token_ok = isinstance(token, str) and secrets.compare_digest(token, expected)

        # Browser extension control-plane REST: also accept extension WS token
        if (
            not token_ok
            and path.startswith(self._EXTENSION_REST_PREFIX)
            and isinstance(token, str)
        ):
            from src.api.routes.browser_extension import get_extension_auth_token

            ext_token = get_extension_auth_token()
            token_ok = isinstance(ext_token, str) and secrets.compare_digest(
                token, ext_token
            )

        if not token_ok:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid local run token"},
            )

        return await call_next(request)


app.add_middleware(LocalAuthMiddleware)

# Serve frontend static files from frontend-v2 dist only.
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_DEFAULT_FRONTEND_DIR = os.path.join(_ROOT_DIR, "frontend-v2", "dist")
FRONTEND_DIR = os.environ.get("OWLYNN_FRONTEND_DIR", _DEFAULT_FRONTEND_DIR)


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
_VENDOR_DIR = os.path.join(_ROOT_DIR, "assets", "vendor")
app.mount("/vendor", StaticFiles(directory=_VENDOR_DIR, check_dir=False), name="vendor")


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
    from src.agent.cloud.cloud_cost_tracker import (
        build_cloud_usage_payload,
        get_cost_tracker,
    )
    from src.config.config_loader import config
    from src.memory.user_profile import get_profile

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
    from src.agent.core.graph import _check_cloud_connectivity

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
    """Agent readiness + honest Postgres / checkpointer fields.

    Consumers that mean "can I talk to the API?" MUST use ``agent === "ready"``
    (or accept HTTP 200 while waiting). Do **not** require ``status === "ok"`` —
    ``status`` is ``degraded`` when the Postgres soft-path circuit is open while
    chat can still limp. Nested ``postgres`` / ``checkpointer`` stay authoritative
    for memory durability.
    """
    agent_ready = False
    try:
        agent_ready = (
            hasattr(app, "state")
            and getattr(app.state, "agent", None) is not None
            and getattr(app.state, "llms_ready", False) is True
        )
    except Exception as e:
        logger.warning("Error suppressed: %s", e)

    from src.memory.postgres_health import get_checkpointer_backend, postgres_status

    pg = postgres_status()
    checkpointer = get_checkpointer_backend()
    # Top-level status = memory durability, not agent readiness.
    overall = "degraded" if pg != "ok" else "ok"

    return {
        "status": overall,
        "agent": "ready" if agent_ready else "initializing",
        "postgres": pg,
        "checkpointer": checkpointer,
    }


@app.get("/api/system-info")
async def api_system_info():
    """Return live infrastructure status: Postgres, LM Studio, optional Stirling.

    Postgres + LM Studio are the core dependencies for a healthy local-first session.
    """
    import asyncio
    import os
    import socket
    import subprocess

    import httpx

    from src.config.config_loader import config as cfg

    result: dict = {
        "model_name": cfg.get("models.main.model_name", ""),
        "lm_studio_url": cfg.get("models.main.base_url", "http://127.0.0.1:1234/v1"),
        "lm_studio": "error",
        "postgres": "error",
        "stirling": "off",
        "podman": "unavailable",
        "podman_containers": 0,
        "features": {
            "pentest_enabled": bool(cfg.get("features.pentest_enabled", False)),
        },
    }

    # LM Studio check (OpenAI-compatible /v1/models)
    try:
        base = result["lm_studio_url"].rstrip("/")
        models_url = (
            (base + "/models") if base.endswith("/v1") else (base + "/v1/models")
        )
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(models_url)
            result["lm_studio"] = "ok" if r.status_code == 200 else "error"
    except (httpx.HTTPError, OSError):
        result["lm_studio"] = "error"

    # Postgres check — TCP connect to DATABASE_URL host/port (default localhost:5432)
    def _check_postgres() -> str:
        try:
            dsn = os.environ.get("DATABASE_URL", "")
            host, port = "127.0.0.1", 5432
            if "://" in dsn:
                # postgresql+asyncpg://user:pass@host:port/db
                after = dsn.split("://", 1)[1]
                if "@" in after:
                    after = after.split("@", 1)[1]
                hostport = after.split("/", 1)[0]
                if ":" in hostport:
                    host, port_s = hostport.rsplit(":", 1)
                    port = int(port_s)
                else:
                    host = hostport or host
            with socket.create_connection((host, port), timeout=2.0):
                return "ok"
        except OSError:
            return "error"

    result["postgres"] = await asyncio.get_event_loop().run_in_executor(
        None, _check_postgres
    )

    # Prefer circuit-breaker view when soft-path has opened (honest degraded).
    try:
        from src.memory.postgres_health import (
            get_checkpointer_backend,
            postgres_status,
        )

        cb_status = postgres_status()
        if cb_status != "ok":
            result["postgres"] = cb_status
        elif result["postgres"] == "error":
            result["postgres"] = "error"
        result["checkpointer"] = get_checkpointer_backend()
    except Exception:
        result["checkpointer"] = "memory"

    # Optional StirlingPDF
    stirling_url = cfg.get(
        "external_services.stirling_pdf.url", "http://127.0.0.1:8090"
    )
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{stirling_url.rstrip('/')}/api/v1/info")
            result["stirling"] = "ok" if r.status_code < 400 else "error"
    except (httpx.HTTPError, OSError):
        result["stirling"] = "off"

    # Podman/Docker check — run in thread pool to avoid blocking the event loop
    def _run_container_cli() -> tuple[str, int]:
        for cli in ("podman", "docker"):
            try:
                proc = subprocess.run(
                    [cli, "ps", "--format", "{{.Names}}"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    check=False,
                )
                if proc.returncode == 0:
                    containers = [
                        c.strip() for c in proc.stdout.splitlines() if c.strip()
                    ]
                    return "running", len(containers)
            except FileNotFoundError:
                continue
            except OSError:
                return "stopped", 0
        return "unavailable", 0

    podman_status, podman_count = await asyncio.get_event_loop().run_in_executor(
        None, _run_container_cli
    )
    result["podman"] = podman_status
    result["podman_containers"] = podman_count

    return result


@app.get("/api/local-run-token")
async def api_local_run_token(request: Request):
    """Return the local run token for WS authentication. Only accessible from localhost."""
    from src.api.local_auth import get_local_run_token, is_loopback_client

    if not is_loopback_client(request):
        raise HTTPException(status_code=403, detail="Only available from localhost")
    token = get_local_run_token(app)
    return {"token": token}


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
        context = await get_memory_context_for_prompt()
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

    async def _wait_for_processed_cache(fp: str, timeout: float = 8.0) -> str:
        """Poll .processed/ for the cached text file instead of blindly sleeping."""
        project_processed_dir = os.path.join(os.path.dirname(fp), ".processed")
        root_processed_dir = os.path.join(
            os.path.abspath(str(WORKSPACE_DIR)), ".processed"
        )
        fname = os.path.basename(fp)
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            for pdir in [project_processed_dir, root_processed_dir]:
                for cache_ext in [".txt", ".md"]:
                    cache_path = os.path.join(pdir, fname + cache_ext)
                    if os.path.exists(cache_path):
                        try:
                            with open(cache_path, "r", encoding="utf-8") as f:
                                return f.read()
                        except Exception:
                            pass
            await asyncio.sleep(0.3)
        return ""

    text = await _wait_for_processed_cache(filepath)
    ext = os.path.splitext(filename)[1].lower()

    try:
        # If poll didn't find the cache, try reading the processed dirs directly
        if not text:
            project_processed_dir = os.path.join(
                os.path.dirname(filepath), ".processed"
            )
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
        "auto_approve_sensitive": False,
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
