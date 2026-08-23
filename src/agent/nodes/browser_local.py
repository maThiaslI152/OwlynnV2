"""
Local Browser Node — Gemma-4 powered extension driver.

Handles the `browser_local` routing decision by using the local small LLM
to natively interact with the browser extension tools. Hands off to cloud
if reasoning tasks become too complex or after maximum browser turns.
"""

import logging

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from src.agent.core.state import AgentState
from src.agent.llm import get_main_llm
from src.config.log_middleware import log_node
from src.tools.screen_assist.tools import SCREEN_ASSIST_TOOLS

logger = logging.getLogger(__name__)

# Constants
MAX_BROWSER_TURNS = 15


@tool
def handoff_to_cloud(action_summary: str) -> str:
    """
    Hands off the current task to the cloud model (DeepSeek) for heavy reasoning.
    Call this ONLY when you have finished navigating the browser or if the user's request requires complex analysis you cannot perform.
    Provide a brief action_summary of what you accomplished (e.g. "I navigated to the dashboard and clicked the login button").
    """
    return f"Handoff initiated. Summary: {action_summary}"


LOCAL_BROWSER_TOOLS = SCREEN_ASSIST_TOOLS + [handoff_to_cloud]

SYSTEM_PROMPT = """You are the Local Browser Driver. Your ONLY job is to mechanically interact with the user's browser using the provided tools.
You are running on a local, small model to save the user tokens and latency.

CRITICAL RULES:
1. YOU MUST ALWAYS call `read_dom_tree` FIRST to understand the current page structure. NEVER GUESS SELECTORS. The page excerpt provided in the prompt is just plain text; you MUST read the DOM to get the actual `id` or CSS selectors before calling `active_browser_action`.
2. ONLY use the `read_dom_tree` tool for navigation. Do NOT use `read_full_dom_tree` unless you are on the final page and are about to call `handoff_to_cloud`. The full DOM will break your context window.
3. Use the `active_browser_action` tool to click, type, and hover using the selectors you found in step 1.
4. If the user asks you to "test", "mock", or "fill" a form without providing specific data, YOU MUST MAKE UP the data (e.g., use "John Doe", "test@example.com"). DO NOT ask the user for data unless they explicitly said the data is required for a real-world critical task.
5. If you have successfully navigated to the required page, OR if the user asked a complex question that requires heavy reasoning, immediately call the `handoff_to_cloud` tool. Provide a very brief `action_summary` when handing off.
6. If the user's request is simple (e.g., "scroll down", "click the login button") and you completed it, you can just reply with a success message instead of handing off.

Do not write code, do not write essays. Just drive the browser.
"""


@log_node("browser_local")
async def browser_local_node(state: AgentState) -> dict:
    """Run the local Gemma-4 model against browser tools."""
    messages = list(state.get("messages") or [])

    # Check for loop escalation safety net
    browser_turns = state.get("_browser_local_turns", 0)

    # Check if the last message was a handoff tool call
    if (
        messages
        and isinstance(messages[-1], ToolMessage)
        and getattr(messages[-1], "name", None) == "handoff_to_cloud"
    ):
        logger.info("Local browser agent explicitly handed off to cloud.")
        return {"route": "complex-cloud", "_browser_local_turns": 0}

    if browser_turns >= MAX_BROWSER_TURNS:
        logger.warning(
            f"browser_local loop escalated to cloud after {browser_turns} turns."
        )
        state["route"] = "complex-cloud"
        # Synthesize a handoff message
        handoff_msg = AIMessage(
            content="[System Auto-Escalation] Exceeded maximum local browser turns. Handing off to cloud."
        )
        return {
            "messages": [handoff_msg],
            "route": "complex-cloud",
            "_browser_local_turns": 0,
        }

    # Bind tools to local model
    llm = await get_main_llm()
    llm_with_tools = llm.bind_tools(LOCAL_BROWSER_TOOLS)

    # Prepare messages
    run_messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    response = await llm_with_tools.ainvoke(run_messages)

    # If it's a text response (no tool calls), push it to the extension UI so the user isn't left hanging
    if isinstance(response, AIMessage) and not response.tool_calls and response.content:
        from src.api.routes.browser_extension import push_extension_ui_status

        push_extension_ui_status("Response:", str(response.content))

    updates = {"messages": [response], "_browser_local_turns": browser_turns + 1}

    return updates
