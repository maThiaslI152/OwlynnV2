import asyncio
import json
import logging
import re
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from src.agent.state import AgentState
from src.agent.llm import get_large_llm, get_medium_llm, get_cloud_llm, CloudUnavailableError
from src.agent.swap_manager import ModelSwapError
from src.agent.response_styles import style_instruction_for_prompt
from src.agent.tool_sets import (
    COMPLEX_TOOLS_NO_WEB,
    COMPLEX_TOOLS_WITH_WEB,
    resolve_tools,
)
from src.agent.lm_studio_compat import is_local_server, with_system_for_local_server
from src.agent.anonymization import anonymize, deanonymize
from src.agent.hitl.cloud_brief import build_cloud_brief, estimate_brief_tokens
from src.memory.user_profile import get_profile
from src.config.audit_log import audit_debug, audit_info, audit_warn
from src.config.log_middleware import log_model_attempt, log_node
from src.config.config_loader import config

def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks from reasoning output."""
    if not text:
        return text
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return cleaned if cleaned else text

def _synthetic_answer_from_web_search_tool(content: str) -> str:
    """
    When the LLM returns empty after a successful web_search, surface the tool text
    so the user still gets a usable answer in the UI.
    """
    c = (content or "").strip()
    if not c:
        return (
            "I ran **web_search** but the tool returned no text. "
            "Try again or narrow the query."
        )
    pref = (
        "The model returned an empty message after **web_search**, so here is the "
        "search payload directly (you can use the links below):\n\n"
    )
    cap = int(config.get("complex.synthetic_answer_max_chars", 4500))
    if len(c) > cap:
        return pref + c[:cap] + "\n\n… [truncated]"
    return pref + c

def _flatten_human_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return str(content or "")
