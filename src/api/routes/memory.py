from fastapi import APIRouter
router = APIRouter()
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
from src.config.audit_log import audit_info, audit_debug
from src.config.config_loader import config
from src.config.logging_config import setup_logging
from src.agent.llm import LLMPool
from langchain_core.messages import HumanMessage
import asyncio as _asyncio
from src.config.log_middleware import AuditLogMiddleware
from src.agent.cloud_cost_tracker import get_cost_tracker
from src.agent.graph import _check_cloud_connectivity
from src.config.secret_store import verify_deepseek_api_key
import os
from src.hitl.fixtures import load_fixture
import asyncio
from src.config.audit_log import set_thread_id
import traceback
import base64
from io import BytesIO
import time
import uuid
import json


@router.get("/api/memories")
async def api_get_memories():
    return load_memories()



@router.post("/api/memories")
async def api_add_memory(body: dict):
    fact = body.get("fact")
    if not fact:
        return {"status": "error", "message": "Fact required"}
    result = save_memory(fact)
    return {"status": "ok", "message": result, "memories": load_memories()}



@router.delete("/api/memories")
async def api_delete_memory(body: dict):
    fact = body.get("fact")
    if not fact:
        return {"status": "error", "message": "Fact required"}
    success = delete_memory(fact)
    return {"status": "ok" if success else "error", "memories": load_memories()}



# ─── Mem0 LTM API endpoints ──────────────────────────────────────────

@router.get("/api/mem0/search")
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




@router.get("/api/mem0/count")
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




@router.post("/api/mem0/delete")
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




@router.post("/api/mem0/clear")
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




@router.post("/api/mem0/reset")
async def api_mem0_reset():
    """Reset ALL Mem0 memories (global). Use with caution."""
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available"}
    try:
        mem0_memory.reset()
        return {"status": "ok", "message": "All Mem0 memories reset"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


