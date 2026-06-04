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



@router.post("/v1/chat/completions")
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
    thread_id = body.get("thread_id") or f"api-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "messages": lc_messages,
        "project_id": project_id,
        "persona_id": persona_id,
        "mode": "api",
        "auto_approve_sensitive": auto_approve_sensitive,
    }
    
    try:
        from src.api.server import app
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


