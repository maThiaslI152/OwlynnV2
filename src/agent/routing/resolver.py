"""Route resolution — complex route selection, cloud availability, budget estimation.

Extracted from router.py during the router decomposition refactor.
"""

from __future__ import annotations

import logging
import re

from src.agent.core.state import AgentState
from src.config.config_loader import config
from src.config.settings import (
    MEDIUM_DEFAULT_CONTEXT,
    MEDIUM_LONGCTX_CONTEXT,
    CLOUD_CONTEXT,
)
from src.config.secret_store import resolve_deepseek_api_key
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

# ── Context window constants ─────────────────────────────────────────────
_MEDIUM_DEFAULT_CONTEXT = MEDIUM_DEFAULT_CONTEXT
_MEDIUM_LONGCTX_CONTEXT = MEDIUM_LONGCTX_CONTEXT
_CLOUD_CONTEXT = CLOUD_CONTEXT
_SMALL_MODEL_CONTEXT = int(config.get("models.small.context_window", 65536))

# Budget tiers from centralized config
_BUDGET_TIERS_RAW = config.get(
    "routing.budget_tiers",
    [
        [40, 256],
        [150, 512],
        [400, 1536],
        [800, 3072],
        [1600, 4096],
    ],
)
_BUDGET_TIERS = [(int(t[0]), int(t[1])) for t in _BUDGET_TIERS_RAW]

_LONG_ANSWER_HINTS = {
    "explain",
    "write",
    "create",
    "implement",
    "build",
    "generate",
    "refactor",
    "analyze",
    "compare",
    "review",
    "summarize",
    "translate",
    "step by step",
    "in detail",
    "full code",
    "complete",
    "visualize",
    "plot",
    "draw",
    "chart",
    "graph",
}

_SHORT_ANSWER_HINTS = {
    "yes or no",
    "true or false",
    "which one",
    "what is",
    "how much",
    "how many",
    "when",
    "where",
}


def estimate_token_budget(user_text: str, route: str) -> int:
    """Estimate a reasonable max_tokens budget for the response.

    Uses per-tier context windows:
    - simple → _SMALL_MODEL_CONTEXT with 1500 reserve
    - complex-cloud → _CLOUD_CONTEXT (131072) with 8000 reserve, budget_max 16384
    - complex-default → _MEDIUM_DEFAULT_CONTEXT with 4000 reserve, budget_max 8192
    """
    reserves_cfg = config.get("routing.input_reserves", {})
    budget_max_cfg = config.get("routing.budget_max", {})

    if route == "simple":
        budget = 256
        if len(user_text) > 100:
            budget = 512
        simple_reserve = int(reserves_cfg.get("simple", 1500))
        return min(budget, _SMALL_MODEL_CONTEXT - simple_reserve)

    if route == "complex-cloud":
        context = _CLOUD_CONTEXT
        input_reserve = int(reserves_cfg.get("cloud", 8000))
        budget_max = int(budget_max_cfg.get("cloud", 16384))
    else:
        # Default to complex-local
        context = int(config.get("models.complex_local.context_window", 65536))
        input_reserve = int(reserves_cfg.get("default", 4000))
        budget_max = int(budget_max_cfg.get("other", 16384))

    text_len = len(user_text)
    text_lower = user_text.lower()

    budget = budget_max

    if any(hint in text_lower for hint in _LONG_ANSWER_HINTS):
        budget = max(budget, 3072)

    _LONG_FORM_HINTS = {
        "write a story",
        "write a short story",
        "write an essay",
        "write in the style",
        "continue the story",
        "add a scene",
        "detailed",
        "generate a long",
        "full story",
        "full code",
        "comprehensive",
        "in depth",
        "in-depth",
    }
    if any(hint in text_lower for hint in _LONG_FORM_HINTS):
        budget = budget_max

    if any(hint in text_lower for hint in _SHORT_ANSWER_HINTS):
        budget = min(budget, 1536)

    estimated_input_tokens = input_reserve + (text_len // 4)
    available = context - estimated_input_tokens
    budget = min(budget, max(available, 512))

    return budget


def _check_cloud_available() -> bool:
    """Check if cloud escalation is possible (API key + enabled + circuit breaker)."""
    from src.agent.cloud.cloud_circuit_breaker import get_circuit_breaker

    profile = get_profile()
    if not profile.get("cloud_escalation_enabled", True):
        return False
    if get_circuit_breaker().is_open():
        return False
    api_key = resolve_deepseek_api_key()
    return bool(api_key)


def _check_travel_mode() -> bool:
    """Check if Travel Mode is enabled via profile or Eco-Mode."""
    travel_mode = get_profile().get("travel_mode", False)
    if not travel_mode:
        try:
            from src.api.power_monitor import ECO_MODE
            if ECO_MODE:
                travel_mode = True
        except ImportError:
            pass
    return travel_mode

def _preferred_complex_route(cloud_available: bool | None = None) -> str:
    """Default complex route: local-first, cloud on travel/fallback."""
    if cloud_available is None:
        cloud_available = _check_cloud_available()
    
    if _check_travel_mode() and cloud_available:
        return "complex-cloud"
    return "complex-local"


def _has_image_content(state: AgentState) -> bool:
    """Check if the last message contains image attachments."""
    messages = state.get("messages") or []
    if not messages:
        return False
    content = messages[-1].content
    if isinstance(content, list):
        return any(
            isinstance(block, dict) and block.get("type") == "image_url"
            for block in content
        )
    return False


_FRONTIER_HINTS = {
    "prove",
    "theorem",
    "formal proof",
    "mathematical proof",
    "symbolic",
    "calculus",
    "differential equation",
    "optimize algorithm",
    "complexity proof",
    "best possible",
    "highest quality",
    "frontier",
}


def _needs_frontier_quality(text: str) -> bool:
    """Check if the task needs frontier-class model quality."""
    lower = text.lower()
    return any(hint in lower for hint in _FRONTIER_HINTS)


def _resolve_complex_route(
    user_text: str,
    state: AgentState,
    toolbox: list[str],
    *,
    cloud_available: bool | None = None,
) -> tuple[str, list[str]]:
    """Given a complex classification, pick the specific route (local-first or cloud)."""
    if cloud_available is None:
        cloud_available = _check_cloud_available()

    scenario_id = state.get("scenario_id")
    if scenario_id == "pentest":
        return "complex-local", toolbox

    if _check_travel_mode() and cloud_available:
        return "complex-cloud", toolbox

    text_len = len(user_text)
    estimated_input = 4000 + (text_len // 4)
    _LOCAL_MAX_CONTEXT = int(config.get("models.complex_local.context_window", 65536))

    if estimated_input > _LOCAL_MAX_CONTEXT * 0.80:
        if cloud_available:
            return "complex-cloud", toolbox

    if _needs_frontier_quality(user_text):
        if cloud_available:
            return "complex-cloud", toolbox

    return "complex-local", toolbox


def _build_router_metadata(
    route: str,
    confidence: float = 0.5,
    reasoning: str = "",
    classification_source: str = "llm_classifier",
    cloud_available: bool = False,
    has_images: bool = False,
    task_category: str = "general",
    estimated_tokens: int = 4096,
    web_on: bool = True,
    swap_decision: str = "not_needed",
    swap_from: str | None = None,
    swap_to: str | None = None,
) -> dict:
    """Build the router_metadata dict for router_info telemetry event."""
    return {
        "route": route,
        "confidence": round(confidence, 4),
        "reasoning": reasoning,
        "swap_decision": swap_decision,
        "swap_from": swap_from,
        "swap_to": swap_to,
        "classification_source": classification_source,
        "token_budget": estimated_tokens,
        "cloud_available": cloud_available,
        "features": {
            "has_images": has_images,
            "task_category": task_category,
            "estimated_tokens": estimated_tokens,
            "web_intent": web_on
            and bool(any(h in reasoning.lower() for h in ["web", "search"])),
        },
    }


def _resolve_memory_gate(
    decision: str,
    *,
    parsed_needs: bool | None,
    user_text: str,
    knowledge_context: str | None,
) -> bool:
    """Resolve whether vector memory retrieval should run this turn."""
    if decision == "simple":
        return False
    if parsed_needs is not None:
        return bool(parsed_needs)
    if _knowledge_cache_likely_answers(user_text, knowledge_context):
        return False
    return True


_KNOWLEDGE_CACHE_STOP_WORDS = frozenset(
    {
        "what",
        "who",
        "where",
        "when",
        "why",
        "how",
        "the",
        "and",
        "for",
        "are",
        "was",
        "were",
        "with",
        "from",
        "that",
        "this",
        "about",
        "your",
        "you",
        "our",
        "can",
        "could",
        "would",
        "should",
        "tell",
        "give",
        "please",
    }
)


def _knowledge_cache_likely_answers(
    user_text: str, knowledge_context: str | None
) -> bool:
    """Heuristic: injected knowledge cache overlaps the user's question."""
    kc = (knowledge_context or "").strip()
    if not kc or kc.lower() in {"none", "n/a"}:
        return False
    if len(kc) < 20:
        return False

    keywords = [
        w
        for w in re.findall(r"[a-z0-9]{3,}", user_text.lower())
        if w not in _KNOWLEDGE_CACHE_STOP_WORDS
    ]
    if len(keywords) < 2:
        return False

    kc_lower = kc.lower()
    hits = sum(1 for w in keywords if w in kc_lower)
    return hits >= max(2, len(keywords) // 3)


def _resolve_scenario_id(parsed_scenario: str | None, user_text: str) -> str | None:
    if parsed_scenario in ("pentest", "research", "study"):
        return parsed_scenario
    from src.memory.scenarios import detect_scenario_id

    return detect_scenario_id(user_text)


def _memory_gate_fields(
    state: AgentState,
    user_text: str,
    decision: str,
    *,
    parsed_needs: bool | None = None,
    parsed_scenario: str | None = None,
    force_needs: bool | None = None,
) -> dict:
    needs = (
        force_needs
        if force_needs is not None
        else _resolve_memory_gate(
            decision,
            parsed_needs=parsed_needs,
            user_text=user_text,
            knowledge_context=state.get("knowledge_context"),
        )
    )
    resolved_scenario = _resolve_scenario_id(parsed_scenario, user_text)
    if resolved_scenario is None:
        resolved_scenario = state.get("scenario_id")
    return {
        "needs_memory_retrieval": needs,
        "scenario_id": resolved_scenario,
    }
