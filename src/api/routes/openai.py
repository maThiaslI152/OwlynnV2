from fastapi import APIRouter
import logging
from src.api.shared import _stringify_lc_message_content

logger = logging.getLogger(__name__)
router = APIRouter()
from langchain_core.messages import HumanMessage, AIMessage
import time
import uuid


@router.post("/v1/chat/completions")
async def api_openai_chat_completions(body: dict):
    """OpenAI-compatible local API completions endpoint."""
    from langchain_core.messages import SystemMessage
    from fastapi.responses import StreamingResponse
    from src.api.server import openai_stream_generator

    # Extract request params
    messages = body.get("messages", [])
    model = body.get("model", "qwen2.5-3b")
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
            openai_stream_generator(
                lc_messages, project_id, persona_id, auto_approve_sensitive
            ),
            media_type="text/event-stream",
        )

    thread_id = body.get("thread_id") or f"api-{uuid.uuid4().hex[:8]}"
    from src.config.config_loader import config as app_config

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
        from src.api.server import app

        output = await app.state.agent.ainvoke(inputs, config=config)

        # Extract assistant response
        assistant_content = ""
        if "messages" in output and output["messages"]:
            # Find the last AIMessage
            for msg in reversed(output["messages"]):
                if isinstance(msg, AIMessage):
                    assistant_content = _stringify_lc_message_content(
                        msg.content
                    ).strip()
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
                    "message": {"role": "assistant", "content": assistant_content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": -1, "completion_tokens": -1, "total_tokens": -1},
        }
        return response_payload
    except Exception as e:
        logger.error("Error in non-streaming completions API: %s", e)
        return {"error": str(e)}
