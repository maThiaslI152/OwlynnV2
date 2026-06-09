"""
LangGraph orchestration with a secure cyclic tool flow.
"""

from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.nodes.router import router_node
from src.agent.nodes.simple import simple_node
from src.agent.nodes.complex import complex_llm_node, complex_tool_action_node
from src.agent.nodes.security_proxy import security_proxy_node
from src.agent.nodes.scope_clarify import scope_clarify_node
from src.agent.nodes.plan_review import plan_review_node
from src.agent.nodes.memory import (
    memory_inject_lite_node,
    memory_retrieve_node,
    memory_write_node,
)
from src.agent.nodes.summarize import auto_summarize_node

import logging

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_debug, set_route
from src.config.config_loader import config

# ── Summarize gate: conditional edge after memory_retrieve ───────────

_DEFAULT_CONTEXT_WINDOW = int(
    config.get("models.medium.variants.default.context_window", 16384)
)
_SUMMARIZE_THRESHOLD = float(config.get("summarization.threshold_ratio", 0.85))


def summarize_gate(state: AgentState) -> str:
    """Route to ``auto_summarize`` when active_tokens > 85% of context_window.

    Returns ``"auto_summarize"`` to trigger summarization, or ``"router"`` to skip.
    """
    active_tokens: int | None = state.get("active_tokens")
    context_window: int | None = state.get("context_window") or _DEFAULT_CONTEXT_WINDOW

    if not active_tokens or active_tokens <= 0:
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="memory_inject→router",
            reason="no_active_tokens",
        )
        return "router"
    threshold = _SUMMARIZE_THRESHOLD * context_window
    if active_tokens > threshold:
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="memory_inject→auto_summarize",
            active_tokens=active_tokens,
            threshold=int(threshold),
        )
        return "auto_summarize"
    audit_debug(
        "agent.lifecycle",
        "edge_traversal",
        edge="memory_inject→router",
        active_tokens=active_tokens,
        threshold=int(threshold),
    )
    return "router"


def route_decision(state: AgentState) -> str:
    route = state.get("route", "complex-default")
    set_route(route)
    if route == "simple":
        audit_debug(
            "agent.lifecycle", "edge_traversal", edge="router→simple", route=route
        )
        return "simple"
    valid_complex = {
        "complex-default",
        "complex-cloud",
    }
    if route in valid_complex:
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="router→scope_clarify",
            route=route,
        )
        return "scope_clarify"
    audit_debug(
        "agent.lifecycle",
        "edge_traversal",
        edge="router→scope_clarify",
        route=route,
        reason="unrecognised_fallback",
    )
    return "scope_clarify"


def after_memory_retrieve(state: AgentState) -> str:
    """Summarize when over token threshold, else branch simple vs complex."""
    gate = summarize_gate(state)
    if gate == "auto_summarize":
        return "auto_summarize"
    return route_decision(state)


def scope_clarify_next(state: AgentState) -> str:
    """After scope_clarify, always continue to complex_llm."""
    return "complex_llm"


def llm_next_step(state: AgentState) -> str:
    """After complex_llm: route to plan_review, security_proxy, memory_write, or back to complex_llm for cutoff continuation."""
    if state.get("_cutoff_pending"):
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="complex_llm→complex_llm",
            reason="cutoff_continuation",
        )
        return "complex_llm"
    if not state.get("pending_tool_calls"):
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="complex_llm→memory_write",
            reason="no_pending_tool_calls",
        )
        return "memory_write"
    if _has_sensitive_pending(state):
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="complex_llm→plan_review",
            reason="sensitive_pending",
        )
        return "plan_review"
    audit_debug("agent.lifecycle", "edge_traversal", edge="complex_llm→security_proxy")
    return "security_proxy"


def _has_sensitive_pending(state: AgentState) -> bool:
    """Check if any pending tool calls match sensitive policy."""
    from src.agent.hitl.policy import is_sensitive_call

    messages = list(state.get("messages") or [])
    if not messages:
        return False
    last = messages[-1]
    tool_calls = list(getattr(last, "tool_calls", None) or [])
    for call in tool_calls:
        name = str(call.get("name", "unknown"))
        args = call.get("args", {})
        if is_sensitive_call(name, args):
            return True
    return False


def plan_review_next(state: AgentState) -> str:
    """After plan_review: approved → security_proxy, denied → memory_write."""
    if state.get("execution_approved") is False:
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="plan_review→memory_write",
            reason="plan_rejected",
        )
        return "memory_write"
    audit_debug(
        "agent.lifecycle",
        "edge_traversal",
        edge="plan_review→security_proxy",
        reason="plan_approved",
    )
    return "security_proxy"


def security_next_step(state: AgentState) -> str:
    go = "tool_action" if bool(state.get("execution_approved")) else "memory_write"
    audit_debug(
        "agent.lifecycle",
        "edge_traversal",
        edge=f"security_proxy→{go}",
        execution_approved=bool(state.get("execution_approved")),
    )
    return go


def build_graph():
    """
    Stateful cyclic LangGraph with HITL gates:
    scope_clarify → plan_review → security_proxy → tool_action.

    Flow:
      memory_inject_lite -> router -> memory_retrieve -> summarize_gate -> ...

    NOTE ON LANGGRAPH MODERNIZATION:
    While LangGraph 1.2+ introduces implicit `Command(goto=...)` routing from within nodes,
    we explicitly retain `add_conditional_edges` here. This orchestration layer is highly
    reliable, and keeping the state machine topology explicitly visible in `graph.py`
    is safer for our complex DeepSeek V4 fallback loops and HITL security gates.
    """
    builder = StateGraph(AgentState)

    builder.add_node("memory_inject_lite", memory_inject_lite_node)
    builder.add_node("memory_retrieve", memory_retrieve_node)
    builder.add_node("auto_summarize", auto_summarize_node)
    builder.add_node("router", router_node)
    builder.add_node("simple", simple_node)
    builder.add_node("scope_clarify", scope_clarify_node)
    builder.add_node("complex_llm", complex_llm_node)
    builder.add_node("plan_review", plan_review_node)
    builder.add_node("security_proxy", security_proxy_node)
    builder.add_node("tool_action", complex_tool_action_node)
    builder.add_node("memory_write", memory_write_node)

    builder.set_entry_point("memory_inject_lite")
    builder.add_edge("memory_inject_lite", "router")
    builder.add_edge("router", "memory_retrieve")

    builder.add_conditional_edges(
        "memory_retrieve",
        after_memory_retrieve,
        {
            "auto_summarize": "auto_summarize",
            "simple": "simple",
            "scope_clarify": "scope_clarify",
        },
    )
    builder.add_conditional_edges(
        "auto_summarize",
        route_decision,
        {
            "simple": "simple",
            "scope_clarify": "scope_clarify",
        },
    )

    # scope_clarify → complex_llm (always continue)
    builder.add_edge("scope_clarify", "complex_llm")

    # complex_llm → plan_review | security_proxy | memory_write | complex_llm
    builder.add_conditional_edges(
        "complex_llm",
        llm_next_step,
        {
            "plan_review": "plan_review",
            "security_proxy": "security_proxy",
            "memory_write": "memory_write",
            "complex_llm": "complex_llm",
        },
    )

    # plan_review → security_proxy (approved) | memory_write (denied)
    builder.add_conditional_edges(
        "plan_review",
        plan_review_next,
        {
            "security_proxy": "security_proxy",
            "memory_write": "memory_write",
        },
    )

    # security_proxy → tool_action | memory_write
    builder.add_conditional_edges(
        "security_proxy",
        security_next_step,
        {
            "tool_action": "tool_action",
            "memory_write": "memory_write",
        },
    )

    builder.add_edge("tool_action", "complex_llm")
    builder.add_edge("simple", "memory_write")
    builder.add_edge("memory_write", END)

    return builder


# --- Init Agent Async Wrapper ---
from langgraph.checkpoint.memory import MemorySaver
from src.config.settings import MCP_CONFIG_PATH, REDIS_URL
from src.tools.mcp_client import mcp_manager
from src.config.secret_store import resolve_deepseek_api_key
from src.agent.cloud_circuit_breaker import reset_circuit_breaker
from src.agent.cloud_cost_tracker import reset_cost_tracker


async def _check_cloud_connectivity() -> dict:
    """Non-blocking cloud connectivity check for startup diagnostics.

    Returns a dict with ``available``, ``key_valid``, and ``model`` keys.
    """
    result: dict = {"available": False, "key_valid": False, "model": "", "error": ""}
    try:
        api_key = resolve_deepseek_api_key()
        if not api_key:
            result["error"] = "No API key configured"
            return result

        from src.memory.user_profile import get_profile

        profile = get_profile()

        import httpx

        from src.agent.llm import LLMPool

        base_url = config.get("models.cloud.base_url", "https://api.deepseek.com/v1")
        model = LLMPool._resolve_cloud_model_name(profile.get("cloud_model_tier"))
        result["model"] = model

        async with httpx.AsyncClient(
            timeout=float(
                config.get("web_search.timeouts.cloud_connectivity_check", 15.0)
            )
        ) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "model": model,
                    "max_tokens": 1,
                },
            )
            if response.status_code == 200:
                result["available"] = True
                result["key_valid"] = True
            elif response.status_code in (401, 403):
                result["key_valid"] = False
                result["error"] = f"Invalid API key (HTTP {response.status_code})"
            else:
                result["available"] = True  # API reachable
                result["key_valid"] = True
                result["error"] = f"Unexpected response: HTTP {response.status_code}"
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        result["error"] = str(e)

    return result


async def init_agent(checkpointer=None):
    """Initializes the agent with Redis checkpointer (falls back to MemorySaver)."""
    try:
        await mcp_manager.initialize(str(MCP_CONFIG_PATH))
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        pass

    # Reset cloud subsystems for fresh session
    reset_circuit_breaker()
    reset_cost_tracker()

    # Non-blocking cloud connectivity check
    import asyncio as _asyncio

    _asyncio.ensure_future(_log_cloud_connectivity())

    builder = build_graph()

    if checkpointer is None:
        try:
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver

            checkpointer = AsyncRedisSaver(redis_url=REDIS_URL)
            await checkpointer.setup()
            logger.info("Using Redis checkpointer at %s", REDIS_URL)
        except Exception as e:
            logger.warning("Redis unavailable (%s), falling back to MemorySaver", e)
            checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


async def _log_cloud_connectivity():
    """Log cloud connectivity status after startup."""
    status = await _check_cloud_connectivity()
    if status["available"] and status["key_valid"]:
        logger.info(
            "[cloud-check] DeepSeek V4 reachable — model=%s, key=valid",
            status.get("model", "unknown"),
        )
    elif status["available"]:
        logger.warning(
            "[cloud-check] DeepSeek V4 reachable but key invalid: %s",
            status.get("error", "unknown"),
        )
    else:
        logger.warning(
            "[cloud-check] DeepSeek V4 unreachable: %s",
            status.get("error", "unknown"),
        )
