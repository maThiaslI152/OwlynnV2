"""WebSocket chat handler — streams LangGraph events to the frontend.

See docs/CHAT_PROTOCOL.md for event types and serialization contract.
"""

"""WebSocket chat handler — streaming events and HITL resume.

See docs/CHAT_PROTOCOL.md for the frontend event contract.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

import asyncio
import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.agent.routing.router import generate_chat_title_router_llm
from src.api.controllers.graph_session import GraphSession
from src.api.controllers.ws_helpers import (
    _files_for_message_content,
    _is_tool_preamble_text,
    _last_ai_message,
    _sanitize_assistant_text,
    _stringify_tool_input,
    _tool_risk_metadata,
    _tool_status_from_content,
    serialize_interrupt_item,
)
from src.api.shared import (
    _session_usage,
    _stringify_lc_message_content,
    build_message_content,
    connected_websockets,
    emit_cloud_usage_events,
    logger,
    serialize_message,
)
from src.config.audit_log import audit_info
from src.memory.semantic_cache import check_semantic_cache, store_semantic_cache
from src.tools.notebook_libs import parse_chart_artifact


@router.websocket("/ws/chat/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    # ── Token-based authentication ──────────────────────────────────────
    import secrets as _secrets

    from src.api.local_auth import get_local_run_token

    token = websocket.query_params.get("token")
    expected = get_local_run_token(websocket.app)
    if not token or not _secrets.compare_digest(token, expected):
        await websocket.close(code=4001, reason="Authentication failed")
        return

    await websocket.accept()
    websocket.scope["thread_id"] = thread_id
    connected_websockets.add(websocket)  # Track connection

    from src.config.config_loader import config as app_config

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": int(app_config.get("complex.recursion_limit", 100)),
    }
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

    # Mutable container shared between the message-receive loop and forward_events
    # closure so that the forwarder can populate the semantic cache on 'idle'.
    _pending_cache: dict = {"prompt": None, "project_id": "default"}

    # Task to listen to the session events and send them to the websocket
    async def forward_events():
        q = await session.add_listener()
        pending_tool_calls: dict[str, dict] = {}
        running_tool_calls: dict[str, dict] = {}
        _stream_echo_buffer = (
            ""  # Accumulates streaming text to detect system instruction echo
        )
        last_model_used = None
        last_fallback_chain = None
        last_token_usage = None
        last_cloud_brief = None
        last_anonymization = None
        last_vision_intake = None
        last_vision_proxy = None
        _last_ai_text_for_cache: str | None = (
            None  # Tracks last AI reply text for cache storage
        )

        try:
            while True:
                item = await q.get()
                if item is None:  # Sentinel
                    break
                event, correlation_id = (
                    item if isinstance(item, tuple) else (item, None)
                )

                # Per-event error isolation: catch and skip bad events instead
                # of killing the entire forwarder coroutine.
                try:

                    async def _send_ws(payload):
                        if correlation_id and isinstance(payload, dict):
                            payload["correlation_id"] = correlation_id

                        try:
                            from src.api.ws.schemas import ServerEventAdapter

                            ServerEventAdapter.validate_python(payload)
                        except Exception as e:
                            logger.error(
                                f"WS Payload Drift Detected (Server -> Client): {e} | Payload: {payload}"
                            )

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

                        if kind == "on_chain_start" and (
                            node in {"tool_action", "tools"}
                            or metadata.get("langgraph_step") == "tools"
                        ):
                            for tool_call_id, tc in list(pending_tool_calls.items()):
                                tool_name = str(tc.get("tool_name") or "unknown_tool")
                                tool_input = tc.get("tool_input")
                                batch_id = tc.get("batch_id")
                                started_at = asyncio.get_running_loop().time()
                                running_tool_calls[tool_call_id] = {
                                    "tool_name": tool_name,
                                    "started_at": started_at,
                                    "batch_id": batch_id,
                                }
                                await _send_ws(
                                    {
                                        "type": "tool_execution",
                                        "status": "running",
                                        "tool_name": tool_name,
                                        "tool_call_id": tool_call_id or None,
                                        "input": tool_input,
                                        "batch_id": batch_id,
                                        **(
                                            _tool_risk_metadata(tool_name, tool_input)
                                            or {}
                                        ),
                                    }
                                )
                            pending_tool_calls.clear()

                        elif kind == "on_chain_stream":
                            chunk = event.get("data", {}).get("chunk")
                            if isinstance(chunk, dict) and "__interrupt__" in chunk:
                                interrupts = [
                                    serialize_interrupt_item(i)
                                    for i in chunk.get("__interrupt__", [])
                                ]
                                pending_tool_calls.clear()
                                await _send_ws(
                                    {"type": "interrupt", "interrupts": interrupts}
                                )

                        elif kind == "on_chat_model_stream" and node in [
                            "simple",
                            "complex_llm",
                            "coherence_retry",
                        ]:
                            if pending_tool_calls or running_tool_calls:
                                continue
                            chunk = event["data"]["chunk"]
                            if chunk.content:
                                # Stream deltas may be str or list[content_block]; stringify like finalize path.
                                text = _sanitize_assistant_text(
                                    _stringify_lc_message_content(chunk.content)
                                )
                                # Skip empty chunks and internal reminders
                                if not text or text.strip().startswith(
                                    "[Internal reminder"
                                ):
                                    continue
                                if _is_tool_preamble_text(text):
                                    continue
                                # Suppress system instruction echo in streaming chunks.
                                # Some models (Qwen) regurgitate the folded system prompt as output.
                                # Accumulate text until we've passed the echo block, then start sending.
                                _stream_echo_buffer += text
                                if "[SYSTEM INSTRUCTIONS BEGIN]" in _stream_echo_buffer:
                                    # Still inside the system echo block — keep buffering but don't send
                                    if (
                                        "[SYSTEM INSTRUCTIONS END]"
                                        in _stream_echo_buffer
                                    ):
                                        # End marker found — extract everything after the end marker
                                        idx = _stream_echo_buffer.find(
                                            "[SYSTEM INSTRUCTIONS END]"
                                        )
                                        after = _stream_echo_buffer[
                                            idx + len("[SYSTEM INSTRUCTIONS END]") :
                                        ].lstrip()
                                        _stream_echo_buffer = ""  # Reset buffer
                                        if after:
                                            await _send_ws(
                                                {"type": "chunk", "content": after}
                                            )
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
                                if isinstance(output, dict) and output.get(
                                    "memory_invalidated"
                                ):
                                    await _send_ws(
                                        {
                                            "type": "memory_updated",
                                        }
                                    )

                            # Emit response_coherence and calibrated model_info when coherence_check completes
                            if node == "coherence_check":
                                if isinstance(output, dict):
                                    confidence = output.get("response_confidence")
                                    coherence = output.get("response_coherence") or {}
                                    duration_ms = output.get("turn_duration_ms") or 0

                                    await _send_ws(
                                        {
                                            "type": "response_coherence",
                                            "coherent": coherence.get("coherent", True),
                                            "confidence": confidence,
                                            "duration_ms": duration_ms,
                                            "reason": coherence.get("reason", ""),
                                        }
                                    )

                                    # Signal that coherence_retry will run so the UI can
                                    # show a transient "Improving answer..." indicator.
                                    if (
                                        isinstance(confidence, (int, float))
                                        and float(confidence) < 0.4
                                    ):
                                        await _send_ws(
                                            {
                                                "type": "coherence_retry_started",
                                                "thread_id": thread_id,
                                                "attempt": 1,
                                                "original_confidence": confidence,
                                                "original_reason": coherence.get(
                                                    "reason", ""
                                                ),
                                            }
                                        )

                            # When coherence_retry completes, emit a completion event so
                            # the frontend can dismiss the transient retry indicator.
                            if node == "coherence_retry":
                                if isinstance(output, dict):
                                    await _send_ws(
                                        {
                                            "type": "coherence_retry_completed",
                                            "thread_id": thread_id,
                                            "attempt": output.get(
                                                "_coherence_retry_round"
                                            )
                                            or 1,
                                        }
                                    )

                                    if last_model_used:
                                        model_info_payload = {
                                            "type": "model_info",
                                            "model": last_model_used,
                                            "swapping": False,
                                            "response_confidence": confidence,
                                        }
                                        if last_fallback_chain:
                                            model_info_payload["fallback_chain"] = (
                                                last_fallback_chain
                                            )
                                        if last_cloud_brief:
                                            model_info_payload[
                                                "cloud_brief_tokens_est"
                                            ] = last_cloud_brief
                                        if last_anonymization is not None:
                                            model_info_payload[
                                                "anonymization_placeholders_count"
                                            ] = last_anonymization
                                        if last_token_usage:
                                            model_info_payload["token_usage"] = (
                                                last_token_usage
                                            )
                                        if last_vision_intake:
                                            model_info_payload["vision_intake_mode"] = (
                                                last_vision_intake
                                            )
                                        if last_vision_proxy:
                                            model_info_payload["vision_proxy_model"] = (
                                                last_vision_proxy
                                            )

                                        await _send_ws(model_info_payload)

                            if isinstance(output, dict) and "__interrupt__" in output:
                                interrupts = [
                                    serialize_interrupt_item(i)
                                    for i in output.get("__interrupt__", [])
                                ]
                                await _send_ws(
                                    {"type": "interrupt", "interrupts": interrupts}
                                )

                            # Emit router_info event when router node completes
                            if node == "router":
                                router_metadata = None
                                if isinstance(output, dict):
                                    router_metadata = output.get("router_metadata")
                                # If output contains nested state, check there too
                                if not router_metadata and isinstance(output, dict):
                                    inner = output.get("state") or output.get(
                                        "agent_state"
                                    )
                                    if isinstance(inner, dict):
                                        router_metadata = inner.get("router_metadata")
                                if not router_metadata:
                                    logger.debug(
                                        "[ws] router on_chain_end: output type=%s, has_router_metadata=%s",
                                        type(output).__name__,
                                        isinstance(output, dict)
                                        and "router_metadata" in output,
                                    )
                                if router_metadata and isinstance(
                                    router_metadata, dict
                                ):
                                    safe_metadata = {}
                                    for k, v in router_metadata.items():
                                        try:
                                            json.dumps({k: v})
                                            safe_metadata[k] = v
                                        except (TypeError, ValueError):
                                            logger.warning(
                                                "[ws] Skipping non-serializable router_metadata field: %s",
                                                k,
                                            )
                                    if safe_metadata:
                                        # Derive a model name from the route for the frontend
                                        route = safe_metadata.get("route", "")
                                        if route == "simple":
                                            model = "main-local"
                                        elif route == "complex-cloud":
                                            model = "large-cloud"
                                        elif route in (
                                            "complex-default",
                                            "complex-local",
                                        ):
                                            model = "main-local"
                                        elif route.startswith("complex-"):
                                            variant = route.replace("complex-", "")
                                            model = f"main-{variant}"
                                        else:
                                            model = "main-local"
                                        await _send_ws(
                                            {
                                                "type": "router_info",
                                                "metadata": safe_metadata,
                                                "model": model,
                                            }
                                        )

                            if node in ["simple", "complex_llm", "coherence_retry"]:
                                if node == "complex_llm":
                                    running_tool_calls.clear()
                                    pending_tool_calls.clear()
                                if isinstance(output, dict) and "messages" in output:
                                    messages = output.get("messages") or []
                                    msg = _last_ai_message(messages)
                                    if not msg:
                                        continue
                                    # Flush any buffered stream text (simple node may not emit chunks).
                                    if _stream_echo_buffer.strip():
                                        pending = _stream_echo_buffer
                                        _stream_echo_buffer = ""
                                        if "[SYSTEM INSTRUCTIONS END]" in pending:
                                            idx = pending.find(
                                                "[SYSTEM INSTRUCTIONS END]"
                                            )
                                            after = pending[
                                                idx + len("[SYSTEM INSTRUCTIONS END]") :
                                            ].lstrip()
                                            if after:
                                                await _send_ws(
                                                    {"type": "chunk", "content": after}
                                                )
                                        elif (
                                            "[SYSTEM INSTRUCTIONS BEGIN]" not in pending
                                        ):
                                            await _send_ws(
                                                {"type": "chunk", "content": pending}
                                            )
                                    tc_list = list(
                                        getattr(msg, "tool_calls", None) or []
                                    )
                                    text_for_ui = (
                                        _sanitize_assistant_text(
                                            _stringify_lc_message_content(msg.content)
                                        ).strip()
                                        if isinstance(msg, AIMessage)
                                        else _sanitize_assistant_text(
                                            str(getattr(msg, "content", "") or "")
                                        ).strip()
                                    )

                                    # Extract model provenance and token usage from node output
                                    _node_model_used = output.get("model_used")
                                    _node_token_usage = output.get("api_tokens_used")
                                    _node_fallback_chain = output.get("fallback_chain")

                                    if _node_model_used:
                                        last_model_used = _node_model_used
                                    if _node_fallback_chain:
                                        last_fallback_chain = _node_fallback_chain
                                    if _node_token_usage:
                                        last_token_usage = _node_token_usage
                                    if output.get("cloud_brief_tokens_est"):
                                        last_cloud_brief = output[
                                            "cloud_brief_tokens_est"
                                        ]
                                    if (
                                        output.get("anonymization_placeholders_count")
                                        is not None
                                    ):
                                        last_anonymization = output[
                                            "anonymization_placeholders_count"
                                        ]
                                    if output.get("vision_intake_mode"):
                                        last_vision_intake = output[
                                            "vision_intake_mode"
                                        ]
                                    if output.get("vision_proxy_model"):
                                        last_vision_proxy = output["vision_proxy_model"]

                                    # Send model_info event so frontend can show badge
                                    if _node_model_used:
                                        model_info_payload: dict = {
                                            "type": "model_info",
                                            "model": _node_model_used,
                                            "swapping": False,
                                        }
                                        if _node_fallback_chain and isinstance(
                                            _node_fallback_chain, list
                                        ):
                                            model_info_payload["fallback_chain"] = (
                                                _node_fallback_chain
                                            )
                                        # Include cloud brief telemetry if present
                                        if output.get("cloud_brief_tokens_est"):
                                            model_info_payload[
                                                "cloud_brief_tokens_est"
                                            ] = output["cloud_brief_tokens_est"]
                                        if (
                                            output.get(
                                                "anonymization_placeholders_count"
                                            )
                                            is not None
                                        ):
                                            model_info_payload[
                                                "anonymization_placeholders_count"
                                            ] = output[
                                                "anonymization_placeholders_count"
                                            ]
                                        if _node_token_usage and isinstance(
                                            _node_token_usage, dict
                                        ):
                                            model_info_payload["token_usage"] = (
                                                _node_token_usage
                                            )
                                        if output.get("vision_intake_mode"):
                                            model_info_payload["vision_intake_mode"] = (
                                                output["vision_intake_mode"]
                                            )
                                        if output.get("vision_proxy_model"):
                                            model_info_payload["vision_proxy_model"] = (
                                                output["vision_proxy_model"]
                                            )
                                        await _send_ws(model_info_payload)
                                    elif _node_fallback_chain and isinstance(
                                        _node_fallback_chain, list
                                    ):
                                        # No model_used but fallback chain exists (e.g. tools_off fallback)
                                        await _send_ws(
                                            {
                                                "type": "model_info",
                                                "model": "unknown",
                                                "swapping": False,
                                                "fallback_chain": _node_fallback_chain,
                                            }
                                        )

                                    # Emit cloud_fallback event when local fallback was used
                                    if output.get("cloud_fallback_used"):
                                        await _send_ws(
                                            {
                                                "type": "cloud_fallback",
                                                "reason": output.get(
                                                    "cloud_fallback_reason",
                                                    "cloud_unavailable",
                                                ),
                                                "fallback_model": _node_model_used
                                                or "local-fallback",
                                                "can_retry": True,
                                                "correlation_id": correlation_id,
                                            }
                                        )

                                    # Accumulate cloud token usage into session totals
                                    if _node_token_usage and isinstance(
                                        _node_token_usage, dict
                                    ):
                                        _session_usage["prompt_tokens"] += int(
                                            _node_token_usage.get("prompt_tokens", 0)
                                        )
                                        _session_usage["completion_tokens"] += int(
                                            _node_token_usage.get(
                                                "completion_tokens", 0
                                            )
                                        )
                                        _session_usage["prompt_cache_hit_tokens"] = int(
                                            _session_usage.get(
                                                "prompt_cache_hit_tokens", 0
                                            )
                                        ) + int(
                                            _node_token_usage.get(
                                                "prompt_cache_hit_tokens", 0
                                            )
                                        )
                                        _session_usage["prompt_cache_miss_tokens"] = (
                                            int(
                                                _session_usage.get(
                                                    "prompt_cache_miss_tokens", 0
                                                )
                                            )
                                            + int(
                                                _node_token_usage.get(
                                                    "prompt_cache_miss_tokens", 0
                                                )
                                            )
                                        )
                                        _session_usage["total_tokens"] = (
                                            _session_usage["prompt_tokens"]
                                            + _session_usage["completion_tokens"]
                                        )
                                        if _node_model_used == "large-cloud":
                                            await emit_cloud_usage_events(
                                                _send_ws,
                                                turn_usage=_node_token_usage,
                                                model_used=_node_model_used,
                                            )

                                    if tc_list:
                                        # Do not surface tool-only placeholders in chat; tool cards show progress.
                                        if (
                                            text_for_ui
                                            and not text_for_ui.startswith(
                                                "[Internal reminder"
                                            )
                                            and not _is_tool_preamble_text(text_for_ui)
                                        ):
                                            aw_msg = serialize_message(msg)
                                            if _node_model_used:
                                                aw_msg["model_used"] = _node_model_used
                                            if _node_token_usage:
                                                aw_msg["token_usage"] = (
                                                    _node_token_usage
                                                )
                                            await _send_ws(
                                                {
                                                    "type": "assistant.message",
                                                    "message": aw_msg,
                                                }
                                            )
                                        # Generate a batch_id to group parallel tool calls from the same LLM response
                                        batch_id = str(uuid.uuid4().hex[:12])
                                        for tc in tc_list:
                                            tool_call_id = str(
                                                tc.get("id")
                                                or tc.get("tool_call_id")
                                                or f"pending-{len(pending_tool_calls) + 1}"
                                            )
                                            tool_name = str(
                                                tc.get("name") or "unknown_tool"
                                            )
                                            tool_input = _stringify_tool_input(
                                                tc.get("args")
                                            )
                                            pending_tool_calls[tool_call_id] = {
                                                "tool_name": tool_name,
                                                "tool_input": tool_input,
                                                "batch_id": batch_id,
                                            }
                                    if text_for_ui and not tc_list:
                                        # Final assistant text after tools (or non-streaming turns). Without this,
                                        # the UI only saw chunks; if streaming missed events, the answer was blank.
                                        final_msg = serialize_message(msg)
                                        if _node_model_used:
                                            final_msg["model_used"] = _node_model_used
                                        if _node_token_usage:
                                            final_msg["token_usage"] = _node_token_usage
                                        await _send_ws(
                                            {
                                                "type": "assistant.message",
                                                "message": final_msg,
                                            }
                                        )
                                        # Track for semantic cache population on idle
                                        _last_ai_text_for_cache = text_for_ui
                                    elif not tc_list:
                                        # text_for_ui is empty (e.g. _clean_response stripped system echo leaving nothing).
                                        # Fallback: extract raw content after system markers from the uncut message.
                                        raw_content = _stringify_lc_message_content(
                                            getattr(msg, "content", "")
                                        )
                                        if "[SYSTEM INSTRUCTIONS END]" in raw_content:
                                            idx = raw_content.find(
                                                "[SYSTEM INSTRUCTIONS END]"
                                            ) + len("[SYSTEM INSTRUCTIONS END]")
                                            after = raw_content[idx:].strip()
                                            if after:
                                                fallback_msg = {
                                                    "type": msg.type,
                                                    "content": _sanitize_assistant_text(
                                                        after
                                                    ),
                                                }
                                                if _node_model_used:
                                                    fallback_msg["model_used"] = (
                                                        _node_model_used
                                                    )
                                                await _send_ws(
                                                    {
                                                        "type": "assistant.message",
                                                        "message": fallback_msg,
                                                    }
                                                )
                                        elif raw_content.strip():
                                            from src.agent.core.simple import (
                                                _clean_response,
                                            )

                                            cleaned = _clean_response(
                                                raw_content
                                            ).strip()
                                            cleaned = _sanitize_assistant_text(cleaned)
                                            if cleaned and not _is_tool_preamble_text(
                                                cleaned
                                            ):
                                                fallback_msg = serialize_message(
                                                    AIMessage(content=cleaned)
                                                )
                                                if _node_model_used:
                                                    fallback_msg["model_used"] = (
                                                        _node_model_used
                                                    )
                                                await _send_ws(
                                                    {
                                                        "type": "assistant.message",
                                                        "message": fallback_msg,
                                                    }
                                                )
                                        else:
                                            # All fallbacks exhausted — send empty message to clear streaming state
                                            await _send_ws(
                                                {
                                                    "type": "assistant.message",
                                                    "message": {
                                                        "type": "ai",
                                                        "content": "",
                                                        "id": str(
                                                            getattr(msg, "id", "") or ""
                                                        ),
                                                    },
                                                }
                                            )
                            elif node is None or node not in {
                                "simple",
                                "complex_llm",
                                "tool_action",
                                "tools",
                                "auto_summarize",
                                "memory_write",
                                "router",
                            }:
                                # Catch-all: root-level or unknown node with AIMessage content
                                if isinstance(output, dict) and "messages" in output:
                                    msgs_ = output.get("messages") or []
                                    if msgs_ and isinstance(msgs_[0], AIMessage):
                                        raw = str(msgs_[0].content or "").strip()
                                        if raw and not raw.startswith(
                                            "[Internal reminder"
                                        ):
                                            await _send_ws(
                                                {
                                                    "type": "assistant.message",
                                                    "message": serialize_message(
                                                        msgs_[0]
                                                    ),
                                                }
                                            )
                            elif (
                                node in {"tool_action", "tools"}
                                or metadata.get("langgraph_step") == "tools"
                            ):
                                if isinstance(output, dict) and "messages" in output:
                                    for msg in output["messages"]:
                                        if isinstance(msg, ToolMessage):
                                            tool_call_id = str(
                                                getattr(msg, "tool_call_id", "") or ""
                                            )
                                            stored = (
                                                running_tool_calls.pop(
                                                    tool_call_id, None
                                                )
                                                if tool_call_id
                                                else None
                                            )
                                            tool_name = str(
                                                getattr(msg, "name", "")
                                                or (stored or {}).get("tool_name")
                                                or "unknown_tool"
                                            )
                                            started_at = (stored or {}).get(
                                                "started_at"
                                            )
                                            duration = None
                                            if started_at is not None:
                                                duration = max(
                                                    0.0,
                                                    asyncio.get_running_loop().time()
                                                    - float(started_at),
                                                )
                                            content = str(
                                                getattr(msg, "content", "") or ""
                                            )
                                            status = _tool_status_from_content(content)
                                            batch_id = (stored or {}).get("batch_id")
                                            tool_payload: dict = {
                                                "type": "tool_execution",
                                                "status": status,
                                                "tool_name": tool_name,
                                                "tool_call_id": tool_call_id or None,
                                                "output": content
                                                if status == "success"
                                                else None,
                                                "error": content
                                                if status == "error"
                                                else None,
                                                "duration": duration,
                                                "batch_id": batch_id,
                                            }
                                            if status == "success" and tool_name in (
                                                "notebook_run",
                                                "write_workspace_file",
                                            ):
                                                chart_artifact = parse_chart_artifact(
                                                    content, session.last_project_id
                                                )
                                                if chart_artifact:
                                                    tool_payload["chart_artifact"] = (
                                                        chart_artifact
                                                    )
                                            await _send_ws(tool_payload)
                                            if tool_call_id:
                                                running_tool_calls.pop(
                                                    tool_call_id, None
                                                )
                                        else:
                                            # Skip internal assistant reminders and empty messages.
                                            content = str(
                                                getattr(msg, "content", "") or ""
                                            ).strip()
                                            if not content or content.startswith(
                                                "[Internal reminder"
                                            ):
                                                continue
                                            await _send_ws(
                                                {
                                                    "type": "assistant.message",
                                                    "message": serialize_message(msg),
                                                }
                                            )
                    else:
                        # Our custom events (status, error, etc)
                        logger.debug("Custom Event: %s", event)
                        # On idle: populate the semantic cache with the last AI answer (skip error messages)
                        if (
                            isinstance(event, dict)
                            and event.get("type") == "status"
                            and event.get("content") == "idle"
                            and _last_ai_text_for_cache
                            and not _last_ai_text_for_cache.startswith(
                                (
                                    "Cloud unavailable",
                                    "Unable to connect",
                                    "Error:",
                                    "Local fallback",
                                )
                            )
                            and _pending_cache.get("prompt")
                        ):
                            asyncio.create_task(
                                store_semantic_cache(
                                    _pending_cache["prompt"],
                                    _last_ai_text_for_cache,
                                    project_id=_pending_cache["project_id"],
                                )
                            )
                            _last_ai_text_for_cache = None
                            _pending_cache["prompt"] = None
                        await _send_ws(event)
                except Exception as e:
                    logger.error(
                        "Error processing event in forwarder: %s", e, exc_info=True
                    )
                    continue
        except WebSocketDisconnect:
            logger.debug("Forwarder disconnected")
        except Exception as e:
            logger.error("Error in event forwarder: %s", e)
        finally:
            session.remove_listener(q)
            if not session.is_active() and thread_id in sessions:
                del sessions[thread_id]

    # Start the event forwarder task
    forwarder_task = asyncio.create_task(forward_events())

    # Start conversation trace writer (persists per-thread JSONL)
    trace_task = None
    _trace_queue = None
    try:
        from src.config.trace_writer import get_trace_writer, trace_listener

        cfg_trace_enabled = get_trace_writer() is not None
    except Exception:
        cfg_trace_enabled = False

    if cfg_trace_enabled:
        try:
            _trace_queue = await session.add_listener()
            trace_task = asyncio.create_task(
                trace_listener(thread_id, _trace_queue, get_trace_writer())
            )
        except Exception:
            logger.debug("Trace writer init failed", exc_info=True)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)

                # Validate WS Payload Drift
                from src.api.ws.schemas import ClientEventAdapter

                ClientEventAdapter.validate_python(payload)

            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.error(
                    f"WS Payload Drift Detected (Client -> Server): {e} | Payload: {payload}"
                )
                # We log but continue, dropping the invalid payload or attempting to process it anyway
                # In strict mode, we might `continue` here to drop it, but we'll let it pass for now and rely on backend handlers to fail safely.

            # Handle explicit STOP command to cancel executing GraphSession
            if payload.get("type") == "stop":
                sessions = websocket.app.state.sessions
                if thread_id in sessions:
                    session = sessions[thread_id]
                    while not session._run_queue.empty():
                        try:
                            session._run_queue.get_nowait()
                            session._run_queue.task_done()
                        except asyncio.QueueEmpty:
                            break
                    if session.task and not session.task.done():
                        session.task.cancel()
                        session.is_running = False
                continue

            if payload.get("type") == "security_approval":
                approved = bool(payload.get("approved"))
                await session.start_run(
                    Command(resume={"approved": approved}),
                    config=config,
                    correlation_id=payload.get("correlation_id"),
                )
                continue

            if payload.get("type") == "ask_user_response":
                answer = payload.get("answer", "")
                await session.start_run(
                    Command(resume={"answer": answer}),
                    config=config,
                    correlation_id=payload.get("correlation_id"),
                )
                continue

            if payload.get("type") == "plan_review_response":
                approved = bool(payload.get("approved"))
                feedback = payload.get("feedback", "")
                await session.start_run(
                    Command(resume={"approved": approved, "feedback": feedback}),
                    config=config,
                    correlation_id=payload.get("correlation_id"),
                )
                continue

            if payload.get("type") == "prefetch_memory":
                user_input = payload.get("message", "")
                project_id = payload.get("project_id", "default")
                persona_id = payload.get("persona_id", "default")
                from src.agent.nodes.memory import background_prefetch_memory

                logger.debug(
                    f"Starting background memory prefetch for thread {thread_id}"
                )
                asyncio.create_task(
                    background_prefetch_memory(
                        thread_id, project_id, persona_id, user_input
                    )
                )
                continue

            user_input = payload.get("message", "")
            files = payload.get("files", [])
            payload_mode = payload.get("mode", "tools_on")
            web_search_enabled = payload.get("web_search_enabled")
            if web_search_enabled is None:
                web_search_enabled = True

            # ── Idle manager: reset timer + ensure LLM is loaded ─────────
            try:
                from src.api.idle_manager import ensure_llm_loaded, record_activity

                record_activity()
                asyncio.create_task(ensure_llm_loaded())
            except Exception:
                pass
            # ─────────────────────────────────────────────────────────────

            response_style = (payload.get("response_style") or "normal").strip()
            project_id = payload.get("project_id", "default")
            persona_id = payload.get("persona_id", "default")
            # Organic-map backend: conversations are ThoughtNodes. project_id remains
            # a soft compatibility field (usually "default") for semantic cache keys.

            # Mode → scenario mapping: frontend sends scenario_id for explicit modes
            client_scenario_id = payload.get("scenario_id")
            if client_scenario_id in ("study", "pentest"):
                scenario_id = client_scenario_id
                if client_scenario_id == "study" and response_style == "normal":
                    response_style = "learning"
                elif client_scenario_id == "pentest" and response_style == "normal":
                    response_style = "concise"
            else:
                scenario_id = None  # Let the router detect it

            # Soft-note workspace refs (chat-only mode does not load them from disk)
            for f in files:
                if f.get("type") == "workspace_ref":
                    prompt_path = f.get("path")
                    user_input += f"\n\n[Attached Workspace File: {prompt_path}]"

            # On first user message, register the ThoughtNode (not a project chat).
            # Pentest stays engagement-scoped and skips the shared graph.
            if scenario_id != "pentest" and (
                thread_id not in sessions or not sessions[thread_id].event_buffer
            ):
                chat_id = thread_id
                file_names = [f.get("name", "") for f in files if f.get("name")]
                try:
                    title = await generate_chat_title_router_llm(
                        user_input[:1000], file_names=file_names
                    )
                except Exception as e:
                    logger.warning("Error suppressed: %s", e)
                    title = ""

                try:
                    from src.memory.thought_graph import thought_graph_manager

                    node_mode = "study" if scenario_id == "study" else "normal"
                    await thought_graph_manager.get_or_create_node(
                        node_id=chat_id,
                        title=title or "New Thought",
                        mode=node_mode,
                        scenario_id=scenario_id,
                    )
                    if title:
                        await thought_graph_manager.update_node(chat_id, title=title)

                    parent_node = payload.get("parent_thread_id") or payload.get(
                        "branch_from"
                    )
                    if parent_node and parent_node != chat_id:
                        await thought_graph_manager.create_edge(
                            source_id=parent_node,
                            target_id=chat_id,
                            relation="branches_to",
                            weight=1.0,
                            auto_generated=False,
                        )
                except Exception as e:
                    logger.debug(
                        "[ws_handler] Failed to sync thought node or branch: %s", e
                    )

                logger.info(
                    "Registered thought node %s (title=%s)",
                    chat_id,
                    title or "New Chat",
                )

            # Chat-only: extract attachments in memory (no disk write)
            message_content = await build_message_content(
                user_input, _files_for_message_content(files, "")
            )
            if not message_content:
                continue

            # ── Semantic Cache Check ───────────────────────────────────────
            # Skip cache for pentest mode (always local, no caching), multi-modal
            # payloads (images), or when files are attached.
            _skip_cache = (
                scenario_id == "pentest"
                or bool(files)
                or not isinstance(message_content, str)
            )
            if not _skip_cache:
                cached_answer = await check_semantic_cache(
                    user_input, project_id=project_id
                )
                if cached_answer:
                    logger.info("[semantic-cache] Cache HIT for thread=%s", thread_id)
                    corr_id = payload.get("correlation_id")

                    def _cache_payload(p: dict) -> dict:
                        return {**p, "correlation_id": corr_id} if corr_id else p

                    await websocket.send_json(
                        _cache_payload({"type": "status", "content": "working"})
                    )
                    # Stream cached text in one shot so UI shows it as a normal reply
                    await websocket.send_json(
                        _cache_payload(
                            {
                                "type": "chunk",
                                "content": cached_answer,
                                "model": "cache",
                            }
                        )
                    )
                    await websocket.send_json(
                        _cache_payload(
                            {
                                "type": "assistant.message",
                                "role": "assistant",
                                "content": cached_answer,
                                "model": "cache",
                            }
                        )
                    )
                    await websocket.send_json(
                        _cache_payload({"type": "status", "content": "idle"})
                    )
                    continue

            # Write user message to trace (before graph run starts)
            if cfg_trace_enabled:
                try:
                    tw = get_trace_writer()
                    tw.write(thread_id, {"type": "turn_start"})
                    tw.write(
                        thread_id,
                        {
                            "type": "user_message",
                            "content": message_content[:2000],
                        },
                    )
                except Exception:
                    pass

            # Update shared cache context so forward_events can store the answer
            if not _skip_cache:
                _pending_cache["prompt"] = user_input
                _pending_cache["project_id"] = project_id

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
                    "_cache_user_input": user_input if not _skip_cache else None,
                    **({"scenario_id": scenario_id} if scenario_id else {}),
                },
                config=config,
                correlation_id=payload.get("correlation_id"),
            )

    except WebSocketDisconnect:
        logger.info("Client disconnected from thread: %s", thread_id)
        audit_info("api.ws", "ws_disconnected", thread_id=thread_id)
    finally:
        connected_websockets.discard(websocket)
        forwarder_task.cancel()
        if trace_task is not None:
            trace_task.cancel()
        if _trace_queue is not None:
            session.remove_listener(_trace_queue)
        try:
            await websocket.close(code=1000)
        except (RuntimeError, AttributeError):
            pass


@router.websocket("/ws/pentest/terminal")
async def pentest_terminal_ws(websocket: WebSocket):
    import secrets as _secrets

    from src.api.local_auth import get_local_run_token

    token = websocket.query_params.get("token")
    expected = get_local_run_token(websocket.app)
    if not token or not _secrets.compare_digest(token, expected):
        await websocket.close(code=4001, reason="Authentication failed")
        return

    await websocket.accept()
    connected_websockets.add(websocket)

    from src.config.config_loader import config as app_config
    from src.tools.screen_assist.kali_stream import get_terminal_streamer

    kali_cfg = app_config.get("screen_assist.kali", {})
    streamer = get_terminal_streamer(
        host=kali_cfg.get("host", "127.0.0.1"),
        user=kali_cfg.get("user", "kali"),
        port=int(kali_cfg.get("port", 60022)),
        session=kali_cfg.get("tmux_session", "main"),
        window="main",
        identity_file=kali_cfg.get("identity_file", "~/.lima/_config/user"),
    )

    async def on_terminal_diff(diff: str, snapshot: str):
        try:
            await websocket.send_json(
                {
                    "type": "pentest.terminal",
                    "data": diff,
                    "window": "main",
                }
            )
        except Exception:
            pass

    unsubscribe = await streamer.subscribe(on_terminal_diff)

    snapshot = await streamer.get_snapshot()
    if snapshot:
        await websocket.send_json(
            {
                "type": "pentest.terminal",
                "data": snapshot,
                "snapshot": snapshot,
                "window": "main",
            }
        )

    await websocket.send_json(
        {
            "type": "pentest.terminal_status",
            "connected": True,
            "host": kali_cfg.get("host", "127.0.0.1"),
            "session": kali_cfg.get("tmux_session", "main"),
        }
    )

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                event_type = payload.get("type")
                if event_type == "pentest.terminal_stop":
                    break
                elif event_type == "pentest.terminal_input":
                    from src.tools.screen_assist.kali_ssh import send_remote_kali_input

                    text = payload.get("text", "")
                    window = payload.get("window", "main")
                    if text:
                        await send_remote_kali_input(
                            host=kali_cfg.get("host", "127.0.0.1"),
                            user=kali_cfg.get("user", "kali"),
                            session=kali_cfg.get("tmux_session", "main"),
                            window=window,
                            text=text,
                            port=int(kali_cfg.get("port", 60022)),
                            identity_file=kali_cfg.get(
                                "identity_file", "~/.lima/_config/user"
                            ),
                        )
            except json.JSONDecodeError:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        await unsubscribe()
        connected_websockets.discard(websocket)
        try:
            await websocket.close(code=1000)
        except (RuntimeError, AttributeError):
            pass
