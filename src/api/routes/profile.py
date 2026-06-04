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


@router.get("/api/profile")
async def api_get_profile():
    return get_profile()



@router.post("/api/profile")
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



@router.get("/api/persona")
async def api_get_persona():
    return get_persona()



@router.post("/api/persona")
async def api_update_persona(body: dict):
    for field, value in body.items():
        try:
            update_persona_field(field, value)
        except Exception as e:
            logger.warning("[persona] update failed for field %s: %s", field, e)
    return get_persona()



@router.get("/api/personas")
async def api_list_personas():
    """List all available personas (built-in + custom)."""
    from src.memory.persona_manager import list_personas
    return list_personas()



@router.post("/api/personas")
async def api_create_persona(body: dict):
    """Save a new custom persona definition."""
    from src.memory.persona_manager import save_custom_persona
    success = save_custom_persona(body)
    if success:
        return {"status": "ok", "message": f"Saved custom persona: {body.get('id')}"}
    return {"status": "error", "message": "Failed to save persona (ensure 'id' is unique and not a built-in)"}


