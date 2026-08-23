"""Per-conversation trace writer for IDE agent diagnostics.

Subscribes to the same LangGraph ``astream_events`` pipeline as the WebSocket
forwarder and persists structured trace records to per-thread JSONL files.

Usage from an IDE agent::

    import json
    with open("~/.owlynn/traces/{thread_id}.jsonl") as f:
        events = [json.loads(line) for line in f]
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


def _resolve_trace_dir() -> Path:
    raw = ConfigLoader.get("trace.output_dir", "~/.owlynn/traces")
    return Path(raw).expanduser().resolve()


class TraceWriter:
    """Writes per-thread conversation traces as JSONL files."""

    def __init__(self) -> None:
        self._dir = _resolve_trace_dir()
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def output_dir(self) -> Path:
        return self._dir

    def _ts(self) -> str:
        return datetime.now(UTC).isoformat(timespec="milliseconds")

    def write(self, thread_id: str, record: dict[str, Any]) -> None:
        """Append a single trace record to the thread's JSONL file."""
        record.setdefault("ts", self._ts())
        record.setdefault("thread_id", thread_id)
        path = self._dir / f"{thread_id}.jsonl"
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception:
            logger.debug("Failed to write trace for %s", thread_id, exc_info=True)


def _truncate(text: str, max_len: int = 2000) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [truncated, {len(text)} chars total]"


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content) if content else ""


async def trace_listener(
    thread_id: str,
    queue: asyncio.Queue,
    writer: TraceWriter,
) -> None:
    """Consume events from a GraphSession listener queue and write traces.

    Interprets raw LangGraph ``astream_events(version="v2")`` output into
    structured trace records, mirroring the WS forwarder's logic but simpler
    (no streaming chunks — only final results).

    ``turn_start`` and ``user_message`` are written by the WS handler before
    the graph run starts; this coroutine only handles graph events.
    """

    pending_tool_calls: dict[str, dict] = {}
    running_tool_calls: dict[str, dict] = {}
    loop = asyncio.get_running_loop()

    try:
        while True:
            item = await queue.get()
            if item is None:
                break

            event, _correlation_id = item if isinstance(item, tuple) else (item, None)

            # Synthetic events (status, error)
            if isinstance(event, dict) and "type" in event and "event" not in event:
                evt_type = event.get("type")
                if evt_type == "error":
                    writer.write(
                        thread_id,
                        {
                            "type": "error",
                            "message": event.get("content", ""),
                        },
                    )
                elif evt_type == "status" and event.get("content") == "idle":
                    writer.write(thread_id, {"type": "turn_end"})
                continue

            # LangGraph astream_events
            if not isinstance(event, dict) or "event" not in event:
                continue

            kind = event.get("event")
            metadata = event.get("metadata", {})
            node = metadata.get("langgraph_node")
            data = event.get("data", {})

            if kind == "on_chain_start":
                if (
                    node in {"tool_action", "tools"}
                    or metadata.get("langgraph_step") == "tools"
                ):
                    for tc_id, tc in list(pending_tool_calls.items()):
                        running_tool_calls[tc_id] = {
                            "tool_name": tc.get("tool_name", "unknown"),
                            "started_at": loop.time(),
                        }
                    pending_tool_calls.clear()

            elif kind == "on_chain_end":
                output = data.get("output")

                # Router decision
                if node == "router" and isinstance(output, dict):
                    meta = output.get("router_metadata")
                    if meta and isinstance(meta, dict):
                        writer.write(
                            thread_id,
                            {
                                "type": "router_decision",
                                "route": meta.get("route", ""),
                                "confidence": meta.get("confidence"),
                                "source": meta.get("classification_source", ""),
                                "task_category": meta.get("task_category", ""),
                                "toolbox": meta.get("toolbox", ""),
                            },
                        )

                # LLM response (simple or complex_llm)
                if node in {"simple", "complex_llm"} and isinstance(output, dict):
                    msgs = output.get("messages") or []
                    if msgs:
                        last = msgs[-1]
                        content = _stringify_content(getattr(last, "content", ""))
                        tool_calls = list(getattr(last, "tool_calls", None) or [])
                        writer.write(
                            thread_id,
                            {
                                "type": "llm_response",
                                "node": node,
                                "model": output.get("model_used", ""),
                                "content_preview": _truncate(content, 1000),
                                "has_tool_calls": bool(tool_calls),
                                "tool_call_count": len(tool_calls),
                                "token_usage": output.get("api_tokens_used"),
                                "fallback_chain": output.get("fallback_chain"),
                            },
                        )
                        # Track pending tool calls
                        for tc in tool_calls:
                            tc_id = str(tc.get("id") or tc.get("tool_call_id") or "")
                            if tc_id:
                                pending_tool_calls[tc_id] = {
                                    "tool_name": str(tc.get("name") or "unknown"),
                                    "tool_input": tc.get("args"),
                                }

                # Tool results
                if (
                    node in {"tool_action", "tools"}
                    or metadata.get("langgraph_step") == "tools"
                ):
                    if isinstance(output, dict) and "messages" in output:
                        from langchain_core.messages import ToolMessage

                        for msg in output["messages"]:
                            if isinstance(msg, ToolMessage):
                                tc_id = str(getattr(msg, "tool_call_id", "") or "")
                                stored = (
                                    running_tool_calls.pop(tc_id, None)
                                    if tc_id
                                    else None
                                )
                                tool_name = str(
                                    getattr(msg, "name", "")
                                    or (stored or {}).get("tool_name")
                                    or "unknown"
                                )
                                started_at = (stored or {}).get("started_at")
                                duration = (
                                    max(0.0, loop.time() - float(started_at))
                                    if started_at is not None
                                    else None
                                )
                                content = str(getattr(msg, "content", "") or "")
                                is_error = any(
                                    kw in content.lower()
                                    for kw in (
                                        "error",
                                        "exception",
                                        "traceback",
                                        "failed",
                                    )
                                )
                                writer.write(
                                    thread_id,
                                    {
                                        "type": "tool_call",
                                        "tool_name": tool_name,
                                        "input": (stored or {}).get("tool_input"),
                                        "output": _truncate(content, 2000),
                                        "error": content if is_error else None,
                                        "duration_s": round(duration, 3)
                                        if duration
                                        else None,
                                    },
                                )

                # Coherence check
                if node == "coherence_check" and isinstance(output, dict):
                    coherence = output.get("response_coherence") or {}
                    writer.write(
                        thread_id,
                        {
                            "type": "coherence_check",
                            "coherent": coherence.get("coherent", True),
                            "confidence": output.get("response_confidence"),
                            "reason": coherence.get("reason", ""),
                            "duration_ms": output.get("turn_duration_ms"),
                        },
                    )

                # Interrupt (HITL)
                if isinstance(output, dict) and "__interrupt__" in output:
                    writer.write(
                        thread_id,
                        {
                            "type": "hitl_interrupt",
                            "interrupt_count": len(output["__interrupt__"]),
                        },
                    )

            elif kind == "on_chat_model_end":
                # Capture LLM prompt from the start event if available
                pass

    except asyncio.CancelledError:
        pass
    except Exception:
        logger.debug("Trace listener error for %s", thread_id, exc_info=True)
    finally:
        writer.write(thread_id, {"type": "trace_session_end"})


# Module-level singleton
_trace_writer: TraceWriter | None = None


def get_trace_writer() -> TraceWriter:
    global _trace_writer
    if _trace_writer is None:
        _trace_writer = TraceWriter()
    return _trace_writer
