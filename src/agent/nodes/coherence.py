"""
Coherence Checker Node — Evaluates answer coherence and turn latency.

Calculates turn duration, checks response coherence using the small local LLM,
and calibrates confidence based on coherence scores and tool execution failures.
"""

import time
import json
import re
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from src.agent.llm import get_small_llm
from src.agent.core.state import AgentState
from src.config.log_middleware import log_node
from src.config.audit_log import audit_warn, audit_info

logger = logging.getLogger(__name__)

COHERENCE_PROMPT = """You are a quality assurance system. Compare the user's query and the assistant's final response below, and evaluate if the response is coherent, relevant, and directly addresses the user's query.

User Query: {query}
Assistant Response: {response}

Output your evaluation in standard JSON format. The JSON must contain exactly these three keys:
- "coherent": boolean (true if the response is coherent, relevant, and addresses the query; false otherwise)
- "score": float (from 0.0 to 1.0, representing the degree of coherence/relevance)
- "reason": string (a short explanation of your rating)

Do not include any preamble, thinking process, or markdown formatting outside of the JSON block.

JSON output:"""


def _parse_coherence_json(content: str) -> Dict[str, Any]:
    """Parse JSON evaluation safely, removing thinking tags and wrappers."""
    if not content:
        return {
            "coherent": True,
            "score": 1.0,
            "reason": "Empty evaluation content; defaulted to coherent.",
        }

    # Strip thinking tags
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL).strip()

    # Locate JSON block
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if "coherent" in data and "score" in data and "reason" in data:
                return {
                    "coherent": bool(data["coherent"]),
                    "score": float(data["score"]),
                    "reason": str(data["reason"]),
                }
        except Exception as e:
            logger.warning("Failed to parse JSON content from small LLM: %s", e)

    return {
        "coherent": True,
        "score": 1.0,
        "reason": "Failed to parse coherence check JSON response; defaulted to coherent.",
    }


@log_node("coherence_check")
async def coherence_check_node(state: AgentState) -> Dict[str, Any]:
    """Evaluate response coherence, compute turn latency, and calibrate confidence."""
    messages = state.get("messages") or []
    if not messages:
        return {
            "response_confidence": 1.0,
            "response_coherence": {
                "coherent": True,
                "score": 1.0,
                "reason": "No messages in history.",
            },
            "turn_duration_ms": 0,
        }

    # Extract final assistant response
    response_content = ""
    last_msg = messages[-1]
    last_msg_role = (
        getattr(last_msg, "type", None)
        or getattr(last_msg, "role", None)
        or (last_msg.get("role") if isinstance(last_msg, dict) else "")
    )
    if last_msg_role in ("ai", "assistant"):
        response_content = getattr(last_msg, "content", "") or (
            last_msg.get("content") if isinstance(last_msg, dict) else ""
        )
    response_content = str(response_content).strip()

    # Extract user query (last human/user message before the response)
    query_content = ""
    for msg in reversed(messages[:-1]):
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else "")
        )
        if role in ("human", "user"):
            query_content = getattr(msg, "content", "") or (
                msg.get("content") if isinstance(msg, dict) else ""
            )
            break
    query_content = str(query_content).strip()

    # Find messages in the current turn starting from the last human message
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        role = (
            getattr(msg, "type", None)
            or getattr(msg, "role", None)
            or (msg.get("role") if isinstance(msg, dict) else "")
        )
        if role in ("human", "user"):
            last_human_idx = i
            break

    current_turn_messages = (
        messages[last_human_idx:] if last_human_idx != -1 else messages
    )

    # Detect tool failures in the current turn
    tool_failures = 0
    for msg in current_turn_messages:
        is_tool_msg = isinstance(msg, ToolMessage)
        if not is_tool_msg:
            role = (
                getattr(msg, "type", None)
                or getattr(msg, "role", None)
                or (msg.get("role") if isinstance(msg, dict) else "")
            )
            if role == "tool":
                is_tool_msg = True

        if is_tool_msg:
            content = getattr(msg, "content", "") or (
                msg.get("content") if isinstance(msg, dict) else ""
            )
            content_str = str(content)
            if any(
                term in content_str.lower()
                for term in ["error:", "failed", "exception"]
            ):
                tool_failures += 1

    # Check coherence with small LLM
    coherence_data = {
        "coherent": True,
        "score": 1.0,
        "reason": "Default / skipped check",
    }
    if query_content and response_content:
        try:
            small_llm = await get_small_llm()
            # Bind low temperature to ensure consistent evaluations
            runnable = small_llm.bind(temperature=0.1)
            prompt_text = COHERENCE_PROMPT.format(
                query=query_content, response=response_content
            )

            # Safely invoke LLM
            response = await runnable.ainvoke(prompt_text)
            content = getattr(response, "content", "") or str(response)
            coherence_data = _parse_coherence_json(content)
        except Exception as e:
            logger.warning("Coherence check failed to run LLM: %s", e)
            coherence_data = {
                "coherent": True,
                "score": 1.0,
                "reason": f"Coherence check LLM failed: {e}",
            }

    base_score = coherence_data.get("score", 1.0)
    coherent = coherence_data.get("coherent", True)

    # Short response check: if response is extremely short (< 10 chars) for complex turns
    route = state.get("route") or ""
    is_complex = route.startswith("complex")
    if is_complex and len(response_content) < 10:
        base_score -= 0.3
        coherent = False
        coherence_data["coherent"] = False
        coherence_data["reason"] = (
            coherence_data.get("reason", "")
            + " [Warning: Extremely short response in complex turn]"
        ).strip()

    # Tool failure deductions
    deduction = 0.15 * tool_failures
    confidence = base_score - deduction
    if confidence < 0.1:
        confidence = 0.1
    elif confidence > 1.0:
        confidence = 1.0

    # Turn Duration & Lag warning
    turn_duration_ms = 0
    start_time = state.get("turn_start_time")
    if start_time:
        turn_duration_ms = int((time.time() - start_time) * 1000)
        if turn_duration_ms > 15000:
            audit_warn(
                "agent.lifecycle",
                "high_turn_latency",
                duration_ms=turn_duration_ms,
                message="Turn duration exceeded warning threshold of 15 seconds.",
            )

    audit_info(
        "agent.lifecycle",
        "coherence_check_complete",
        coherent=coherent,
        score=base_score,
        confidence=confidence,
        tool_failures=tool_failures,
        duration_ms=turn_duration_ms,
    )

    return {
        "response_confidence": confidence,
        "response_coherence": {
            "coherent": coherent,
            "score": base_score,
            "reason": coherence_data.get("reason", ""),
        },
        "turn_duration_ms": turn_duration_ms,
    }
