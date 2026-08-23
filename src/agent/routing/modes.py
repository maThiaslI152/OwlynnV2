"""Mode-specific routing — pentest, study, and normal mode logic.

Extracted from router.py during the router decomposition refactor.
"""

from __future__ import annotations

import logging

from src.agent.core.state import AgentState
from src.config.audit_log import audit_info

logger = logging.getLogger(__name__)


def augment_toolbox_for_scenario(
    toolbox: list[str],
    scenario_id: str | None,
    user_text: str,
) -> list[str]:
    """Add screen_assist / mcp toolboxes for pentest and terminal workflows.

    For pentest: REPLACES the toolbox entirely with the pentest toolbox
    (pentest tools are curated — no study tools, no global memory tools).
    """
    if "all" in toolbox:
        return toolbox

    # Pentest: replace with curated pentest toolbox
    if scenario_id == "pentest":
        return ["pentest"]

    if scenario_id == "pentest" or _user_wants_screen_assist(user_text):
        if "screen_assist" not in toolbox:
            toolbox = [*toolbox, "screen_assist"]

    from src.config.config_loader import config

    if (
        config.get("mcp.auto_toolbox_on_pentest", True)
        and scenario_id == "pentest"
        and "mcp" not in toolbox
    ):
        from src.tools.mcp_client import get_mcp_tools

        if get_mcp_tools():
            toolbox = [*toolbox, "mcp"]

    if scenario_id == "study":
        for box in ("file_ops", "memory", "study"):
            if box not in toolbox:
                toolbox = [*toolbox, box]

    return toolbox


def apply_learning_mode(
    state: AgentState, gate_fields: dict, toolbox: list[str]
) -> tuple[dict, list[str]]:
    """Learning response_style → study scenario + study toolboxes."""
    style = (state.get("response_style") or "").strip().lower()
    if style != "learning":
        return gate_fields, toolbox
    gf = dict(gate_fields)
    if not gf.get("scenario_id"):
        gf["scenario_id"] = "study"
    gf["needs_memory_retrieval"] = True
    tb = list(toolbox)
    if "all" not in tb:
        for box in ("file_ops", "memory", "study"):
            if box not in tb:
                tb.append(box)
    return gf, tb


def handle_pentest_mode(
    user_text: str,
    state: AgentState,
    *,
    cloud_available: bool,
    has_images: bool,
    web_on: bool,
) -> dict | None:
    """Deterministic pentest-mode bypass.

    Returns a complete router result dict if in pentest mode, or ``None``
    to fall through to the LLM classifier.
    """
    if state.get("scenario_id") != "pentest":
        return None

    from src.agent.routing.pentest_classifier import (
        classify_pentest_query,
        should_route_to_cloud,
    )
    from src.agent.routing.resolver import (
        _build_router_metadata,
        _memory_gate_fields,
        _resolve_complex_route,
        estimate_token_budget,
    )
    from src.config.config_loader import config as _cfg

    cloud_proxy_enabled = _cfg.get("models.pentest.cloud_proxy.enabled", False)
    pentest_category = classify_pentest_query(user_text)
    use_cloud = (
        cloud_proxy_enabled
        and should_route_to_cloud(pentest_category)
        and cloud_available
    )

    if use_cloud:
        route = "complex-cloud"
        toolbox = ["pentest"]
        logger.info(
            "[router] Pentest cloud proxy: category=%s → cloud",
            pentest_category.value,
        )
    else:
        logger.info(
            "[router] Complex path — pentest mode detected, bypassing LLM router"
        )
        route, toolbox = _resolve_complex_route(
            user_text, state, ["pentest"], cloud_available=cloud_available
        )
    budget = estimate_token_budget(user_text, route)
    metadata = _build_router_metadata(
        route,
        confidence=1.0,
        reasoning="pentest_mode_bypass",
        classification_source="deterministic",
        cloud_available=cloud_available,
        has_images=has_images,
        task_category="security",
        estimated_tokens=budget,
        web_on=web_on,
    )
    if use_cloud:
        metadata["pentest_cloud_proxy"] = True
        metadata["pentest_query_category"] = pentest_category.value
    audit_info(
        "agent.lifecycle",
        "router_decision",
        route=route,
        confidence=1.0,
        source="pentest_mode_bypass",
        task_category="security",
    )
    return {
        "route": route,
        "token_budget": budget,
        "selected_toolboxes": toolbox,
        "router_clarification_used": False,
        "skill_matched": None,
        "router_metadata": metadata,
        **_memory_gate_fields(state, user_text, route, force_needs=False),
    }


_SCREEN_ASSIST_HINTS = (
    "tmux",
    "my terminal",
    "terminal output",
    "shell output",
    "what's on screen",
    "on my screen",
    "browser tab",
    "active tab",
    "kali vm",
    "kali terminal",
    "capture pane",
    "iterm",
    "browser page",
    "current page",
    "on the page",
    "my browser",
    "screenshot",
)


def _user_wants_screen_assist(text: str) -> bool:
    lower = text.lower()
    return any(h in lower for h in _SCREEN_ASSIST_HINTS)
