"""Tool execution, parallel dispatch, and output bounding for the complex path.

Extracted from complex.py with prompt-cache preservation (zero synthetic HumanMessage injections).
"""

from __future__ import annotations

import asyncio
import logging
import re

from langchain_core.messages import ToolMessage
from langgraph.prebuilt import ToolNode

from src.agent.core.complex_prompt import (
    _message_has_image_content,
    _resolve_complex_tools,
    apply_fetch_retry_nudge,
    apply_web_search_answer_nudge,
)
from src.agent.core.state import AgentState
from src.config.config_loader import config
from src.config.log_middleware import log_node

logger = logging.getLogger(__name__)

# Tools that mutate shared state and must execute sequentially
_SERIAL_TOOLS = frozenset(
    {
        "write_workspace_file",
        "edit_workspace_file",
        "delete_workspace_file",
        "notebook_run",
        "run_kali_command",
        "send_kali_input",
        "metasploit_run",
        "hydra_attack",
        "john_crack",
        "wifi_deauth",
        "wifi_handshake_capture",
        "wifi_crack_handshake",
    }
)


def _extract_tool_output_delta(
    current_messages: list,
    output_messages: list,
) -> list:
    """Extract new messages from ToolNode output.

    LangGraph >=0.3 ToolNode returns only new ToolMessages, not input+output.
    Legacy paths returned the full message list; support both shapes.
    """
    if not output_messages:
        return []
    if all(isinstance(m, ToolMessage) for m in output_messages):
        return list(output_messages)
    if len(output_messages) > len(current_messages):
        return list(output_messages[len(current_messages) :])
    return list(output_messages)


@log_node("tool_action")
async def complex_tool_action_node(state: AgentState) -> AgentState:
    """Executes already-approved tool calls and appends tool outputs to the thread.

    Truncates large tool outputs and embeds error recovery hints directly into ToolMessages
    to preserve KV prompt caching without injecting synthetic HumanMessages.
    """
    current_messages = list(state.get("messages") or [])
    if not current_messages:
        return {"pending_tool_calls": False}

    last_message = current_messages[-1]
    if not bool(getattr(last_message, "tool_calls", None)):
        return {"pending_tool_calls": False}

    web_on = state.get("web_search_enabled")
    if web_on is None:
        web_on = True
    web_on = bool(web_on)

    route = state.get("route") or "complex-cloud"
    has_images = _message_has_image_content(current_messages) or bool(
        (state.get("router_metadata") or {}).get("has_images")
    )
    vision_task = has_images and route == "complex-cloud"
    tools = _resolve_complex_tools(
        state, current_messages, web_on=web_on, vision_task=vision_task
    )
    tool_node = ToolNode(tools)

    async def _parallel_tool_dispatch(tool_calls: list[dict], messages: list) -> dict:
        """Execute independent tool calls in parallel; serial tools run sequentially."""
        call_names = {tc.get("name", "") for tc in tool_calls}
        if call_names & _SERIAL_TOOLS or len(tool_calls) <= 1:
            return await tool_node.ainvoke({"messages": messages})

        base_msgs = messages[:-1]
        last_ai_msg = messages[-1]

        async def _invoke_single(tc: dict) -> ToolMessage | None:
            from langchain_core.messages import AIMessage

            single_ai = AIMessage(
                content=last_ai_msg.content,
                tool_calls=[tc],
                id=last_ai_msg.id,
            )
            result = await tool_node.ainvoke({"messages": base_msgs + [single_ai]})
            msgs = result.get("messages", [])
            return msgs[0] if msgs else None

        results = await asyncio.gather(
            *[_invoke_single(tc) for tc in tool_calls],
            return_exceptions=True,
        )
        tool_msgs = []
        for tc, res in zip(tool_calls, results):
            if isinstance(res, Exception):
                tool_msgs.append(
                    ToolMessage(
                        content=f"Tool execution failed: {type(res).__name__}: {res}",
                        tool_call_id=tc.get("id", "unknown"),
                        name=tc.get("name", "unknown"),
                    )
                )
            elif res is not None:
                tool_msgs.append(res)
        return {"messages": tool_msgs}

    last_tool_calls = getattr(last_message, "tool_calls", None) or []
    try:
        tool_payload = await _parallel_tool_dispatch(last_tool_calls, current_messages)
    except Exception as e:
        logger.exception("Tool execution crashed: %s", type(e).__name__)
        last_msg = current_messages[-1]
        tool_call_id = "unknown"
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            tool_call_id = last_msg.tool_calls[0].get("id", "unknown")
        error_msg = ToolMessage(
            content=(
                f"Tool execution failed with an internal error: {type(e).__name__}: {e}. "
                "Please inform the user that the tool encountered an unexpected error "
                "and suggest trying again or using a different approach."
            ),
            tool_call_id=tool_call_id,
            name="system_error",
        )
        tool_payload = {"messages": [error_msg]}

    output_messages = tool_payload.get("messages", [])
    delta = _extract_tool_output_delta(current_messages, output_messages)

    # Truncate large tool outputs to stay within context window
    _MAX_TOOL_OUTPUT_CHARS = int(config.get("tool_output.max_tool_output_chars", 20000))
    processed_delta = []
    for msg in delta:
        if isinstance(msg, ToolMessage):
            content = (
                msg.content if isinstance(msg.content, str) else str(msg.content or "")
            )
            if len(content) > _MAX_TOOL_OUTPUT_CHARS:
                content = (
                    content[:_MAX_TOOL_OUTPUT_CHARS]
                    + "\n\n[... output truncated for context window. Use read_workspace_file for full content.]"
                )

            # In-place hint enrichment (KV-cache friendly: preserves message roles)
            tool_name = getattr(msg, "name", "") or ""
            if "Error" in content and (
                "Field required" in content or "No code provided" in content
            ):
                content += (
                    f"\n\n[Tool Guidance]: Missing required parameter for {tool_name}. "
                    "Please retry the tool call with the required parameters provided."
                )
            elif "FileNotFoundError" in content and tool_name == "notebook_run":
                content += (
                    "\n\n[Tool Guidance]: File not found. The variable WORKSPACE_DIR is pre-defined. "
                    'Use: pd.read_csv(f"{WORKSPACE_DIR}/filename.csv") to reference workspace files.'
                )
            elif "ModuleNotFoundError" in content and tool_name == "notebook_run":
                from src.tools.notebook_libs import notebook_module_missing_nudge

                mod_match = re.search(r"No module named '([^']+)'", content)
                mod_name = mod_match.group(1) if mod_match else "unknown"
                content += (
                    f"\n\n[Tool Guidance]: {notebook_module_missing_nudge(mod_name)}"
                )
            elif (
                "Error" in content
                and tool_name == "notebook_run"
                and "Traceback" in content
            ):
                lines = content.strip().split("\n")
                error_line = lines[-1] if lines else "Unknown error"
                content += (
                    f"\n\n[Tool Guidance]: Python error encountered: {error_line}. "
                    "Check column dtypes with df.dtypes or convert with pd.to_numeric(col, errors='coerce')."
                )

            msg = ToolMessage(
                content=content,
                tool_call_id=msg.tool_call_id,
                name=getattr(msg, "name", None),
            )
        processed_delta.append(msg)

    nudged = apply_fetch_retry_nudge(processed_delta)
    nudged = apply_web_search_answer_nudge(nudged)

    return {
        "messages": nudged,
        "pending_tool_calls": False,
        "execution_approved": None,
    }
