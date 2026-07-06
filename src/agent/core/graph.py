"""LangGraph orchestration with a secure cyclic tool flow.

See docs/AGENT_FLOW.md for node-by-node flow and docs/EXTENDING_AGENT.md for extension points.
"""

from langgraph.graph import StateGraph, END
from src.agent.core.state import AgentState
from src.agent.routing.router import router_node
from src.agent.core.simple import simple_node
from src.agent.nodes.browser_local import browser_local_node
from src.agent.core.complex import complex_llm_node, complex_tool_action_node
from src.agent.nodes.security_proxy import security_proxy_node
from src.agent.nodes.scope_clarify import scope_clarify_node
from src.agent.nodes.plan_review import plan_review_node
from src.agent.nodes.memory import (
    memory_inject_lite_node,
    memory_retrieve_node,
    memory_write_node,
)
from src.agent.nodes.summarize import auto_summarize_node
from src.agent.nodes.coherence import coherence_check_node
from src.agent.nodes.coherence_retry import coherence_retry_node


import logging

logger = logging.getLogger(__name__)

from src.config.audit_log import audit_debug, set_route
from src.config.config_loader import config

# ── Summarize gate: conditional edge after memory_retrieve ───────────

_DEFAULT_CONTEXT_WINDOW = int(
    config.get("models.medium.variants.default.context_window", 16384)
)
_SUMMARIZE_THRESHOLD = float(config.get("summarization.threshold_ratio", 0.85))

_COHERENCE_THRESHOLD = float(config.get("coherence.retry_threshold", 0.4))
_COHERENCE_MAX_RETRIES = int(config.get("coherence.max_retries", 1))


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
    route = state.get("route", "complex-cloud")
    set_route(route)
    if route == "simple":
        audit_debug(
            "agent.lifecycle", "edge_traversal", edge="router→simple", route=route
        )
        return "simple"
    if route == "browser_local":
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="router→browser_local",
            route=route,
        )
        return "browser_local"
    # All complex routes go to scope_clarify → complex_llm (cloud-only)
    audit_debug(
        "agent.lifecycle",
        "edge_traversal",
        edge="router→scope_clarify",
        route=route,
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
    """After complex_llm: route to plan_review, security_proxy, coherence_check, or back to complex_llm for cutoff continuation."""
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
            edge="complex_llm→coherence_check",
            reason="no_pending_tool_calls",
        )
        return "coherence_check"
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
    """After plan_review: approved → security_proxy, denied → coherence_check."""
    if state.get("execution_approved") is False:
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="plan_review→coherence_check",
            reason="plan_rejected",
        )
        return "coherence_check"
    audit_debug(
        "agent.lifecycle",
        "edge_traversal",
        edge="plan_review→security_proxy",
        reason="plan_approved",
    )
    return "security_proxy"


def security_next_step(state: AgentState) -> str:
    go = "tool_action" if bool(state.get("execution_approved")) else "coherence_check"
    audit_debug(
        "agent.lifecycle",
        "edge_traversal",
        edge=f"security_proxy→{go}",
        execution_approved=bool(state.get("execution_approved")),
    )
    return go


def coherence_retry_gate(state: AgentState) -> str:
    """After coherence_check: route to coherence_retry when confidence is below
    the configured threshold AND the retry budget remains. Otherwise proceed
    to memory_write.

    Mirrors the cutoff-continuation pattern in llm_next_step: a single bounded
    cycle that cannot spin.
    """
    enabled = bool(config.get("coherence.enabled", True))
    confidence = state.get("response_confidence")
    rounds_done = int(state.get("_coherence_retry_round") or 0)
    below_threshold = (
        confidence is not None and float(confidence) < _COHERENCE_THRESHOLD
    )
    budget_left = rounds_done < _COHERENCE_MAX_RETRIES
    if enabled and below_threshold and budget_left:
        audit_debug(
            "agent.lifecycle",
            "edge_traversal",
            edge="coherence_check→coherence_retry",
            confidence=confidence,
            rounds_done=rounds_done,
            threshold=_COHERENCE_THRESHOLD,
            reason="low_coherence_retry",
        )
        return "coherence_retry"
    audit_debug(
        "agent.lifecycle",
        "edge_traversal",
        edge="coherence_check→memory_write",
        confidence=confidence,
        rounds_done=rounds_done,
        reason="retry_skipped_or_exhausted",
    )
    return "memory_write"


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
    builder.add_node("browser_local", browser_local_node)
    builder.add_node("scope_clarify", scope_clarify_node)
    builder.add_node("complex_llm", complex_llm_node)
    builder.add_node("plan_review", plan_review_node)
    builder.add_node("security_proxy", security_proxy_node)
    builder.add_node("tool_action", complex_tool_action_node)
    builder.add_node("coherence_check", coherence_check_node)
    builder.add_node("coherence_retry", coherence_retry_node)
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
            "browser_local": "browser_local",
            "scope_clarify": "scope_clarify",
        },
    )

    builder.add_conditional_edges(
        "auto_summarize",
        route_decision,
        {
            "simple": "simple",
            "browser_local": "browser_local",
            "scope_clarify": "scope_clarify",
        },
    )

    def browser_local_next(state: AgentState) -> str:
        # If route was changed to complex-cloud (via handoff), go to scope_clarify or complex_llm
        route = state.get("route")
        if route == "complex-cloud":
            return "scope_clarify"
        # Otherwise, check if there are pending tool calls
        messages = list(state.get("messages") or [])
        if messages and getattr(messages[-1], "tool_calls", None):
            return "tool_action_local"
        # Done
        return "memory_write"

    builder.add_conditional_edges(
        "browser_local",
        browser_local_next,
        {
            "scope_clarify": "scope_clarify",
            "tool_action_local": "tool_action",
            "memory_write": "memory_write",
        },
    )

    # scope_clarify → complex_llm (always continue)
    builder.add_edge("scope_clarify", "complex_llm")

    # complex_llm → plan_review | security_proxy | coherence_check | complex_llm
    builder.add_conditional_edges(
        "complex_llm",
        llm_next_step,
        {
            "plan_review": "plan_review",
            "security_proxy": "security_proxy",
            "coherence_check": "coherence_check",
            "complex_llm": "complex_llm",
        },
    )

    # plan_review → security_proxy (approved) | coherence_check (denied)
    builder.add_conditional_edges(
        "plan_review",
        plan_review_next,
        {
            "security_proxy": "security_proxy",
            "coherence_check": "coherence_check",
        },
    )

    # security_proxy → tool_action | coherence_check
    builder.add_conditional_edges(
        "security_proxy",
        security_next_step,
        {
            "tool_action": "tool_action",
            "coherence_check": "coherence_check",
        },
    )

    def after_tool_action(state: AgentState) -> str:
        if state.get("route") == "browser_local":
            return "browser_local"
        return "complex_llm"

    builder.add_conditional_edges(
        "tool_action",
        after_tool_action,
        {"browser_local": "browser_local", "complex_llm": "complex_llm"},
    )
    builder.add_edge("simple", "coherence_check")

    # coherence_check → coherence_retry (low confidence + budget left) | memory_write
    builder.add_conditional_edges(
        "coherence_check",
        coherence_retry_gate,
        {
            "coherence_retry": "coherence_retry",
            "memory_write": "memory_write",
        },
    )
    # coherence_retry cycles back through complex_llm so the new response
    # flows through the normal tool/HITL/coherence pipeline. _coherence_retry_round
    # is incremented by the retry node so the gate accepts at most max_retries
    # attempts per turn.
    builder.add_edge("coherence_retry", "complex_llm")
    builder.add_edge("memory_write", END)

    return builder


# --- Init Agent Async Wrapper ---
from langgraph.checkpoint.memory import MemorySaver
from src.config.settings import MCP_CONFIG_PATH, REDIS_URL
from src.tools.mcp_client import mcp_manager
from src.config.secret_store import resolve_deepseek_api_key
from src.agent.cloud.cloud_circuit_breaker import reset_circuit_breaker
from src.agent.cloud.cloud_cost_tracker import reset_cost_tracker


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
            # Start background eviction of stale checkpoint keys (runs every 24h)
            _asyncio.ensure_future(_evict_stale_checkpoints(REDIS_URL))
        except Exception as e:
            logger.warning("Redis unavailable (%s), falling back to MemorySaver", e)
            checkpointer = MemorySaver()

    # Initialize the semantic cache (non-blocking, degrades gracefully on error)
    try:
        from src.memory.semantic_cache import init_semantic_cache

        _asyncio.ensure_future(init_semantic_cache())
    except Exception as e:
        logger.warning("Semantic cache init failed: %s", e)

    return builder.compile(checkpointer=checkpointer)


async def _evict_stale_checkpoints(redis_url: str, max_age_days: int = 30):
    """
    Background task that scans Redis for LangGraph checkpoint keys older than
    `max_age_days` and deletes them to prevent unbounded memory growth.
    Runs once on startup then repeats every 24 hours.
    """
    import asyncio
    import redis.asyncio as aioredis

    max_age_secs = max_age_days * 86_400
    while True:
        try:
            client = aioredis.from_url(redis_url)
            cursor = 0
            evicted = 0
            async for key in client.scan_iter(match="checkpoint:*", count=500):
                ttl = await client.ttl(key)
                if ttl == -1:  # No TTL set — check creation time via OBJECT IDLETIME
                    idle = await client.object("IDLETIME", key)
                    if idle is not None and idle > max_age_secs:
                        await client.delete(key)
                        evicted += 1
            await client.aclose()
            if evicted:
                logger.info(
                    "[checkpoint-evict] Evicted %d stale checkpoint keys (> %d days idle)",
                    evicted,
                    max_age_days,
                )
        except Exception as e:
            logger.warning("[checkpoint-evict] Error during eviction scan: %s", e)
        await asyncio.sleep(86_400)  # Sleep 24 hours


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
