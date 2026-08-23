import logging
import secrets as _secrets

from fastapi import APIRouter, HTTPException, Request

from src.api.shared import _stringify_lc_message_content

logger = logging.getLogger(__name__)
router = APIRouter()
import time
import uuid

from langchain_core.messages import AIMessage, HumanMessage


def _verify_openai_token(request: Request) -> None:
    """Verify local run token for the /v1/ endpoint (outside /api/* middleware)."""
    from src.api.local_auth import get_local_run_token, is_loopback_client

    if not is_loopback_client(request):
        raise HTTPException(
            status_code=403, detail="API only accessible from localhost"
        )

    token = request.headers.get("X-Owlynn-Run-Token") or request.query_params.get(
        "token"
    )
    expected = get_local_run_token(request.app)
    if not token or not _secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=401, detail="Missing or invalid local run token"
        )


@router.post("/v1/chat/completions")
async def api_openai_chat_completions(body: dict, request: Request):
    """OpenAI-compatible local API completions endpoint."""
    _verify_openai_token(request)

    from fastapi.responses import StreamingResponse
    from langchain_core.messages import SystemMessage

    from src.api.server import openai_stream_generator

    # Extract request params
    messages = body.get("messages", [])
    from src.config.config_loader import config

    model = body.get("model") or config.get_main_model_name()
    stream = bool(body.get("stream", False))
    project_id = body.get("project_id", "default")
    persona_id = body.get("persona_id", "default")
    # Security: never accept auto_approve from the client — always require HITL
    auto_approve_sensitive = False

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
        "auto_approve_sensitive": False,
    }

    try:
        from src.api.server import app

        output = await app.state.agent.ainvoke(inputs, config=config)

        # Extract assistant response
        assistant_content = ""
        if output.get("messages"):
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
        return {"error": "Internal server error"}
