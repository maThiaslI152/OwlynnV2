"""
FastAPI Backend Server for Local Cowork Agent.

This module defines the API endpoints and WebSocket handlers for interacting
with the LangGraph agent, managing user profiles, and serving the frontend.
It supports streaming responses and handling multimodal file uploads.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import Response
from fastapi import HTTPException
import json
import asyncio
import os
import re
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.types import Command

from src.agent.graph import init_agent
from src.agent.nodes.router import generate_chat_title_router_llm
from src.agent.llm import LLMPool
from src.memory.user_profile import get_profile, update_profile, VALID_FIELDS
from src.memory.persona import get_persona, update_persona_field
from src.memory.memory_manager import load_memories, save_memory, delete_memory
from src.memory.long_term import memory as mem0_memory
from src.memory.project import project_manager
from src.memory.personal_assistant import (
    get_relevant_topics,
    get_user_interests_summary,
    load_conversations_history,
    get_memory_context_for_prompt,
    track_topic,
    update_interests,
)
from src.config.settings import WORKSPACE_DIR, get_project_workspace, normalize_project_id
from src.api.file_processor import start_watcher
from src.tools.workspace_context import reset_active_project, set_active_project_for_run

from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_info, audit_debug
from src.config.config_loader import config

connected_websockets = set()

def notify_file_processed(filepath_or_name, status="processed"):
    """Callback for FileWatcher background thread to broadcast over websockets and auto-index projects."""
    import asyncio
    import os
    
    # Gracefully handle both full path and legacy plain filename
    filepath = os.path.abspath(filepath_or_name) if (isinstance(filepath_or_name, str) and (os.path.isabs(filepath_or_name) or os.path.exists(filepath_or_name))) else filepath_or_name
    filename = os.path.basename(filepath) if isinstance(filepath, str) else str(filepath)
    
    loop = getattr(app.state, "loop", None)
    if not loop:
        logger.warning("Loop not preserved, cannot notify websocket clients.")
        return
        
    # Broadcast to all active websockets
    for ws in list(connected_websockets):
        try:
            coro = ws.send_json({"type": "file_status", "name": filename, "status": status})
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:
            logger.warning("Failed to send ws notification: %s", e)
            
    # Auto-index into project knowledge base if it's inside a project workspace and is successfully processed
    if status == "processed" and isinstance(filepath, str) and os.path.exists(filepath):
        try:
            rel_path = os.path.relpath(filepath, WORKSPACE_DIR)
            parts = rel_path.split(os.sep)
            if len(parts) >= 3 and parts[0] == "projects":
                project_id = parts[1]
                # Auto-index all projects, including default
                # Read the processed text format in .processed/
                # Check both project-local and root workspace cache paths
                project_workspace = get_project_workspace(project_id)
                root_processed = os.path.join(WORKSPACE_DIR, ".processed")
                cache_path = None
                
                for search_dir in [root_processed, os.path.join(project_workspace, ".processed")]:  # root first (fast path)
                    for ext in [".txt", ".md"]:
                        candidate = os.path.join(search_dir, filename + ext)
                        if os.path.exists(candidate):
                            cache_path = candidate
                            break
                    if cache_path:
                        break
                        
                if cache_path:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    
                    if text and len(text.strip()) > 50:
                        async def index_task():
                            try:
                                # Chunk the text: configurable chunk_size with overlap
                                from src.config.config_loader import config as _app_cfg
                                chunks = []
                                chunk_size = int(_app_cfg.get("file_indexing.chunk_size", 1500))
                                overlap = int(_app_cfg.get("file_indexing.overlap", 200))
                                max_chunks = int(_app_cfg.get("file_indexing.max_chunks", 20))
                                start = 0
                                content_len = len(text)
                                while start < content_len:
                                    end = start + chunk_size
                                    chunk = text[start:end].strip()
                                    if chunk:
                                        chunks.append(chunk)
                                    start += chunk_size - overlap
                                
                                # Index each chunk (up to max_chunks to prevent performance issues)
                                for i, chunk_text in enumerate(chunks[:max_chunks]):
                                    await project_manager.add_knowledge(
                                        project_id,
                                        f"{filename}#chunk{i}",
                                        chunk_text
                                    )
                                logger.info("Auto-indexed %d chunks of %s into project %s knowledge base", len(chunks[:20]), filename, project_id)
                            except Exception as e:
                                logger.error("Failed to auto-index file %s: %s", filepath, e)
                                
                        asyncio.run_coroutine_threadsafe(index_task(), loop)
        except Exception as e:
            logger.error("Error in watcher auto-indexing: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize centralized logging
    from src.config.logging_config import setup_logging
    setup_logging()
    
    # Preserve loop for async dispatchs from sync threads
    app.state.loop = asyncio.get_running_loop()
    
    # Initialize the LangGraph Agent Engine Singleton asynchronously
    app.state.agent = await init_agent()
    app.state.sessions = {} # thread_id -> GraphSession

    # Preload medium LLM (gemma4) in background.
    # Avoids cold-start swap latency on the first complex request.
    async def _preload_medium():
        try:
            from src.agent.llm import LLMPool
            await LLMPool.get_medium_llm("default")
            logger.info("[startup] Medium LLM preloaded successfully")
        except Exception as e:
            logger.warning("[startup] Medium LLM preload skipped: %s", e)
    asyncio.create_task(_preload_medium())

    # Embedding models are pre-pulled manually via `ollama pull` or LM Studio UI.
    # The app relies on them being already available; no auto-load at startup.
    
    # Start background file watcher with WebSocket callback
    try:
        app.state.file_watcher = start_watcher(WORKSPACE_DIR, on_processed_callback=notify_file_processed)
    except Exception as e:
        logger.warning("Failed to start file watcher: %s", e)
        app.state.file_watcher = None
        
    yield
    # Cleanup: cancel all background tasks
    if getattr(app.state, "file_watcher", None):
        try:
            app.state.file_watcher.stop()
            app.state.file_watcher.join()
        except Exception:
            pass
            
    for session in app.state.sessions.values():
        if session.task:
            session.task.cancel()

app = FastAPI(title="Local Cowork Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        raise HTTPException(status_code=503, detail="frontend-v2 build is missing (expected frontend-v2/dist/index.html)")
    return FileResponse(index_path)

# Mount static roots for frontend assets.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR, check_dir=False), name="static")
_ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")
app.mount("/assets", StaticFiles(directory=_ASSETS_DIR, check_dir=False), name="assets")

@app.get("/script.js")
async def serve_script():
    raise HTTPException(status_code=410, detail="Legacy script.js endpoint retired; use frontend-v2 assets")

@app.get("/style.css")
async def serve_style():
    raise HTTPException(status_code=410, detail="Legacy style.css endpoint retired; use frontend-v2 assets")

@app.get("/vendor/{path:path}")
async def serve_vendor_retired(path: str):
    raise HTTPException(status_code=410, detail="Legacy vendor endpoint retired; use frontend-v2 bundled assets")

# ─── REST API endpoints ──────────────────────────────────────────────────────

# Track cumulative session token usage
_session_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

# Profile fields that require clearing cached LLM instances when changed
_LLM_SENSITIVE_FIELDS = {
    "cloud_llm_base_url", "cloud_llm_model_name", "deepseek_api_key",
    "cloud_request_timeout",
    "llm_base_url", "llm_model_name", "large_llm_base_url", "large_llm_model_name",
    "medium_models", "small_llm_base_url", "small_llm_model_name",
}

_ADVANCED_SETTINGS_DEFAULTS = {
    "temperature": 0.7,
    "top_p": 0.9,
    "max_tokens": 2048,
    "top_k": 40,
    "streaming_enabled": True,
    "show_thinking": False,
    "show_tool_execution": True,
    "cloud_escalation_enabled": True,
    "cloud_anonymization_enabled": True,
    "router_hitl_enabled": True,
    "router_clarification_threshold": 0.6,
    "execution_policy": "auto_approve",
    "safe_mode": "normal",
    "custom_sensitive_terms": [],
    "redis_url": "redis://localhost:6379",
    "lm_studio_fold_system": True,
}

_UNIFIED_SETTINGS_CLOUD_BUDGET_DEFAULTS = {
    "cloud_daily_token_limit": config.get("cloud.budget.daily_token_limit", 500_000),
    "cloud_budget_warning_thresholds": config.get("cloud.budget.warning_thresholds", [0.5, 0.8, 0.95]),
}

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
    from src.agent.cloud_cost_tracker import get_cost_tracker
    tracker = get_cost_tracker()
    return {
        "session": _session_usage,
        "cost": tracker.summary(),
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

@app.get("/api/profile")
async def api_get_profile():
    return get_profile()

@app.post("/api/profile")
async def api_update_profile(body: dict):
    updated_fields: list[str] = []
    update_errors: dict[str, str] = {}
    for field, value in body.items():
        try:
            update_profile(field, value)
            updated_fields.append(field)
        except Exception as exc:
            update_errors[field] = str(exc)
    needs_llm_clear = any(f in _LLM_SENSITIVE_FIELDS for f in updated_fields)
    if needs_llm_clear:
        LLMPool.clear()
    profile = get_profile()
    if update_errors:
        return {
            "status": "partial_success",
            "profile": profile,
            "updated_fields": updated_fields,
            "errors": update_errors,
        }
    return profile

@app.get("/api/persona")
async def api_get_persona():
    return get_persona()

@app.post("/api/persona")
async def api_update_persona(body: dict):
    for field, value in body.items():
        try:
            update_persona_field(field, value)
        except Exception as e:
            logger.warning("[persona] update failed for field %s: %s", field, e)
    return get_persona()

@app.get("/api/personas")
async def api_list_personas():
    """List all available personas (built-in + custom)."""
    from src.memory.persona_manager import list_personas
    return list_personas()

@app.post("/api/personas")
async def api_create_persona(body: dict):
    """Save a new custom persona definition."""
    from src.memory.persona_manager import save_custom_persona
    success = save_custom_persona(body)
    if success:
        return {"status": "ok", "message": f"Saved custom persona: {body.get('id')}"}
    return {"status": "error", "message": "Failed to save persona (ensure 'id' is unique and not a built-in)"}

@app.get("/api/system-settings")
async def api_get_system_settings():
    """Get system prompts and instructions."""
    try:
        profile = get_profile()
        persona = get_persona()
        return {
            "system_prompt": profile.get("system_prompt", ""),
            "custom_instructions": profile.get("custom_instructions", ""),
            "name": persona.get("name", "Owlynn"),
            "tone": persona.get("tone", "friendly")
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/system-settings")
async def api_update_system_settings(body: dict):
    """Update system prompts and instructions."""
    try:
        update_profile("system_prompt", body.get("system_prompt", ""))
        update_profile("custom_instructions", body.get("custom_instructions", ""))
        if body.get("name"):
            update_persona_field("name", body["name"])
        if body.get("tone"):
            update_persona_field("tone", body["tone"])
        return {"status": "ok", "message": "System settings saved"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/memory-settings")
async def api_get_memory_settings():
    """Get memory settings."""
    try:
        profile = get_profile()
        return {
            "short_term_enabled": profile.get("short_term_enabled", True),
            "long_term_enabled": profile.get("long_term_enabled", True)
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/memory-settings")
async def api_update_memory_settings(body: dict):
    """Update memory settings."""
    try:
        if "short_term_enabled" in body:
            update_profile("short_term_enabled", body["short_term_enabled"])
        if "long_term_enabled" in body:
            update_profile("long_term_enabled", body["long_term_enabled"])
        return {"status": "ok", "message": "Memory settings saved"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/advanced-settings")
async def api_get_advanced_settings():
    """Get inference and behavior settings."""
    try:
        profile = get_profile()
        return {
            field: profile.get(field, default)
            for field, default in _ADVANCED_SETTINGS_DEFAULTS.items()
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/unified-settings")
async def api_get_unified_settings():
    """Get merged profile and advanced settings in one payload."""
    try:
        from src.config.secret_store import resolve_deepseek_api_key

        profile = get_profile()
        unified = dict(profile)
        unified.update({
            field: profile.get(field, default)
            for field, default in _ADVANCED_SETTINGS_DEFAULTS.items()
        })
        # These budget fields may not exist in old profiles; provide stable defaults.
        unified.update({
            field: profile.get(field, default)
            for field, default in _UNIFIED_SETTINGS_CLOUD_BUDGET_DEFAULTS.items()
        })

        # Never expose raw API keys to the frontend.
        # Check Keychain first, then env var, then (deprecated) profile.
        deepseek_key = resolve_deepseek_api_key()
        unified["deepseek_api_key"] = "••••••••" if deepseek_key else ""
        return unified
    except Exception as e:
        return {"error": str(e)}


@app.put("/api/unified-settings")
async def api_update_unified_settings(body: dict):
    """Update unified profile and advanced settings in one payload.

    The ``deepseek_api_key`` field is stored in macOS Keychain (not profile).
    Pass ``""`` (empty string) to delete the key.
    """
    try:
        from src.config.secret_store import store_deepseek_api_key, delete_deepseek_api_key

        # Allowed fields: profile VALID_FIELDS + advanced settings defaults + cloud budget
        allowed = set(VALID_FIELDS.keys()) | set(_ADVANCED_SETTINGS_DEFAULTS.keys()) | set(_UNIFIED_SETTINGS_CLOUD_BUDGET_DEFAULTS.keys())
        updated = []
        for field, value in body.items():
            if field == "deepseek_api_key":
                # Secure storage path — Keychain, not profile
                key_value = str(value).strip() if value else ""
                if key_value and key_value != "••••••••":
                    store_deepseek_api_key(key_value)
                    updated.append(field)
                elif not key_value:
                    delete_deepseek_api_key()
                    updated.append(field)
                # If sent as "••••••••", ignore — it's the masked placeholder
            elif field in allowed:
                update_profile(field, value)
                updated.append(field)
        return {"status": "ok", "updated": updated}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/health")
async def api_health():
    """Check if the agent graph is fully initialized."""
    agent_ready = False
    try:
        agent_ready = hasattr(app, "state") and getattr(app.state, "agent", None) is not None
    except Exception:
        pass
        
    return {
        "status": "ok",
        "agent": "ready" if agent_ready else "initializing"
    }


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
        raise HTTPException(status_code=403, detail="Dev API requires OWLYNN_DEV=1 or debug_mode enabled in profile")

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
    return {"status": "fixture_only", "variant": variant, "fixture_name": fixture_name, "payload": fixture}


@app.post("/api/advanced-settings")
async def api_update_advanced_settings(body: dict):
    """Update inference and behavior settings."""
    try:
        for field in _ADVANCED_SETTINGS_DEFAULTS:
            if field in body:
                update_profile(field, body[field])
        return {"status": "ok", "message": "Advanced settings saved"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/memories")
async def api_get_memories():
    return load_memories()

@app.post("/api/memories")
async def api_add_memory(body: dict):
    fact = body.get("fact")
    if not fact:
        return {"status": "error", "message": "Fact required"}
    result = save_memory(fact)
    return {"status": "ok", "message": result, "memories": load_memories()}

@app.delete("/api/memories")
async def api_delete_memory(body: dict):
    fact = body.get("fact")
    if not fact:
        return {"status": "error", "message": "Fact required"}
    success = delete_memory(fact)
    return {"status": "ok" if success else "error", "memories": load_memories()}

# ─── Mem0 LTM API endpoints ──────────────────────────────────────────

@app.get("/api/mem0/search")
async def api_mem0_search(query: str = "", limit: int = 50, project_id: str = ""):
    """Search Mem0 long-term memory.
    
    - query: optional search text (empty returns recent memories)
    - limit: max results (default 50)
    - project_id: if provided, scopes search to that project's memory space;
      otherwise searches global ("owner") memory.
    """
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available", "memories": [], "count": 0}
    try:
        user_id = f"project:{project_id}" if project_id else "owner"
        # Use a broad query to retrieve memories; if empty, use a space to get recent ones
        search_query = query if query else " "
        results_dict = mem0_memory.search(search_query, filters={"user_id": user_id}, limit=limit)
        results = results_dict.get("results", []) if isinstance(results_dict, dict) else results_dict
        # Normalize: Mem0 results may have 'memory' or 'id' keys
        memories = []
        for item in results:
            if isinstance(item, dict):
                memories.append({
                    "id": item.get("id", ""),
                    "memory": item.get("memory", item.get("text", "")),
                    "text": item.get("memory", item.get("text", "")),
                    "created_at": item.get("created_at", ""),
                    "user_id": user_id,
                })
        return {"status": "ok", "memories": memories, "count": len(memories)}
    except Exception as e:
        return {"status": "error", "message": str(e), "memories": [], "count": 0}


@app.get("/api/mem0/count")
async def api_mem0_count(project_id: str = ""):
    """Get the count of memories for a given user/project.
    
    - project_id: if provided, counts project-scoped memories
    """
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available", "count": 0}
    try:
        user_id = f"project:{project_id}" if project_id else "owner"
        # Search with a large limit to get all memories and count them
        results_dict = mem0_memory.search(" ", filters={"user_id": user_id}, limit=1000)
        results = results_dict.get("results", []) if isinstance(results_dict, dict) else results_dict
        count = len(results) if isinstance(results, list) else 0
        return {"status": "ok", "count": count, "user_id": user_id}
    except Exception as e:
        return {"status": "error", "message": str(e), "count": 0}


@app.post("/api/mem0/delete")
async def api_mem0_delete(body: dict):
    """Delete a specific memory from Mem0 by its ID.
    
    Body: { "memory_id": "..." }
    """
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available"}
    try:
        memory_id = body.get("memory_id", "")
        if not memory_id:
            return {"status": "error", "message": "memory_id is required"}
        mem0_memory.delete(memory_id=memory_id)
        return {"status": "ok", "message": f"Deleted memory {memory_id}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/mem0/clear")
async def api_mem0_clear(body: dict):
    """Clear all memories for a given user_id.
    
    Body: { "user_id": "owner" } (defaults to "owner")
    """
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available"}
    try:
        user_id = body.get("user_id", "owner")
        mem0_memory.delete_all(user_id=user_id)
        return {"status": "ok", "message": f"Cleared all memories for {user_id}"} if user_id else {"status": "error", "message": "user_id required"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/mem0/reset")
async def api_mem0_reset():
    """Reset ALL Mem0 memories (global). Use with caution."""
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available"}
    try:
        mem0_memory.reset()
        return {"status": "ok", "message": "All Mem0 memories reset"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Personal Assistant Endpoints - Topics, Interests, Conversation History

@app.get("/api/topics")
async def api_get_topics():
    """Get tracked topics with relevance scores and recency."""
    try:
        topics = get_relevant_topics(limit=10)
        return {"status": "ok", "topics": topics}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/interests")
async def api_get_interests():
    """Get detected interests with occurrence counts."""
    try:
        interests = get_user_interests_summary()
        return {"status": "ok", "interests": interests}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/conversations")
async def api_get_conversations(limit: int = 10):
    """Get recent conversation history with summaries."""
    try:
        conversations = load_conversations_history(limit=limit)
        return {"status": "ok", "conversations": conversations}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/chats/generate-title")
async def api_generate_chat_title(body: dict):
    """
    Generate a short chat title using the router's small LLM.
    Input: { "message": string, "files": [{ "name": string }] } (files optional)
    Output: { "status": "ok", "title": string }
    """
    try:
        message = body.get("message", "") if isinstance(body, dict) else ""
        files = body.get("files", []) if isinstance(body, dict) else []

        file_names: list[str] = []
        if isinstance(files, list):
            for f in files:
                if isinstance(f, str):
                    file_names.append(f)
                elif isinstance(f, dict) and f.get("name"):
                    file_names.append(str(f.get("name")))

        title = await generate_chat_title_router_llm(message, file_names=file_names)
        return {"status": "ok", "title": title or ""}
    except Exception as e:
        return {"status": "error", "message": str(e), "title": ""}


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
        return {"status": "error", "message": str(e)}

@app.post("/api/topics/track")
async def api_track_topic(body: dict):
    """Manually track a topic of interest."""
    try:
        topic = body.get("topic")
        category = body.get("category", "other")
        if not topic:
            return {"status": "error", "message": "Topic required"}
        result = track_topic(topic, category)
        topics = get_relevant_topics(limit=10)
        return {"status": "ok", "message": result, "topics": topics}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/interests/update")
async def api_update_interests(body: dict):
    """Manually update detected interests."""
    try:
        interests = body.get("interests", {})
        if not interests:
            return {"status": "error", "message": "Interests required"}
        update_interests(interests)
        updated = get_user_interests_summary()
        return {"status": "ok", "interests": updated}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/projects")
async def api_list_projects(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return project_manager.list_projects()

@app.post("/api/projects")
async def api_create_project(body: dict):
    name = body.get("name", "New Project")
    instructions = body.get("instructions")
    return project_manager.create_project(name, instructions)

@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
    return project_manager.get_project(project_id)

@app.post("/api/projects/{project_id}/chats")
async def api_add_project_chat(project_id: str, body: dict):
    # body: {id, name?}
    import time
    chat_id = body["id"]
    name = body.get("name", "")
    # Generate a title from the first message if one was provided
    if not name and body.get("first_message"):
        try:
            title = await generate_chat_title_router_llm(body["first_message"])
            if title:
                name = title
        except Exception as e:
            logger.warning("[chat_title] generation failed: %s", e)
    project_manager.add_chat_to_project(project_id, {
        "id": chat_id,
        "name": name or "New Chat",
        "created_at": __import__('time').time()
    })
    return {"status": "ok", "chat": {"id": chat_id, "name": name or "New Chat"}}

@app.delete("/api/projects/{project_id}/chats/{chat_id}")
async def api_delete_project_chat(project_id: str, chat_id: str):
    try:
        project_manager.delete_chat_from_project(project_id, chat_id)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.put("/api/projects/{project_id}/chats/{chat_id}")
async def api_update_project_chat(project_id: str, chat_id: str, body: dict):
    project_manager.update_chat_in_project(project_id, chat_id, **body)
    return {"status": "ok"}

@app.get("/api/tools")
async def api_get_tools():
    """Returns a list of available tools for the Customize view."""
    from src.agent.tool_sets import COMPLEX_TOOLS_WITH_WEB
    tools = []
    for t in COMPLEX_TOOLS_WITH_WEB:
        name = getattr(t, "name", str(t))
        desc = getattr(t, "description", "")
        if not desc and hasattr(t, "__doc__") and t.__doc__:
            desc = t.__doc__.strip().split("\n")[0]
        tools.append({
            "name": name,
            "description": desc or "No description available.",
            "type": "core",
        })
    return tools

@app.get("/api/artifacts")
async def api_get_artifacts(project_id: str = "default"):
    """Returns a list of artifacts. Mocked for design demonstration."""
    # In a full impl, we would read from `{workspace}/.artifacts/`
    return [
        {
            "id": "1",
            "name": "Writing editor",
            "type": "editor",
            "category": "Learn something",
            "image_url": "https://images.unsplash.com/photo-1455390582262-044cdead277a?w=400&auto=format&fit=crop&q=60",
            "description": "Use 'I' instead of 'me' as the subject."
        },
        {
            "id": "2",
            "name": "PRD To Prototype",
            "type": "prototype",
            "category": "Life hacks",
            "image_url": "https://images.unsplash.com/photo-1507238691740-187a5b1d37b8?w=400&auto=format&fit=crop&q=60",
            "description": "Convert PRD to visual design dashboard."
        },
        {
            "id": "3",
            "name": "Slack Project Insights",
            "type": "insights",
            "category": "Play a game",
            "image_url": "https://images.unsplash.com/photo-1563986768609-322da13575f3?w=400&auto=format&fit=crop&q=60",
            "description": "Summarize insights from project slack dumps."
        },
        {
            "id": "4",
            "name": "CodeVerter",
            "type": "converter",
            "category": "Be creative",
            "image_url": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=400&auto=format&fit=crop&q=60",
            "description": "Convert Python to Javascript logic."
        }
    ]

@app.get("/api/files")
async def api_list_files(sub_path: str = "", project_id: str = "default"):
    """Returns a list of files in the workspace with processing status and folder support."""
    try:
        import urllib.parse
        sub_path = urllib.parse.unquote(sub_path)
        
        base_dir = get_project_workspace(project_id)
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
        if not target_dir.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
             
        files = []
        if not os.path.exists(target_dir):
            return []
            
        processed_dir = os.path.join(base_dir, ".processed")
        root_processed_dir = os.path.join(str(WORKSPACE_DIR), ".processed")  # Legacy watcher cache location
        
        for f in os.listdir(target_dir):
            if f.startswith(".") or f == "__pycache__":
                continue
            filepath = os.path.join(target_dir, f)
            stats = os.stat(filepath)
            
            # Identify if item is Folder or File
            is_dir = os.path.isdir(filepath)
            
            # File extraction status cache check (project-local or root watcher cache)
            has_cache = False
            if not is_dir:
                 has_cache = (
                     os.path.exists(os.path.join(processed_dir, f + ".txt")) or
                     os.path.exists(os.path.join(processed_dir, f + ".md")) or
                     os.path.exists(os.path.join(root_processed_dir, f + ".txt")) or
                     os.path.exists(os.path.join(root_processed_dir, f + ".md"))
                 )
                           
            files.append({
                "name": f,
                "size": stats.st_size if not is_dir else 0,
                "modified": stats.st_mtime,
                "type": "folder" if is_dir else "file",
                "status": "processed" if has_cache else "idle"
            })
        return sorted(files, key=lambda x: (x["type"] == "file", x["name"].lower()))
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/files/{filename}")
async def api_get_file(filename: str, sub_path: str = "", project_id: str = "default", mode: str = ""):
    """Serve/View a file from the workspace. mode=text returns processed text content."""
    import urllib.parse
    from fastapi.responses import PlainTextResponse
    filename = urllib.parse.unquote(filename)
    sub_path = urllib.parse.unquote(sub_path)
    
    base_dir = get_project_workspace(project_id)
    target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
    if not target_dir.startswith(os.path.abspath(base_dir)):
         return {"status": "error", "message": "Access denied"}
         
    filepath = os.path.abspath(os.path.join(target_dir, filename))
    if not filepath.startswith(os.path.abspath(base_dir)):
         return {"status": "error", "message": "Access denied"}
    if not os.path.exists(filepath):
         return {"status": "error", "message": "File not found"}

    # Text mode: return processed/cached text content
    if mode == "text":
        # Check project-local .processed dir first, then root workspace .processed
        project_processed_dir = os.path.join(os.path.abspath(base_dir), ".processed")
        root_processed_dir = os.path.join(os.path.abspath(str(WORKSPACE_DIR)), ".processed")
        
        for pdir in [project_processed_dir, root_processed_dir]:
            for ext in [".txt", ".md"]:
                cached = os.path.join(pdir, filename + ext)
                if os.path.exists(cached):
                    with open(cached, "r", encoding="utf-8") as f:
                        return PlainTextResponse(f.read())
        # Fallback: try reading as text directly
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return PlainTextResponse(f.read())
        except Exception:
            return PlainTextResponse("Could not read file as text.", status_code=400)

    return FileResponse(filepath)

@app.delete("/api/files/{filename}")
async def api_delete_file(filename: str, sub_path: str = "", project_id: str = "default"):
    """Deletes a file and its processed cache from the workspace."""
    try:
        import urllib.parse
        filename = urllib.parse.unquote(filename)
        sub_path = urllib.parse.unquote(sub_path)
        
        base_dir = get_project_workspace(project_id)
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
        if not target_dir.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
             
        filepath = os.path.abspath(os.path.join(target_dir, filename))
        if not filepath.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
        if os.path.exists(filepath):
            if os.path.isdir(filepath):
                 import shutil
                 shutil.rmtree(filepath) # Support deleting folders recursively!
            else:
                 os.remove(filepath)
            
        # Clean up cache
        processed_dir = os.path.join(base_dir, ".processed")
        for cache_ext in [".txt", ".md"]:
            cache_path = os.path.join(processed_dir, filename + cache_ext)
            if os.path.exists(cache_path):
                os.remove(cache_path)
                
        # Broadcast removal to websocket
        notify_file_processed(filename, status="deleted")
        return {"status": "ok", "message": f"Deleted {filename}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/files/{filename}/rename")
async def api_rename_file(filename: str, body: dict):
    """Renames a file in the workspace."""
    try:
        import urllib.parse
        filename = urllib.parse.unquote(filename)
        new_name = body.get("new_name")
        sub_path = urllib.parse.unquote(body.get("sub_path", ""))
        project_id = body.get("project_id", "default")
        
        if not new_name:
             return {"status": "error", "message": "new_name is required"}
             
        base_dir = get_project_workspace(project_id)
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
        if not target_dir.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
             
        old_path = os.path.abspath(os.path.join(target_dir, filename))
        new_path = os.path.abspath(os.path.join(target_dir, new_name))
        if not old_path.startswith(os.path.abspath(base_dir)) or not new_path.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
        
        if not os.path.exists(old_path):
             return {"status": "error", "message": "File not found"}
        if os.path.exists(new_path):
             return {"status": "error", "message": "File with new name already exists"}
             
        os.rename(old_path, new_path)
        
        # Rename cache too
        processed_dir = os.path.join(base_dir, ".processed")
        for cache_ext in [".txt", ".md"]:
             old_cache = os.path.join(processed_dir, filename + cache_ext)
             new_cache = os.path.join(processed_dir, new_name + cache_ext)
             if os.path.exists(old_cache):
                 os.rename(old_cache, new_cache)
                 
        notify_file_processed(filename, status="deleted")
        notify_file_processed(new_name, status="processed")
        
        return {"status": "ok", "message": f"Renamed to {new_name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/files/{filename}/move")
async def api_move_file(filename: str, body: dict):
    """Moves a file or folder into another subdirectory within the project workspace."""
    try:
        import urllib.parse
        filename = urllib.parse.unquote(filename)
        current_sub_path = urllib.parse.unquote(body.get("current_sub_path", ""))
        target_sub_path = urllib.parse.unquote(body.get("target_sub_path", ""))
        project_id = body.get("project_id", "default")
        
        base_dir = get_project_workspace(project_id)
        src_dir = os.path.abspath(os.path.join(base_dir, current_sub_path))
        dst_dir = os.path.abspath(os.path.join(base_dir, target_sub_path))
        
        if not src_dir.startswith(os.path.abspath(base_dir)) or not dst_dir.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
             
        old_path = os.path.abspath(os.path.join(src_dir, filename))
        new_path = os.path.abspath(os.path.join(dst_dir, filename))
        if not old_path.startswith(os.path.abspath(base_dir)) or not new_path.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
        
        if not os.path.exists(old_path):
             return {"status": "error", "message": f"Source file not found: {filename}"}
        if os.path.exists(new_path):
             return {"status": "error", "message": "Destination already contains an item with this name"}
             
        os.rename(old_path, new_path)
        return {"status": "ok", "message": f"Moved {filename} to {target_sub_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/upload")
async def api_upload_file(file: UploadFile = File(...), sub_path: str = "", project_id: str = "default"):
    """Saves a file directly to the workspace. Auto-indexes into project knowledge base for non-default projects."""
    try:
        import urllib.parse
        sub_path = urllib.parse.unquote(sub_path)
        base_dir = get_project_workspace(project_id)
        
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path))
        if not target_dir.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
             
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        filepath = os.path.abspath(os.path.join(target_dir, file.filename))
        if not filepath.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
        
        file_bytes = await file.read()
        with open(filepath, "wb") as f:
            f.write(file_bytes)

        # Auto-index into project knowledge base for all projects
        import asyncio
        asyncio.create_task(_auto_index_project_file(project_id, file.filename, filepath, file_bytes))

        audit_info("api.file", "file_uploaded", name=file.filename,
                    size_bytes=len(file_bytes), project_id=project_id)
        return {"status": "ok", "message": f"Uploaded {file.filename}"}
    except Exception as e:
        audit_info("api.file", "file_upload_failed", name=file.filename if file else "unknown",
                    error=str(e)[:120])
        return {"status": "error", "message": str(e)}


async def _auto_index_project_file(project_id: str, filename: str, filepath: str, file_bytes: bytes):
    """
    Background task: extract text from an uploaded file and index it into
    the project's Qdrant knowledge base.
    """
    import asyncio
    # Wait for file processor to finish
    await asyncio.sleep(3)
    
    text = ""
    ext = os.path.splitext(filename)[1].lower()
    
    try:
        # Try reading the processed cache — check both project-local and root workspace
        project_processed_dir = os.path.join(os.path.dirname(filepath), ".processed")
        root_processed_dir = os.path.join(os.path.abspath(str(WORKSPACE_DIR)), ".processed")
        
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
        if not text and ext in {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".xml", ".yaml", ".yml"}:
            try:
                text = file_bytes.decode("utf-8", errors="ignore")
            except Exception:
                pass
        
        if text and len(text.strip()) > 50:
            await project_manager.add_knowledge(project_id, filename, text.strip())
            logger.info("Auto-indexed %s into project %s knowledge base", filename, project_id)
        else:
            logger.info("Skipped indexing %s — no extractable text", filename)
    except Exception as e:
        logger.error("Failed to auto-index %s: %s", filename, e)

    return {"status": "ok"}
@app.post("/api/folders")
async def api_create_folder(body: dict):
    """Creates a new directory in the workspace."""
    try:
        import urllib.parse
        name = body.get("name")
        sub_path = urllib.parse.unquote(body.get("sub_path", ""))
        project_id = body.get("project_id", "default")
        
        if not name:
             return {"status": "error", "message": "Folder name is required"}
             
        base_dir = get_project_workspace(project_id)
        target_dir = os.path.abspath(os.path.join(base_dir, sub_path, name))
        if not target_dir.startswith(os.path.abspath(base_dir)):
             return {"status": "error", "message": "Access denied"}
             
        if os.path.exists(target_dir):
             return {"status": "error", "message": "Folder already exists"}
             
        os.makedirs(target_dir, exist_ok=True)
        return {"status": "ok", "message": f"Created folder {name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
    """Delete a project by its ID."""
    try:
        success = project_manager.delete_project(project_id)
        if success:
            return {"status": "ok"}
        else:
            return {"status": "error", "message": "Failed to delete project or cannot delete default project"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/projects/{project_id}/knowledge")
async def api_add_project_knowledge(project_id: str, body: dict):
    """
    Index a file's text content into the project's Qdrant knowledge base.
    Body: { "filename": "report.pdf", "content": "extracted text..." }
    """
    filename = body.get("filename", "")
    content = body.get("content", "")
    if not filename or not content:
        return {"status": "error", "message": "filename and content are required"}
    
    # Truncate very large content to avoid overwhelming Qdrant
    max_chars = 20_000
    if len(content) > max_chars:
        content = content[:max_chars]
    
    success = await project_manager.add_knowledge(project_id, filename, content)
    if success:
        return {"status": "ok", "message": f"Indexed {filename} into project knowledge base"}
    return {"status": "error", "message": "Failed to index — Mem0/Qdrant may be unavailable"}


@app.delete("/api/projects/{project_id}/knowledge/{filename}")
async def api_remove_project_knowledge(project_id: str, filename: str):
    """Remove a knowledge file from the project's tracking."""
    import urllib.parse
    filename = urllib.parse.unquote(filename)
    project_manager.remove_knowledge(project_id, filename)
    return {"status": "ok"}



@app.get("/api/history/{thread_id}")
async def api_get_history(thread_id: str):
    """Retrieves full chat history for a specific thread."""
    try:
        agent = app.state.agent
        if not agent:
            return []
            
        config = {"configurable": {"thread_id": thread_id}}
        state = await agent.aget_state(config)
        
        if not state or not state.values:
            return []
            
        messages = state.values.get("messages", [])
        return [serialize_message(m) for m in messages]
    except Exception as e:
        logger.warning("Failed to fetch history: %s", e)
        return []


@app.put("/api/projects/{project_id}")
async def api_update_project(project_id: str, body: dict):
    return project_manager.update_project(project_id, **body)


def _stringify_lc_message_content(content) -> str:
    """Flatten LangChain message content (str or list of blocks) for JSON/UI."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if text is not None:
                    parts.append(str(text))
                else:
                    nested = block.get("content")
                    if nested is not None:
                        parts.append(_stringify_lc_message_content(nested))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def serialize_message(msg):
    """
    Converts Langchain BaseMessage objects into raw UI-friendly dictionaries
    so they can be safely streamed over WebSockets to a React client.
    """
    if isinstance(msg, AIMessage):
        content_ui = _stringify_lc_message_content(msg.content)
    else:
        content_ui = msg.content

    serialized = {"type": msg.type, "content": content_ui}

    if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
        serialized["tool_calls"] = msg.tool_calls

    if isinstance(msg, ToolMessage):
        serialized["tool_name"] = msg.name
        serialized["tool_call_id"] = msg.tool_call_id
        # Truncate content for UI readability/performance if too large
        if isinstance(msg.content, str) and len(msg.content) > 500:
            serialized["content"] = msg.content[:500] + "\n\n... [Content Truncated for UI] ..."

    return serialized


def serialize_interrupt_item(item):
    """Convert LangGraph interrupt payload items into JSON-safe values."""
    value = getattr(item, "value", item)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        interrupt_type = value.get("type", "")

        if interrupt_type == "security_approval_required":
            sensitive_calls = value.get("sensitive_tool_calls") or []
            primary_call = sensitive_calls[0] if isinstance(sensitive_calls, list) and sensitive_calls else {}
            tool_name = str(primary_call.get("name", "unknown"))
            tool_args = _stringify_tool_input(primary_call.get("args"))
            enriched = dict(value)
            enriched["risk_label"] = str(primary_call.get("risk_label") or "sensitive_tool_execution")
            enriched["risk_confidence"] = float(primary_call.get("risk_confidence", 0.95))
            if primary_call.get("risk_rationale"):
                enriched["risk_rationale"] = str(primary_call.get("risk_rationale"))
            if primary_call.get("remediation_hint"):
                enriched["remediation_hint"] = str(primary_call.get("remediation_hint"))
            enriched["tool_name"] = tool_name
            enriched["tool_args"] = tool_args
            enriched["sensitive_count"] = len(sensitive_calls) if isinstance(sensitive_calls, list) else 0
            return enriched

        if interrupt_type == "plan_review_required":
            # Pass through with enriched context fields for frontend rendering
            enriched = dict(value)
            return enriched

        if interrupt_type == "scope_clarification_required":
            enriched = dict(value)
            return enriched

        if interrupt_type == "ask_user":
            # Pass through; may already have enriched fields from router
            return dict(value)

        return value
    if isinstance(value, list):
        return value
    return str(value)


def _stringify_tool_input(value) -> str | None:
    """Convert tool args payload into a compact UI-safe string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _tool_status_from_content(content: str) -> str:
    """Best-effort status detection for tool outputs."""
    if not isinstance(content, str):
        return "success"
    lowered = content.lower()
    error_hints = (
        "execution error",
        "sandbox error",
        "error:",
        "traceback",
        "exception",
        "permission denied",
        "command not found",
    )
    return "error" if any(h in lowered for h in error_hints) else "success"


_TOOL_DESTRUCTIVE_RE = re.compile(r"(?:\brm\s+-rf\b|\bdrop\b|\bdelete\b|\btruncate\b)", re.IGNORECASE)
_TOOL_NETWORK_RE = re.compile(r"(?:\bcurl\b|\bwget\b|\bhttp[s]?://\b|\bscp\b|\bssh\b)", re.IGNORECASE)
_TOOL_PRIV_RE = re.compile(r"(?:\bsudo\b|\bchmod\b|\bchown\b)", re.IGNORECASE)


def _tool_risk_metadata(tool_name: str, tool_input: str | None) -> dict | None:
    """Best-effort risk metadata for pre-execution tool visibility."""
    hay = f"{tool_name} {tool_input or ''}"
    if _TOOL_DESTRUCTIVE_RE.search(hay) or tool_name == "delete_workspace_file":
        return {
            "risk_label": "destructive_action",
            "risk_confidence": 0.98,
            "risk_rationale": "Delete/drop semantics detected before tool execution.",
            "remediation_hint": "Confirm target path and snapshot before continuing.",
        }
    if _TOOL_NETWORK_RE.search(hay):
        return {
            "risk_label": "network_exfiltration",
            "risk_confidence": 0.9,
            "risk_rationale": "Outbound network indicators detected in tool arguments.",
            "remediation_hint": "Verify destination allowlist and redact sensitive data.",
        }
    if _TOOL_PRIV_RE.search(hay):
        return {
            "risk_label": "privilege_escalation",
            "risk_confidence": 0.92,
            "risk_rationale": "Privilege-elevation markers detected in tool arguments.",
            "remediation_hint": "Run with least privilege and minimal scope.",
        }
    return None


class GraphSession:
    """Manages the graph execution for a specific thread in a background task."""
    def __init__(self, thread_id, agent, sessions_registry):
        self.thread_id = thread_id
        self.agent = agent
        self.sessions_registry = sessions_registry
        self.listeners = set() # asyncio.Queues
        self.task = None
        self.event_buffer = [] # Store all events for the current turn
        self.is_running = False
        self.last_project_id = "default"

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
        return self.is_running or len(self.listeners) > 0

    async def start_run(self, input_data, config, correlation_id=None):
        if self.is_running:
            return
        if isinstance(input_data, dict):
            pid = input_data.get("project_id")
            if pid is not None:
                self.last_project_id = normalize_project_id(pid)
        self.event_buffer = []
        self.is_running = True
        self.task = asyncio.create_task(self._execute(input_data, config, correlation_id))

    async def _execute(self, input_data, config, correlation_id=None):
        # Propagate thread_id into audit context for this graph run
        from src.config.audit_log import set_thread_id
        set_thread_id(self.thread_id)

        token = set_active_project_for_run(self.last_project_id)
        try:
            # Initial status
            start_msg = {"type": "status", "content": "reasoning"}
            self.event_buffer.append((start_msg, correlation_id))
            for q in list(self.listeners):
                await q.put((start_msg, correlation_id))

            async for event in self.agent.astream_events(input_data, config=config, version="v2"):
                self.event_buffer.append((event, correlation_id))
                # Broadcast
                for q in list(self.listeners):
                    await q.put((event, correlation_id))
        except Exception as e:
            import traceback
            traceback.print_exc()
            err_msg = {"type": "error", "content": f"Graph Execution Error: {str(e)}"}
            self.event_buffer.append((err_msg, correlation_id))
            for q in list(self.listeners):
                await q.put((err_msg, correlation_id))
        finally:
            reset_active_project(token)
            self.is_running = False
            # Final status update
            done_msg = {"type": "status", "content": "idle"}
            logger.debug("GraphSession._execute for thread %s FINISHED. Putting done_msg.", self.thread_id)
            self.event_buffer.append((done_msg, correlation_id))
            for q in list(self.listeners):
                await q.put((done_msg, correlation_id))

            
            # If no one is listening anymore, remove from registry
            if not self.listeners and self.thread_id in self.sessions_registry:
                del self.sessions_registry[self.thread_id]


@app.websocket("/ws/chat/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    await websocket.accept()
    connected_websockets.add(websocket) # Track connection
    
    config = {"configurable": {"thread_id": thread_id}}
    agent = websocket.app.state.agent
    
    if not agent:
        await websocket.close(code=1008, reason="Agent not initialized")
        return

    logger.info("WebSocket accepted for thread=%s", thread_id)
    audit_info("api.ws", "ws_connected", thread_id=thread_id)

    # Get or create session
    sessions = websocket.app.state.sessions
    if thread_id not in sessions:
        sessions[thread_id] = GraphSession(thread_id, agent, sessions)
    session = sessions[thread_id]

    # Task to listen to the session events and send them to the websocket
    async def forward_events():
        q = await session.add_listener()
        pending_tool_calls: dict[str, dict] = {}
        running_tool_calls: dict[str, dict] = {}
        _stream_echo_buffer = ""  # Accumulates streaming text to detect system instruction echo
        try:
            while True:
                item = await q.get()
                if item is None: # Sentinel
                    break
                event, correlation_id = item if isinstance(item, tuple) else (item, None)
                
                async def _send_ws(payload):
                    if correlation_id and isinstance(payload, dict):
                        payload["correlation_id"] = correlation_id
                    await websocket.send_json(payload)
            
                # Handle standard LangGraph events vs our custom wrapped events
                if isinstance(event, dict) and "event" in event:
                    kind = event.get("event")
                    metadata = event.get("metadata", {})
                    node = metadata.get("langgraph_node")
                
                    # Debug print
                    if kind in ["on_chain_start", "on_chain_end"]:
                        logger.debug("Event=%s | Node=%s", kind, node)
                    elif kind == "on_chat_model_stream":
                        logger.debug("Stream | Node=%s", node)

                    if kind == "on_chain_start" and (node in {"tool_action", "tools"} or metadata.get("langgraph_step") == "tools"):
                        for tool_call_id, tc in list(pending_tool_calls.items()):
                            tool_name = str(tc.get("tool_name") or "unknown_tool")
                            tool_input = tc.get("tool_input")
                            started_at = asyncio.get_running_loop().time()
                            running_tool_calls[tool_call_id] = {
                                "tool_name": tool_name,
                                "started_at": started_at,
                            }
                            await _send_ws(
                                {
                                    "type": "tool_execution",
                                    "status": "running",
                                    "tool_name": tool_name,
                                    "tool_call_id": tool_call_id or None,
                                    "input": tool_input,
                                    **(_tool_risk_metadata(tool_name, tool_input) or {}),
                                }
                            )
                        pending_tool_calls.clear()

                    elif kind == "on_chain_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if isinstance(chunk, dict) and "__interrupt__" in chunk:
                            interrupts = [serialize_interrupt_item(i) for i in chunk.get("__interrupt__", [])]
                            pending_tool_calls.clear()
                            await _send_ws({"type": "interrupt", "interrupts": interrupts})

                    elif kind == "on_chat_model_stream" and node in ["simple", "complex_llm"]:
                        chunk = event["data"]["chunk"]
                        if chunk.content:
                            # Stream deltas may be str or list[content_block]; stringify like finalize path.
                            text = _stringify_lc_message_content(chunk.content)
                            # Skip empty chunks and internal reminders
                            if not text or text.strip().startswith("[Internal reminder"):
                                continue
                            # Suppress system instruction echo in streaming chunks.
                            # Some models (Gemma) regurgitate the folded system prompt as output.
                            # Accumulate text until we've passed the echo block, then start sending.
                            _stream_echo_buffer += text
                            if "[SYSTEM INSTRUCTIONS BEGIN]" in _stream_echo_buffer:
                                # Still inside the system echo block — keep buffering but don't send
                                if "[SYSTEM INSTRUCTIONS END]" in _stream_echo_buffer:
                                    # End marker found — extract everything after the end marker
                                    idx = _stream_echo_buffer.find("[SYSTEM INSTRUCTIONS END]")
                                    after = _stream_echo_buffer[idx + len("[SYSTEM INSTRUCTIONS END]"):].lstrip()
                                    _stream_echo_buffer = ""  # Reset buffer
                                    if after:
                                        await _send_ws({"type": "chunk", "content": after})
                                # else: still buffering, don't send yet
                            else:
                                # Past the echo block or never started — send normally
                                await _send_ws({"type": "chunk", "content": text})
                        
                    elif kind == "on_chain_end":
                        output = event["data"].get("output")

                        # Emit context_summarized event when auto_summarize node completes
                        if node == "auto_summarize":
                            if isinstance(output, dict):
                                ctx_event = output.get("context_summarized_event")
                                if ctx_event and isinstance(ctx_event, dict):
                                    await _send_ws(ctx_event)

                        # Emit memory_updated when memory_write node completes with invalidation
                        if node == "memory_write":
                            if isinstance(output, dict) and output.get("memory_invalidated"):
                                await _send_ws({
                                    "type": "memory_updated",
                                    "thread_id": thread_id,
                                })

                        if isinstance(output, dict) and "__interrupt__" in output:
                            interrupts = [serialize_interrupt_item(i) for i in output.get("__interrupt__", [])]
                            await _send_ws({"type": "interrupt", "interrupts": interrupts})

                        # Emit router_info event when router node completes
                        if node == "router":
                            router_metadata = None
                            if isinstance(output, dict):
                                router_metadata = output.get("router_metadata")
                            # If output contains nested state, check there too
                            if not router_metadata and isinstance(output, dict):
                                inner = output.get("state") or output.get("agent_state")
                                if isinstance(inner, dict):
                                    router_metadata = inner.get("router_metadata")
                            if not router_metadata:
                                logger.debug("[ws] router on_chain_end: output type=%s, has_router_metadata=%s",
                                    type(output).__name__, isinstance(output, dict) and "router_metadata" in output)
                            if router_metadata and isinstance(router_metadata, dict):
                                safe_metadata = {}
                                for k, v in router_metadata.items():
                                    try:
                                        json.dumps({k: v})
                                        safe_metadata[k] = v
                                    except (TypeError, ValueError):
                                        logger.warning("[ws] Skipping non-serializable router_metadata field: %s", k)
                                if safe_metadata:
                                    # Derive a model name from the route for the frontend
                                    route = safe_metadata.get("route", "")
                                    if route == "simple":
                                        model = "small-local"
                                    elif route.startswith("complex-"):
                                        variant = route.replace("complex-", "")
                                        model = f"medium-{variant}"
                                    else:
                                        model = "unknown"
                                    await _send_ws({
                                        "type": "router_info",
                                        "metadata": safe_metadata,
                                        "model": model,
                                    })

                        if node in ["simple", "complex_llm"]:
                            if isinstance(output, dict) and "messages" in output:
                                messages = output.get("messages") or []
                                if not messages:
                                    continue
                                msg = messages[0]
                                tc_list = list(getattr(msg, "tool_calls", None) or [])
                                text_for_ui = (
                                    _stringify_lc_message_content(msg.content).strip()
                                    if isinstance(msg, AIMessage)
                                    else str(getattr(msg, "content", "") or "").strip()
                                )

                                # Extract model provenance and token usage from node output
                                _node_model_used = output.get("model_used")
                                _node_token_usage = output.get("api_tokens_used")
                                _node_fallback_chain = output.get("fallback_chain")

                                # Send model_info event so frontend can show badge
                                if _node_model_used:
                                    model_info_payload: dict = {
                                        "type": "model_info",
                                        "model": _node_model_used,
                                        "swapping": False,
                                    }
                                    if _node_fallback_chain and isinstance(_node_fallback_chain, list):
                                        model_info_payload["fallback_chain"] = _node_fallback_chain
                                    # Include cloud brief telemetry if present
                                    if output.get("cloud_brief_tokens_est"):
                                        model_info_payload["cloud_brief_tokens_est"] = output["cloud_brief_tokens_est"]
                                    if output.get("anonymization_placeholders_count") is not None:
                                        model_info_payload["anonymization_placeholders_count"] = output["anonymization_placeholders_count"]
                                    await _send_ws(model_info_payload)
                                elif _node_fallback_chain and isinstance(_node_fallback_chain, list):
                                    # No model_used but fallback chain exists (e.g. tools_off fallback)
                                    await _send_ws({
                                        "type": "model_info",
                                        "model": "unknown",
                                        "swapping": False,
                                        "fallback_chain": _node_fallback_chain,
                                    })

                                # Accumulate cloud token usage into session totals
                                if _node_token_usage and isinstance(_node_token_usage, dict):
                                    _session_usage["prompt_tokens"] += int(_node_token_usage.get("prompt_tokens", 0))
                                    _session_usage["completion_tokens"] += int(_node_token_usage.get("completion_tokens", 0))
                                    _session_usage["total_tokens"] = _session_usage["prompt_tokens"] + _session_usage["completion_tokens"]

                                if tc_list:
                                    # Include reasoning / pre-tool text in the same payload (serialize_message flattens content).
                                    # Skip internal reminders leaking through tool-call AIMessages.
                                    if text_for_ui and not text_for_ui.startswith("[Internal reminder"):
                                        aw_msg = serialize_message(msg)
                                        if _node_model_used:
                                            aw_msg["model_used"] = _node_model_used
                                        if _node_token_usage:
                                            aw_msg["token_usage"] = _node_token_usage
                                        await _send_ws({"type": "assistant.message", "message": aw_msg})
                                    for tc in tc_list:
                                        tool_call_id = str(tc.get("id") or tc.get("tool_call_id") or f"pending-{len(pending_tool_calls)+1}")
                                        tool_name = str(tc.get("name") or "unknown_tool")
                                        tool_input = _stringify_tool_input(tc.get("args"))
                                        pending_tool_calls[tool_call_id] = {
                                            "tool_name": tool_name,
                                            "tool_input": tool_input,
                                        }
                                if text_for_ui and not tc_list:
                                    # Final assistant text after tools (or non-streaming turns). Without this,
                                    # the UI only saw chunks; if streaming missed events, the answer was blank.
                                    final_msg = serialize_message(msg)
                                    if _node_model_used:
                                        final_msg["model_used"] = _node_model_used
                                    if _node_token_usage:
                                        final_msg["token_usage"] = _node_token_usage
                                    await _send_ws({"type": "assistant.message", "message": final_msg})
                                elif not tc_list:
                                    # text_for_ui is empty (e.g. _clean_response stripped system echo leaving nothing).
                                    # Fallback: extract raw content after system markers from the uncut message.
                                    raw_content = str(getattr(msg, "content", "") or "")
                                    if "[SYSTEM INSTRUCTIONS END]" in raw_content:
                                        idx = raw_content.find("[SYSTEM INSTRUCTIONS END]") + len("[SYSTEM INSTRUCTIONS END]")
                                        after = raw_content[idx:].strip()
                                        if after:
                                            fallback_msg = {"type": msg.type, "content": after}
                                            if _node_model_used:
                                                fallback_msg["model_used"] = _node_model_used
                                            await _send_ws({"type": "assistant.message", "message": fallback_msg})
                        elif node is None or node not in {"simple", "complex_llm", "tool_action", "tools", "auto_summarize", "memory_write", "router"}:
                            # Catch-all: root-level or unknown node with AIMessage content
                            if isinstance(output, dict) and "messages" in output:
                                msgs_ = output.get("messages") or []
                                if msgs_ and isinstance(msgs_[0], AIMessage):
                                    raw = str(msgs_[0].content or "").strip()
                                    if raw and not raw.startswith("[Internal reminder"):
                                        await _send_ws({"type": "assistant.message", "message": serialize_message(msgs_[0])})
                        elif node in {"tool_action", "tools"} or metadata.get("langgraph_step") == "tools":
                            if isinstance(output, dict) and "messages" in output:
                                for msg in output["messages"]:
                                    if isinstance(msg, ToolMessage):
                                        tool_call_id = str(getattr(msg, "tool_call_id", "") or "")
                                        stored = running_tool_calls.pop(tool_call_id, None) if tool_call_id else None
                                        tool_name = str(getattr(msg, "name", "") or (stored or {}).get("tool_name") or "unknown_tool")
                                        started_at = (stored or {}).get("started_at")
                                        duration = None
                                        if started_at is not None:
                                            duration = max(0.0, asyncio.get_running_loop().time() - float(started_at))
                                        content = str(getattr(msg, "content", "") or "")
                                        status = _tool_status_from_content(content)
                                        await _send_ws(
                                            {
                                                "type": "tool_execution",
                                                "status": status,
                                                "tool_name": tool_name,
                                                "tool_call_id": tool_call_id or None,
                                                "output": content if status == "success" else None,
                                                "error": content if status == "error" else None,
                                                "duration": duration,
                                            }
                                        )
                                    else:
                                        # Skip internal assistant reminders and empty messages.
                                        content = str(getattr(msg, "content", "") or "").strip()
                                        if not content or content.startswith("[Internal reminder"):
                                            continue
                                        await _send_ws({"type": "assistant.message", "message": serialize_message(msg)})
                else:
                    # Our custom events (status, error, etc)
                    logger.debug("Custom Event: %s", event)
                    await _send_ws(event)
        except WebSocketDisconnect:
            logger.debug("Forwarder disconnected")
            pass
        except Exception as e:
            logger.error("Error in event forwarder: %s", e)
        finally:
            session.remove_listener(q)
            if not session.is_active() and thread_id in sessions:
                del sessions[thread_id]



    # Start the event forwarder task
    forwarder_task = asyncio.create_task(forward_events())

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Handle explicit STOP command to cancel executing GraphSession
            if payload.get("type") == "stop":
                sessions = websocket.app.state.sessions
                if thread_id in sessions:
                    session = sessions[thread_id]
                    if session.task and not session.task.done():
                        session.task.cancel()
                        session.is_running = False
                continue

            if payload.get("type") == "security_approval":
                approved = bool(payload.get("approved"))
                await session.start_run(
                    Command(resume={"approved": approved}),
                    config=config,
                    correlation_id=payload.get("correlation_id")
                )
                continue

            if payload.get("type") == "ask_user_response":
                answer = payload.get("answer", "")
                await session.start_run(
                    Command(resume={"answer": answer}),
                    config=config,
                    correlation_id=payload.get("correlation_id")
                )
                continue

            if payload.get("type") == "plan_review_response":
                approved = bool(payload.get("approved"))
                feedback = payload.get("feedback", "")
                await session.start_run(
                    Command(resume={"approved": approved, "feedback": feedback}),
                    config=config,
                    correlation_id=payload.get("correlation_id")
                )
                continue

            user_input = payload.get("message", "")
            files = payload.get("files", [])
            payload_mode = payload.get("mode", "tools_on")
            web_search_enabled = payload.get("web_search_enabled")
            if web_search_enabled is None:
                web_search_enabled = True
            response_style = (payload.get("response_style") or "normal").strip()
            project_id = payload.get("project_id", "default")
            persona_id = payload.get("persona_id", "default")
            base_dir = get_project_workspace(project_id)

            # Handle Workspace References
            for f in files:
                if f.get("type") == "workspace_ref":
                    prompt_path = f.get("path")
                    user_input += f"\n\n[Attached Workspace File: {prompt_path}]"

            # Save uploaded files into the agent workspace so tools can read them
            for f in files:
                if f.get("type") == "workspace_ref":
                    continue # Skip saving workspace references they already exist on disk
                name = f.get("name")
                data_b64 = f.get("data")
                if name and data_b64:
                    try:
                        import base64
                        import urllib.parse
                        raw_bytes = base64.b64decode(data_b64)
                        
                        safe_name = urllib.parse.unquote(name).lstrip("/")
                        filepath = os.path.abspath(os.path.join(base_dir, safe_name))
                        if not filepath.startswith(os.path.abspath(base_dir)):
                             logger.warning("Access denied for file %s (outside workspace)", name)
                             continue
                             
                        with open(filepath, "wb") as file_out:
                            file_out.write(raw_bytes)
                        logger.info("Saved file to %s", filepath)
                    except Exception as e:
                        logger.error("Failed to save file %s: %s", name, e)

            # On first user message in a thread, register the chat in the project
            if thread_id not in sessions or not sessions[thread_id].event_buffer:
                chat_id = thread_id
                file_names = [f.get("name", "") for f in files if f.get("name")]
                try:
                    title = await generate_chat_title_router_llm(user_input[:1000], file_names=file_names)
                except Exception:
                    title = ""
                # Register chat in project manager (idempotent — dedups by chat_id)
                import time as time_module
                project_manager.add_chat_to_project(project_id, {
                    "id": chat_id,
                    "name": title or "New Chat",
                    "created_at": time_module.time(),
                })
                logger.info("Registered chat %s in project %s (title=%s)", chat_id, project_id, title or "New Chat")

            message_content = await build_message_content(user_input, files)
            if not message_content:
                continue

            # Start the graph run in the session (background)
            await session.start_run(
                {
                    "messages": [HumanMessage(content=message_content)],
                    "mode": payload_mode,
                    "web_search_enabled": bool(web_search_enabled),
                    "response_style": response_style,
                    "project_id": project_id,
                    "persona_id": persona_id,
                    "thread_id": thread_id,
                },
                config=config,
                correlation_id=payload.get("correlation_id"),
            )

    except WebSocketDisconnect:
        logger.info("Client disconnected from thread: %s", thread_id)
        audit_info("api.ws", "ws_disconnected", thread_id=thread_id)
    finally:
        # We don't cancel the session task here! It continues in background.
        connected_websockets.discard(websocket) # Remove from active list
        # But we should stop the forwarder.
        forwarder_task.cancel()
        # The forwarder cleanup will check if it should delete the session.


async def build_message_content(text: str, files: list):
    """
    Builds the message content block for LangChain, supporting:
    - Images: forwarded as image_url for multimodal vision models
    - Text PDFs: text extracted via PyMuPDF and injected
    - Scanned PDFs: each page rendered as image and forwarded to the vision model
    - Code/text files: decoded and injected as a fenced code block
    """
    import base64
    from io import BytesIO

    # Scale inline PDF excerpt to leave enough room for the response.
    # Context window is configured in defaults.yaml.
    # Rough heuristic: 3.5 chars per token.
    MAX_INLINE_PDF_CHARS = int(config.get("tool_output.max_inline_pdf_chars", 16000))
    
    content_parts = []
    text_injections = []
    has_multimodal = False

    for f in files:
        mime = f.get("type", "")
        data_b64 = f.get("data", "")
        name = f.get("name", "file")
        
        try:
            raw_bytes = base64.b64decode(data_b64)
        except Exception:
            continue
        
        if mime.startswith("image/"):
            # Regular image — forward directly to vision model
            has_multimodal = True
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{data_b64}"}
            })
        
        elif mime == "application/pdf" or name.lower().endswith(".pdf"):
            logger.info("Uploaded '%s'. Extracting text for chat context.", name)
            # extract_pdf_text defined below — called after module load
            pdf_text = await asyncio.to_thread(extract_pdf_text, raw_bytes)
            pdf_text = (pdf_text or "").strip()
            if len(pdf_text) >= 200:
                excerpt = pdf_text[:MAX_INLINE_PDF_CHARS]
                if len(pdf_text) > MAX_INLINE_PDF_CHARS:
                    excerpt += (
                        "\n\n[PDF truncated in this prompt for size; full file is on disk — "
                        "call read_workspace_file as a real tool if you need the rest.]"
                    )
                text_injections.append(
                    f"[Workspace file `{name}` — text extracted from PDF below. "
                    f"Use this to answer when it is enough; if not, call read_workspace_file with that path "
                    f"(function/tool call, not instructions to the user).]\n\n---\n{excerpt}\n---"
                )
            else:
                text_injections.append(
                    f"[Workspace file `{name}` — little or no extractable text in upload preview. "
                    f"You must invoke read_workspace_file for `{name}` as a tool/function call before answering.]"
                )

        else:
            # Text / code file
            logger.info("Uploaded '%s'. Adding workspace reference.", name)
            text_injections.append(
                f"[Workspace file `{name}` saved. Invoke read_workspace_file as a tool with that path if you need contents — "
                f"do not answer with only a suggestion to use the tool.]"
            )


    # Build final content
    if has_multimodal:
        # Multimodal message — prepend any text file injections
        for inj in text_injections:
            content_parts.insert(0, {"type": "text", "text": inj})
        if text:
            content_parts.append({"type": "text", "text": text})
        return content_parts if content_parts else None
    else:
        # Plain text message
        parts = text_injections[:]
        if text:
            parts.append(text)
        return "\n\n".join(parts) if parts else None


def extract_pdf_text(raw_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        try:
            pages_text = []
            for page in doc:
                pages_text.append(page.get_text())
        finally:
            doc.close()
        return "\n\n".join(pages_text)
    except Exception as e:
        logger.error("PyMuPDF text extraction failed: %s", e)
        return ""


def render_pdf_as_composite(raw_bytes: bytes, max_pages: int = 10) -> str | None:
    """
    Render ALL PDF pages and stitch them into a single tall composite JPEG.
    
    Since mlx_vlm vision models may struggle with multiple separate image_url entries,
    we sidestep the issue by combining all pages into ONE image. The model can still
    see and read all pages in a single pass.
    
    Constraints:
    - Each page is scaled to a fixed width of 392px (14×28 — a known-safe patch width)
    - Heights are rounded to nearest multiple of 28
    - Pages separated by a thin white divider line for visual clarity
    - Final composite W and H must both be multiples of 28
    
    Returns: base64-encoded JPEG string, or None on failure.
    """
    PATCH_SIZE = int(config.get("pdf_rendering.patch_size", 28))
    PAGE_WIDTH = int(config.get("pdf_rendering.page_width", 392))   # 14 × 28 — safe patch count
    DIVIDER_H = int(config.get("pdf_rendering.divider_height", 28))
    
    try:
        import fitz
        import base64
        from PIL import Image, ImageDraw
        from io import BytesIO
        
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        page_imgs = []
        
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            
            # Render at 1x
            pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Scale to fixed width, preserve aspect ratio
            w, h = img.size
            scale = PAGE_WIDTH / w
            new_h = int(h * scale)
            # Snap height to multiple of 28
            new_h = max(PATCH_SIZE, (new_h // PATCH_SIZE) * PATCH_SIZE)
            img = img.resize((PAGE_WIDTH, new_h), Image.LANCZOS)
            page_imgs.append(img)
            logger.debug("Rendered page %s as %sx%s", i+1, PAGE_WIDTH, new_h)
        
        if not page_imgs:
            return None
        
        # Stitch pages vertically with dividers
        divider = Image.new("RGB", (PAGE_WIDTH, DIVIDER_H), color=(220, 220, 220))
        total_h = sum(img.height for img in page_imgs) + DIVIDER_H * (len(page_imgs) - 1)
        # Snap total height to multiple of 28
        total_h = max(PATCH_SIZE, (total_h // PATCH_SIZE) * PATCH_SIZE)
        
        composite = Image.new("RGB", (PAGE_WIDTH, total_h), color=(255, 255, 255))
        y = 0
        for i, img in enumerate(page_imgs):
            composite.paste(img, (0, y))
            y += img.height
            if i < len(page_imgs) - 1:
                composite.paste(divider, (0, y))
                y += DIVIDER_H
        
        # Encode final composite
        buf = BytesIO()
        composite.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        logger.debug("Composite image: %sx%s (%s pages)", PAGE_WIDTH, total_h, len(page_imgs))
        return b64
        
    except Exception as e:
        logger.error("Composite rendering failed: %s", e)
        return None


def extract_text_file(name: str, mime: str, raw_bytes: bytes) -> str:
    """Decode a plain text or code file from raw bytes."""
    text_mimes = ["text/", "application/json", "application/xml", "application/javascript"]
    text_exts = [".py", ".js", ".ts", ".txt", ".md", ".csv", ".yaml", ".yml", ".sh", ".json", ".toml"]
    is_text = any(mime.startswith(m) for m in text_mimes) or any(name.lower().endswith(e) for e in text_exts)
    if is_text:
        try:
            return raw_bytes.decode("utf-8", errors="replace")[:int(config.get("file_decode.max_chars", 8000))]
        except Exception:
            return ""
    return ""


async def openai_stream_generator(lc_messages, project_id, persona_id, auto_approve_sensitive):
    """Generator for streaming OpenAI SSE format completion chunks."""
    import time
    import uuid
    import json
    
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_time = int(time.time())
    
    config = {"configurable": {"thread_id": f"api-{uuid.uuid4().hex[:8]}"}}
    inputs = {
        "messages": lc_messages,
        "project_id": project_id,
        "persona_id": persona_id,
        "mode": "api",
        "auto_approve_sensitive": auto_approve_sensitive,
    }
    
    try:
        async for event in app.state.agent.astream_events(inputs, config=config, version="v2"):
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
                            "model": "gemma-4",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None
                                }
                            ]
                        }
                        yield f"data: {json.dumps(chunk_payload, ensure_ascii=False)}\n\n"
                        
        # Final finish reason stop chunk
        stop_payload = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": "gemma-4",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
        yield f"data: {json.dumps(stop_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error("Error in OpenAI stream generator: %s", e)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@app.post("/v1/chat/completions")
async def api_openai_chat_completions(body: dict):
    """OpenAI-compatible local API completions endpoint."""
    import time
    import uuid
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from fastapi.responses import StreamingResponse
    
    # Extract request params
    messages = body.get("messages", [])
    model = body.get("model", "gemma-4")
    stream = bool(body.get("stream", False))
    project_id = body.get("project_id", "default")
    persona_id = body.get("persona_id", "default")
    auto_approve_sensitive = bool(body.get("auto_approve_sensitive", False))
    
    # Map messages to LangChain types
    lc_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        elif role == "system":
            lc_messages.append(SystemMessage(content=content))
            
    if stream:
        return StreamingResponse(
            openai_stream_generator(lc_messages, project_id, persona_id, auto_approve_sensitive),
            media_type="text/event-stream"
        )
        
    # Non-streaming invocation
    config = {"configurable": {"thread_id": f"api-{uuid.uuid4().hex[:8]}"}}
    inputs = {
        "messages": lc_messages,
        "project_id": project_id,
        "persona_id": persona_id,
        "mode": "api",
        "auto_approve_sensitive": auto_approve_sensitive,
    }
    
    try:
        output = await app.state.agent.ainvoke(inputs, config=config)
        
        # Extract assistant response
        assistant_content = ""
        if "messages" in output and output["messages"]:
            # Find the last AIMessage
            for msg in reversed(output["messages"]):
                if isinstance(msg, AIMessage):
                    assistant_content = _stringify_lc_message_content(msg.content).strip()
                    break
                    
        # OpenAI completion response schema
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        response_payload = {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_content
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": -1,
                "completion_tokens": -1,
                "total_tokens": -1
            }
        }
        return response_payload
    except Exception as e:
        logger.error("Error in non-streaming completions API: %s", e)
        return {"error": str(e)}
