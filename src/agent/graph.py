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
from src.agent.nodes.memory import memory_inject_node, memory_write_node
from src.agent.nodes.summarize import auto_summarize_node

import logging
logger = logging.getLogger(__name__)

from src.config.audit_log import audit_debug, set_route

# ── Summarize gate: conditional edge from memory_inject ───────────────

_DEFAULT_CONTEXT_WINDOW = 16_384  # M4 Air: MLX segfaults beyond ~13K tokens
_SUMMARIZE_THRESHOLD = 0.85

def summarize_gate(state: AgentState) -> str:
    """Route to ``auto_summarize`` when active_tokens > 85% of context_window.

    Returns ``"auto_summarize"`` to trigger summarization, or ``"router"`` to skip.
    """
    active_tokens: int | None = state.get("active_tokens")
    context_window: int | None = state.get("context_window") or _DEFAULT_CONTEXT_WINDOW

    if not active_tokens or active_tokens <= 0:
        audit_debug("agent.lifecycle", "edge_traversal", edge="memory_inject→router",
                     reason="no_active_tokens")
        return "router"
    threshold = _SUMMARIZE_THRESHOLD * context_window
    if active_tokens > threshold:
        audit_debug("agent.lifecycle", "edge_traversal", edge="memory_inject→auto_summarize",
                     active_tokens=active_tokens, threshold=int(threshold))
        return "auto_summarize"
    audit_debug("agent.lifecycle", "edge_traversal", edge="memory_inject→router",
                 active_tokens=active_tokens, threshold=int(threshold))
    return "router"

def route_decision(state: AgentState) -> str:
    route = state.get("route", "complex-default")
    set_route(route)
    if route == "simple":
        audit_debug("agent.lifecycle", "edge_traversal", edge="router→simple", route=route)
        return "simple"
    valid_complex = {"complex-default", "complex-vision", "complex-longctx", "complex-cloud"}
    if route in valid_complex:
        audit_debug("agent.lifecycle", "edge_traversal", edge="router→scope_clarify", route=route)
        return "scope_clarify"
    audit_debug("agent.lifecycle", "edge_traversal", edge="router→scope_clarify",
                 route=route, reason="unrecognised_fallback")
    return "scope_clarify"


def scope_clarify_next(state: AgentState) -> str:
    """After scope_clarify, always continue to complex_llm."""
    return "complex_llm"


def llm_next_step(state: AgentState) -> str:
    """After complex_llm: route to plan_review, security_proxy, memory_write, or back to complex_llm for cutoff continuation."""
    if state.get("_cutoff_pending"):
        audit_debug("agent.lifecycle", "edge_traversal", edge="complex_llm→complex_llm",
                     reason="cutoff_continuation")
        return "complex_llm"
    if not state.get("pending_tool_calls"):
        audit_debug("agent.lifecycle", "edge_traversal", edge="complex_llm→memory_write",
                     reason="no_pending_tool_calls")
        return "memory_write"
    if _has_sensitive_pending(state):
        audit_debug("agent.lifecycle", "edge_traversal", edge="complex_llm→plan_review",
                     reason="sensitive_pending")
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
        audit_debug("agent.lifecycle", "edge_traversal", edge="plan_review→memory_write",
                     reason="plan_rejected")
        return "memory_write"
    audit_debug("agent.lifecycle", "edge_traversal", edge="plan_review→security_proxy",
                 reason="plan_approved")
    return "security_proxy"


def security_next_step(state: AgentState) -> str:
    go = "tool_action" if bool(state.get("execution_approved")) else "memory_write"
    audit_debug("agent.lifecycle", "edge_traversal",
                 edge=f"security_proxy→{go}",
                 execution_approved=bool(state.get("execution_approved")))
    return go


def build_graph():
    """
    Stateful cyclic LangGraph with HITL gates:
    scope_clarify → plan_review → security_proxy → tool_action.

    Flow:
      memory_inject -> summarize_gate -> (if >85%) auto_summarize -> router -> ...
                                            (else) router -> ...
    """
    builder = StateGraph(AgentState)

    builder.add_node("memory_inject", memory_inject_node)
    builder.add_node("auto_summarize", auto_summarize_node)
    builder.add_node("router", router_node)
    builder.add_node("simple", simple_node)
    builder.add_node("scope_clarify", scope_clarify_node)
    builder.add_node("complex_llm", complex_llm_node)
    builder.add_node("plan_review", plan_review_node)
    builder.add_node("security_proxy", security_proxy_node)
    builder.add_node("tool_action", complex_tool_action_node)
    builder.add_node("memory_write", memory_write_node)

    builder.set_entry_point("memory_inject")

    # memory_inject -> summarize_gate -> [auto_summarize -> router] | [router]
    builder.add_conditional_edges("memory_inject", summarize_gate, {
        "auto_summarize": "auto_summarize",
        "router": "router",
    })
    builder.add_edge("auto_summarize", "router")

    # router → simple | scope_clarify (complex paths go through clarification)
    builder.add_conditional_edges("router", route_decision, {
        "simple": "simple",
        "scope_clarify": "scope_clarify",
    })

    # scope_clarify → complex_llm (always continue)
    builder.add_edge("scope_clarify", "complex_llm")

    # complex_llm → plan_review | security_proxy | memory_write
    builder.add_conditional_edges("complex_llm", llm_next_step, {
        "plan_review": "plan_review",
        "security_proxy": "security_proxy",
        "memory_write": "memory_write",
    })

    # plan_review → security_proxy (approved) | memory_write (denied)
    builder.add_conditional_edges("plan_review", plan_review_next, {
        "security_proxy": "security_proxy",
        "memory_write": "memory_write",
    })

    # security_proxy → tool_action | memory_write
    builder.add_conditional_edges("security_proxy", security_next_step, {
        "tool_action": "tool_action",
        "memory_write": "memory_write",
    })

    builder.add_edge("tool_action", "complex_llm")
    builder.add_edge("simple", "memory_write")
    builder.add_edge("memory_write", END)

    return builder

# --- Init Agent Async Wrapper ---
from langgraph.checkpoint.memory import MemorySaver
from src.config.settings import MCP_CONFIG_PATH, REDIS_URL
from src.tools.mcp_client import mcp_manager

async def init_agent(checkpointer=None):
    """Initializes the agent with Redis checkpointer (falls back to MemorySaver)."""
    try:
        await mcp_manager.initialize(str(MCP_CONFIG_PATH))
    except Exception:
        pass

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
