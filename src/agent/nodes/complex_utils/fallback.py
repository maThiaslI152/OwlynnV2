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
from .helpers import _web_search_tool_output_has_results
from .formatter import _synthetic_answer_from_web_search_tool

def _fallback_for_blank_response(messages: list, *, web_search_enabled: bool) -> AIMessage:
    """
    When the model returns empty assistant content, synthesize a safe user-visible reply.

    Prefers context from recent ``ToolMessage`` outputs (successful or failed ``web_search``).
    If there are no tool messages yet (first LLM turn before any tools) or no match, returns a
    generic message so the thread does not stay blank.
    """
    for m in reversed(messages):
        if not isinstance(m, ToolMessage):
            continue
        c = m.content if isinstance(m.content, str) else str(m.content or "")
        if (getattr(m, "name", None) or "") == "web_search":
            if _web_search_tool_output_has_results(c):
                return AIMessage(content=_synthetic_answer_from_web_search_tool(c))
            if (
                c.startswith("[web_search]")
                or "Unable to retrieve online results" in c
                or "blocked_by_captcha" in c
            ):
                return AIMessage(
                    content=(
                        "I couldn't verify this online right now because web search providers returned "
                        "errors or bot challenges. I did not find reliable live sources in this run. "
                        "If you want, I can retry with a narrower query, a different provider, or use "
                        "another source you provide."
                    )
                )
    if web_search_enabled:
        return AIMessage(
            content=(
                "I didn't get a usable reply from the model this time (empty response). "
                "Try rephrasing or shortening your message, confirm your LLM server is running, "
                "or retry. If you need live web facts, we can try again once the model responds normally."
            )
        )
    return AIMessage(
        content=(
            "I didn't get a usable reply from the model this time (empty response). "
            "Try rephrasing your question or confirm your local LLM is running correctly, then retry."
        )
    )
