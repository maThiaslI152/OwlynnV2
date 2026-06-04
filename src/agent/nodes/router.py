"""
Router Node — 5-way routing with toolbox selection and HITL clarification.
--------------------------------------------------------------------------
Uses the Small LLM to classify: simple vs complex, then selects the
appropriate M-tier variant or cloud escalation for complex tasks.
Also selects toolbox categories for dynamic tool loading.
"""

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from src.agent.state import AgentState
from src.agent.llm import get_small_llm, LLMPool
from src.config.secret_store import resolve_deepseek_api_key
from src.config.config_loader import config
from src.config.settings import MEDIUM_DEFAULT_CONTEXT, MEDIUM_LONGCTX_CONTEXT, CLOUD_CONTEXT
from src.memory.user_profile import get_profile
from src.tools.skills import SkillMatcher, MatchResult, _default_loader as _skill_loader

from src.config.audit_log import audit_info, audit_debug, audit_warn
from src.config.log_middleware import log_node

import json
import re
import logging

logger = logging.getLogger(__name__)


# ── Context window constants (backward compat, sourced from centralized config) ──
_MEDIUM_DEFAULT_CONTEXT = MEDIUM_DEFAULT_CONTEXT
_MEDIUM_LONGCTX_CONTEXT = MEDIUM_LONGCTX_CONTEXT
_CLOUD_CONTEXT = CLOUD_CONTEXT
_SMALL_MODEL_CONTEXT = int(config.get("models.small.context_window", 4096))

# Budget tiers from centralized config
_BUDGET_TIERS_RAW = config.get("routing.budget_tiers", [
    [40, 256], [150, 512], [400, 1536], [800, 3072], [1600, 4096],
])
_BUDGET_TIERS = [(int(t[0]), int(t[1])) for t in _BUDGET_TIERS_RAW]

# Keywords that signal the user wants a long/detailed answer
_LONG_ANSWER_HINTS = {
    "explain", "write", "create", "implement", "build", "generate",
    "refactor", "analyze", "compare", "review", "summarize", "translate",
    "step by step", "in detail", "full code", "complete",
}

# Keywords that signal a short answer is fine
_SHORT_ANSWER_HINTS = {
    "yes or no", "true or false", "which one", "what is",
    "how much", "how many", "when", "where",
}


def estimate_token_budget(user_text: str, route: str) -> int:
    """
    Estimate a reasonable max_tokens budget for the response.

    Uses per-tier context windows:
    - simple → _SMALL_MODEL_CONTEXT (4096) with 1500 reserve
    - complex-cloud → _CLOUD_CONTEXT (131072) with 8000 reserve, budget_max 16384
    - complex-longctx → _MEDIUM_LONGCTX_CONTEXT (131072) with 4000 reserve, budget_max 8192
    - complex-default, complex-vision → _MEDIUM_DEFAULT_CONTEXT (100000) with 4000 reserve, budget_max 8192
    """
    reserves_cfg = config.get("routing.input_reserves", {})
    budget_max_cfg = config.get("routing.budget_max", {})

    if route == "simple":
        budget = 256
        if len(user_text) > 100:
            budget = 512
        simple_reserve = int(reserves_cfg.get("simple", 1500))
        return min(budget, _SMALL_MODEL_CONTEXT - simple_reserve)

    # Determine context window and reserves based on route
    if route == "complex-cloud":
        context = _CLOUD_CONTEXT
        input_reserve = int(reserves_cfg.get("cloud", 8000))
        budget_max = int(budget_max_cfg.get("cloud", 16384))
    elif route == "complex-longctx":
        context = _MEDIUM_LONGCTX_CONTEXT
        input_reserve = int(reserves_cfg.get("longctx", 4000))
        budget_max = int(budget_max_cfg.get("other", 8192))
    else:  # complex-default, complex-vision
        context = _MEDIUM_DEFAULT_CONTEXT
        input_reserve = int(reserves_cfg.get("default", 4000))
        budget_max = int(budget_max_cfg.get("other", 8192))

    text_len = len(user_text)
    text_lower = user_text.lower()

    # Start with tier-based estimate from input length
    budget = budget_max
    for max_chars, tier_budget in _BUDGET_TIERS:
        if text_len <= max_chars:
            budget = min(tier_budget, budget_max)
            break

    # Boost if the user is asking for something that needs a long answer
    if any(hint in text_lower for hint in _LONG_ANSWER_HINTS):
        budget = max(budget, 3072)

    # Long-form creative/writing tasks need the full budget
    _LONG_FORM_HINTS = {
        "write a story", "write a short story", "write an essay",
        "write in the style", "continue the story", "add a scene",
        "detailed", "generate a long", "full story", "full code",
        "comprehensive", "in depth", "in-depth",
    }
    if any(hint in text_lower for hint in _LONG_FORM_HINTS):
        budget = budget_max

    # Cap if the user is asking a short-answer question
    if any(hint in text_lower for hint in _SHORT_ANSWER_HINTS):
        budget = min(budget, 1536)

    # Longer input text eats into the context window — reduce output budget
    # Rough heuristic: ~4 chars per token for English
    estimated_input_tokens = input_reserve + (text_len // 4)
    available = context - estimated_input_tokens
    budget = min(budget, max(available, 512))  # Never go below 512 for complex

    return budget


# ── Router prompt with toolbox classification ────────────────────────────
ROUTER_PROMPT = """Classify in one shot. No reasoning, no preamble, no markdown.

simple = greetings/thanks/small talk OR a direct question answerable without tools or heavy reasoning.
complex = code/math/writing, multi-step work, OR needs live web/news/weather/prices.

Toolbox categories (pick one or more, or "all" if unsure):
- web_search: web lookup, live data, current information, news, weather, prices
- file_ops: read/write/edit/list/delete workspace files
- data_viz: create documents/spreadsheets/presentations/PDFs, run code, data analysis, charts
- productivity: task management, todos, skills, workflow templates
- memory: recall past conversations, user preferences, stored facts
- all: when unsure or multiple categories needed

Reply with exactly one JSON object (nothing else):
{{"routing":"simple"|"complex","confidence":0.0-1.0,"toolbox":"toolbox_name"|["name1","name2"]}}

Message: {user_input}

JSON:"""


def _last_user_text(state: AgentState) -> str:
    """Flatten last message content to plain text (handles string or multimodal list)."""
    messages = state.get("messages") or []
    if not messages:
        return ""
    raw = messages[-1].content
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
        return "\n".join(parts) if parts else ""
    return str(raw)


def parse_routing(content: str) -> tuple[str, float, list[str]]:
    """Extract routing decision, confidence, and toolbox from LLM response."""
    try:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            decision = parsed.get("routing", "complex").lower().strip()
            if decision not in ("simple", "complex"):
                decision = "complex"
            confidence = float(parsed.get("confidence", 0.5))
            toolbox = parsed.get("toolbox", "all")
            if isinstance(toolbox, str):
                toolbox = [toolbox]
            return decision, confidence, toolbox
    except Exception:
        pass
    return "complex", 0.5, ["all"]


# ── Image / frontier detection helpers ───────────────────────────────────

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
    "prove", "theorem", "formal proof", "mathematical proof",
    "symbolic", "calculus", "differential equation",
    "optimize algorithm", "complexity proof",
    "best possible", "highest quality", "frontier",
}


def _needs_frontier_quality(text: str) -> bool:
    """Check if the task needs frontier-class model quality."""
    lower = text.lower()
    return any(hint in lower for hint in _FRONTIER_HINTS)


# When web search is enabled, these usually need the large model + tools.
_WEBISH_HINTS = (
    "weather",
    "forecast",
    "temperature in",
    "humidity in",
    "stock price",
    "crypto price",
    "news ",
    "breaking",
    "search the web",
    "search for",
    "look up",
    "google ",
    "current price",
    "price in ",
    "price",
    "today's ",
    "right now",
    "live score",
)


def _resolve_complex_route(
    user_text: str,
    state: AgentState,
    toolbox: list[str],
) -> tuple[str, list[str]]:
    """
    Stage 2: given a complex classification, pick the specific route.

    Returns (route, toolbox) — toolbox may be adjusted.
    """
    # 1. Image attachments → complex-vision
    if _has_image_content(state):
        return "complex-vision", toolbox

    # 2. Estimate input tokens (rough: ~4 chars per token)
    text_len = len(user_text)
    estimated_input = 4000 + (text_len // 4)  # input_reserve + message tokens

    # 3. Exceeds Medium_LongCtx → cloud
    if estimated_input > _MEDIUM_LONGCTX_CONTEXT * 0.80:
        return "complex-cloud", toolbox

    # 4. Exceeds 80% of Medium_Default → longctx
    if estimated_input > _MEDIUM_DEFAULT_CONTEXT * 0.80:
        return "complex-longctx", toolbox

    # 5. Frontier-quality indicators → cloud
    if _needs_frontier_quality(user_text):
        return "complex-cloud", toolbox

    # 6. Default
    return "complex-default", toolbox


def _check_cloud_available() -> bool:
    """Check if cloud escalation is possible (API key + enabled)."""
    profile = get_profile()
    if not profile.get("cloud_escalation_enabled", True):
        return False
    # Check API key via secret store resolution (Keychain → env var → profile)
    api_key = resolve_deepseek_api_key()
    return bool(api_key)


@log_node("router")
async def router_node(state: AgentState) -> AgentState:
    """Route to simple or complex path with 5-way variant selection and toolbox."""
    messages = state.get("messages", [])
    if not messages:
        return {"route": "complex-default", "selected_toolboxes": ["all"],
                "router_clarification_used": False, "skill_matched": None,
                "router_metadata": _build_router_metadata("complex-default", classification_source="empty_state_fallback")}

    user_text = _last_user_text(state)
    user_lower = user_text.lower()
    classification_source = "keyword_bypass"
    swap_decision = "not_needed"
    swap_from = None
    swap_to = None
    cloud_available = _check_cloud_available()
    has_images = _has_image_content(state)
    web_on = state.get("web_search_enabled")
    if web_on is None:
        web_on = True

    # ── Route detection with tracking metadata ─────────────────────────────

    # If the conversation already used tools or the large model, stay on complex.
    if len(messages) > 2:
        has_tool_history = any(
            getattr(m, "type", None) == "tool" or hasattr(m, "tool_calls") and m.tool_calls
            for m in messages[:-1]
        )
        if has_tool_history:
            logger.info("[router] Complex path — conversation has tool history")
            route, toolbox = _resolve_complex_route(user_text, state, ["all"])
            budget = estimate_token_budget(user_text, route)
            metadata = _build_router_metadata(
                route, confidence=0.95, reasoning="tool_history",
                classification_source="deterministic", cloud_available=cloud_available,
                has_images=has_images, task_category="tool_followup", estimated_tokens=budget, web_on=web_on,
                swap_from=state.get("current_medium_model"), swap_to=None,
            )
            audit_info("agent.lifecycle", "router_decision", route=route, confidence=0.95,
                        source="tool_history", task_category="tool_followup")
            return {"route": route, "token_budget": budget,
                    "selected_toolboxes": toolbox, "router_clarification_used": False,
                    "skill_matched": None,
                    "router_metadata": metadata}

    if web_on and any(h in user_lower for h in _WEBISH_HINTS):
        logger.info("[router] Complex path — web/live-data intent (web_search enabled)")
        route, toolbox = _resolve_complex_route(user_text, state, ["web_search"])
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route, confidence=0.9, reasoning="web_intent_detected",
            classification_source="deterministic", cloud_available=cloud_available,
            has_images=has_images, task_category="web_search", estimated_tokens=budget, web_on=web_on,
        )
        audit_info("agent.lifecycle", "router_decision", route=route, confidence=0.9,
                    source="web_intent", task_category="web_search")
        return {"route": route, "token_budget": budget,
                "selected_toolboxes": toolbox, "router_clarification_used": False,
                "skill_matched": None,
                "router_metadata": metadata}

    # Attachments saved to workspace need the large model + tools.
    if (
        "[file:" in user_lower
        or "uploaded to workspace" in user_lower
        or "workspace file" in user_lower
    ):
        logger.info("[router] Complex path — workspace / attachment context")
        route, toolbox = _resolve_complex_route(user_text, state, ["file_ops"])
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route, confidence=0.9, reasoning="workspace_attachment_detected",
            classification_source="deterministic", cloud_available=cloud_available,
            has_images=has_images, task_category="file_operations", estimated_tokens=budget, web_on=web_on,
        )
        audit_info("agent.lifecycle", "router_decision", route=route, confidence=0.9,
                    source="file_attachment", task_category="file_operations")
        return {"route": route, "token_budget": budget,
                "selected_toolboxes": toolbox, "router_clarification_used": False,
                "skill_matched": None,
                "router_metadata": metadata}

    # Quick keyword check to bypass LLM for obvious simple cases.
    # Use word-boundary matching to avoid substring false positives
    # (e.g. "hi" matching inside "which", "this", "Chiang").
    _greeting_pattern = re.compile(
        r"\b(hello|hi|hey|thanks|thank\s+you|bye|goodbye)\b", re.IGNORECASE
    )
    _time_date_pattern = re.compile(r"\b(what\s+time|what\s+date)\b", re.IGNORECASE)
    if _greeting_pattern.search(user_text) or _time_date_pattern.search(user_text):
        logger.info("[router] Simple path - keyword match")
        budget = estimate_token_budget(user_text, "simple")
        metadata = _build_router_metadata(
            "simple", confidence=0.98, reasoning="keyword_match",
            classification_source="keyword_bypass", cloud_available=cloud_available,
            has_images=has_images, task_category="greeting", estimated_tokens=budget, web_on=web_on,
        )
        audit_info("agent.lifecycle", "router_decision", route="simple", confidence=0.98,
                    source="keyword_bypass", task_category="greeting")
        return {"route": "simple", "token_budget": budget,
                "selected_toolboxes": ["all"], "router_clarification_used": False,
                "skill_matched": None,
                "router_metadata": metadata}

    # ── Deterministic complex-route bypasses ──────────────────────────
    # Code review / refactoring requests need the 9B model for depth.
    _code_review_hints = (
        "review this code", "code review", "review the code",
        "check this code", "audit this code", "inspect this code",
        "code quality", "improve this code", "refactor this",
        "find bugs", "bug in this code", "fix this code",
        "review this python", "review this function",
    )
    if any(hint in user_lower for hint in _code_review_hints):
        logger.info("[router] Complex path — code review detected")
        budget = estimate_token_budget(user_text, "complex-default")
        metadata = _build_router_metadata(
            "complex-default", confidence=0.95, reasoning="code_review_bypass",
            classification_source="deterministic", cloud_available=cloud_available,
            has_images=has_images, task_category="code_review", estimated_tokens=budget, web_on=web_on,
        )
        audit_info("agent.lifecycle", "router_decision", route="complex-default", confidence=0.95,
                    source="code_review_bypass", task_category="code_review")
        return {"route": "complex-default", "token_budget": budget,
                "selected_toolboxes": ["file_ops"], "router_clarification_used": False,
                "skill_matched": None,
                "router_metadata": metadata}

    # Explain / compare / trade-off questions need the 9B model for depth.
    _explain_compare_hints = (
        "explain how", "explain the", "compare", "trade-off",
        "trade off", "differences between", "pros and cons",
        "how does", "how do", "in depth",
    )
    if any(hint in user_lower for hint in _explain_compare_hints):
        logger.info("[router] Complex path — explain/compare detected")
        budget = estimate_token_budget(user_text, "complex-default")
        metadata = _build_router_metadata(
            "complex-default", confidence=0.95, reasoning="explain_compare_bypass",
            classification_source="deterministic", cloud_available=cloud_available,
            has_images=has_images, task_category="technical_explanation", estimated_tokens=budget, web_on=web_on,
        )
        audit_info("agent.lifecycle", "router_decision", route="complex-default", confidence=0.95,
                    source="explain_compare_bypass", task_category="technical_explanation")
        return {"route": "complex-default", "token_budget": budget,
                "selected_toolboxes": ["all"], "router_clarification_used": False,
                "skill_matched": None,
                "router_metadata": metadata}

    # Creative writing / story generation needs the 9B model for quality.
    _creative_writing_hints = (
        "write a story", "write a short story", "continue the story",
        "creative writing", "write in the style of", "write a poem",
        "write an essay", "sci-fi story", "science fiction story",
        "story opening", "narrative",
    )
    if any(hint in user_lower for hint in _creative_writing_hints):
        logger.info("[router] Complex path — creative writing detected")
        route, toolbox = _resolve_complex_route(user_text, state, ["all"])
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route, confidence=0.95, reasoning="creative_writing_bypass",
            classification_source="deterministic", cloud_available=cloud_available,
            has_images=has_images, task_category="creative_writing", estimated_tokens=budget, web_on=web_on,
        )
        audit_info("agent.lifecycle", "router_decision", route=route, confidence=0.95,
                    source="creative_writing_bypass", task_category="creative_writing")
        return {"route": route, "token_budget": budget,
                "selected_toolboxes": toolbox, "router_clarification_used": False,
                "skill_matched": None,
                "router_metadata": metadata}

    # ── Stage 1: Ask Small LLM for simple/complex + toolbox ──────────────
    small_llm = await get_small_llm()
    decision = "complex"
    confidence = 0.5
    toolbox = ["all"]

    try:
        router_llm = small_llm.bind(
            temperature=float(config.get("router_llm.temperature", 0.05)),
            max_tokens=int(config.get("router_llm.max_tokens", 512)),
        )
        response = await router_llm.ainvoke(
            [HumanMessage(
                content=ROUTER_PROMPT.format(
                    user_input=json.dumps(user_text[:int(config.get("routing.max_input_chars", 500))])
                )
            )]
        )
        decision, confidence, toolbox = parse_routing(response.content)
        classification_source = "llm_classifier"
    except Exception as e:
        logger.error(f"[router] Error during routing: {e}")
        audit_warn("agent.lifecycle", "router_llm_error", error=str(e)[:120])
        decision, confidence, toolbox = "complex", 0.5, ["all"]
        classification_source = "llm_classifier"

    # ── HITL clarification and proactive skill matching ────────────────
    profile = get_profile()
    router_hitl_enabled = profile.get("router_hitl_enabled", True)
    routing_confidence_threshold = float(profile.get("route_confidence_threshold") or config.get("routing.confidence_threshold", 0.6))
    skill_clarification_threshold = float(profile.get("skill_clarification_threshold") or config.get("routing.skill_clarification_threshold", 0.5))

    router_clarification_used = False
    skill_matched = None

    if router_hitl_enabled:
        # ── Run skill matcher (safe fallback if it fails) ──
        match_result = None
        try:
            matcher = SkillMatcher(_skill_loader)
            match_result = matcher.match_with_confidence(user_text, top_k=5)
        except Exception as e:
            logger.warning("[router] Skill matcher failed: %s", e)
            match_result = MatchResult(
                is_ambiguous=True,
                candidate_skills=[],
                ambiguity_reason="Skill matching unavailable",
            )

        # ── Two independent HITL triggers ──────────────────────────
        hitl_needed = (
            confidence < routing_confidence_threshold      # LLM uncertain
            or match_result.is_ambiguous                    # Skill ambiguous
        )

        # When skill matcher found a confident match, skip HITL even
        # if the LLM router confidence is low — the skill signal is stronger.
        if (
            hitl_needed
            and not match_result.is_ambiguous
            and match_result.best_score >= skill_clarification_threshold
        ):
            hitl_needed = False
            logger.info(
                "[router] Skipping HITL — confident skill match: %s (%.0f%%)",
                match_result.top_match.name, match_result.best_score * 100,
            )
            audit_info("agent.hitl", "router_hitl_skipped",
                        reason="confident_skill_match",
                        skill=match_result.top_match.name,
                        score=round(match_result.best_score, 3))

        # When the request is a build/create action, delegate to the
        # scope_clarify node instead of asking skill-routing questions.
        # scope_clarify asks the *right* questions (language, UI, scope),
        # not "which skill/toolbox?", which the user can't answer well.
        if hitl_needed:
            try:
                from src.agent.hitl.scope_heuristics import needs_clarification
                if needs_clarification(user_text)[0]:
                    hitl_needed = False
                    logger.info(
                        "[router] Delegating to scope_clarify — build/create request detected: %r",
                        user_text[:80],
                    )
                    audit_info("agent.hitl", "router_delegated_to_scope_clarify",
                                reason="build_create_request")
            except ImportError:
                pass  # heuristic module unavailable; fall through to router HITL

        # HITL requires a checkpointer AND an interactive context.
        # In API mode (stateless) there is no human to respond to interrupts,
        # so we must auto-resolve or fall through without pausing.
        _can_interrupt = False
        try:
            from langgraph.config import get_config as _get_config
            _cp = _get_config().get("configurable", {}).get("__pregel_checkpointer")
            _can_interrupt = _cp is not None
        except RuntimeError:
            pass  # outside graph context

        # API/non-interactive mode: do NOT pause the graph — auto-resolve
        if state.get("mode") in ("api", "noninteractive"):
            _can_interrupt = False

        if hitl_needed and _can_interrupt:
            # ── Build interrupt payload and PAUSE the graph ──────
            # Only catch context/checkpointer errors (RuntimeError, ValueError).
            # GraphInterrupt must NOT be caught — it pauses the graph properly.
            if match_result.is_ambiguous and match_result.candidate_skills:
                choices: list[dict] = []
                for skill, score in match_result.candidate_skills[:5]:
                    skill_toolbox = _toolbox_for_skill(skill)
                    choices.append({
                        "label": f"{skill.name} — {skill.description} ({score:.0%})",
                        "route": "complex-default",
                        "toolbox": skill_toolbox,
                        "skill_name": skill.file,
                    })
                choices.append({
                    "label": "Others (describe what you need)",
                    "route": "complex-default",
                    "toolbox": ["all"],
                    "skill_name": None,
                    "allows_user_input": True,
                })
                try:
                    clarification = interrupt({
                        "type": "ask_user",
                        "question": (
                            "I'm not sure which approach fits best — "
                            f"{match_result.ambiguity_reason}\n"
                            "Which would help you most?"
                        ),
                        "choices": choices,
                    })
                    audit_info("agent.hitl", "router_hitl_interrupt",
                                reason="skill_ambiguity", candidate_count=len(choices) - 1)
                except (RuntimeError, ValueError):
                    logger.debug("[router] HITL unavailable (no checkpointer or outside graph context)")
                    clarification = None
            else:
                try:
                    clarification = interrupt({
                        "type": "ask_user",
                        "question": "I'm not sure how to handle this. What would you prefer?",
                        "choices": [
                            {"label": "Search the web", "route": "complex-default", "toolbox": ["web_search"]},
                            {"label": "Work with local files", "route": "complex-default", "toolbox": ["file_ops"]},
                            {"label": "Create documents/visualizations", "route": "complex-default", "toolbox": ["data_viz"]},
                            {"label": "Use cloud model for higher quality", "route": "complex-cloud", "toolbox": ["all"]},
                            {"label": "Just answer directly", "route": "complex-default", "toolbox": ["all"]},
                        ],
                    })
                    audit_info("agent.hitl", "router_hitl_interrupt",
                                reason="low_confidence", confidence=round(confidence, 3))
                except (RuntimeError, ValueError):
                    logger.debug("[router] HITL unavailable (no checkpointer or outside graph context)")
                    clarification = None

            # ── Resume: unwrap the backend's {"answer": ...} wrapper ──
            if isinstance(clarification, dict) and "answer" in clarification and isinstance(clarification["answer"], dict):
                clarification = clarification["answer"]

            if clarification is not None:
                router_clarification_used = True

                # ── Handle "Others" free-text re-match ──────────────
                if isinstance(clarification, dict) and clarification.get("allows_user_input") and clarification.get("user_input"):
                    refined = clarification["user_input"].strip()
                    try:
                        re_match = matcher.match_with_confidence(refined, top_k=5)
                    except Exception:
                        re_match = MatchResult(is_ambiguous=True, candidate_skills=[], ambiguity_reason="")
                    if re_match.candidate_skills:
                        top = re_match.candidate_skills[0]
                        re_toolbox = _toolbox_for_skill(top[0])
                        logger.info(
                            "[router] HITL 'Others' re-match → skill=%s score=%.0f%%",
                            top[0].name, top[1] * 100,
                        )
                        audit_info("agent.hitl", "router_hitl_others_rematch",
                                    skill=top[0].name, score=round(top[1], 3))
                        budget = estimate_token_budget(user_text, "complex-default")
                        metadata = _build_router_metadata(
                            "complex-default", confidence=0.8, reasoning="hitl_others_rematch",
                            classification_source="hitl", cloud_available=cloud_available,
                            has_images=has_images, task_category="from_hitl", estimated_tokens=budget, web_on=web_on,
                        )
                        return {
                            "route": "complex-default", "token_budget": budget,
                            "selected_toolboxes": re_toolbox,
                            "router_clarification_used": True,
                            "skill_matched": None,
                            "router_metadata": metadata,
                        }
                    # Fall through to default complex if re-match also fails

                # ── Standard HITL choice handling ────────────────────
                decision = "complex"
                toolbox = clarification.get("toolbox", ["all"]) if isinstance(clarification, dict) else ["all"]
                route_override = clarification.get("route", "complex-default") if isinstance(clarification, dict) else "complex-default"
                logger.info("[router] HITL clarification → route=%s, toolbox=%s", route_override, toolbox)
                audit_info("agent.hitl", "router_hitl_resolved", route=route_override, toolbox=toolbox)
                budget = estimate_token_budget(user_text, route_override)
                if route_override == "complex-cloud" and not cloud_available:
                    route_override = "complex-default"
                    logger.warning("[router] Cloud unavailable, falling back to complex-default")
                    audit_warn("agent.hitl", "router_hitl_cloud_unavailable",
                                requested="complex-cloud", fallback="complex-default")
                metadata = _build_router_metadata(
                    route_override, confidence=0.8, reasoning="hitl_clarification",
                    classification_source="hitl", cloud_available=cloud_available,
                    has_images=has_images, task_category="from_hitl", estimated_tokens=budget, web_on=web_on,
                )
                return {
                    "route": route_override, "token_budget": budget,
                    "selected_toolboxes": toolbox,
                    "router_clarification_used": True,
                    "skill_matched": None,
                    "router_metadata": metadata,
                }

        elif hitl_needed:
            logger.debug("[router] HITL needed but checkpointer unavailable — falling through to LLM route")
            audit_debug("agent.hitl", "router_hitl_checkpointer_unavailable",
                         confidence=round(confidence, 3))

        # ── No HITL: proactive skill matching ────────────────────
        if match_result.top_match and match_result.best_score >= skill_clarification_threshold:
            skill_toolbox = _toolbox_for_skill(match_result.top_match)
            skill_matched = {
                "name": match_result.top_match.name,
                "toolbox": skill_toolbox,
                "score": match_result.best_score,
            }
            if set(skill_toolbox) != set(toolbox) and toolbox != ["all"]:
                logger.info(
                    "[router] Skill-driven toolbox: LLM=%s → skill=%s",
                    toolbox, skill_toolbox,
                )
                audit_info("agent.lifecycle", "router_skill_toolbox_override",
                            llm_toolbox=toolbox, skill_toolbox=skill_toolbox)
                toolbox = skill_toolbox

    # ── Finalize route ───────────────────────────────────────────────────
    if decision == "simple":
        budget = estimate_token_budget(user_text, "simple")
        logger.info(f"[router] → simple (confidence={confidence:.2f})")
        metadata = _build_router_metadata(
            "simple", confidence=confidence, reasoning="llm_classified_simple",
            classification_source=classification_source, cloud_available=cloud_available,
            has_images=has_images, task_category="simple_conversation", estimated_tokens=budget, web_on=web_on,
        )
        audit_info("agent.lifecycle", "router_decision", route="simple",
                    confidence=round(confidence, 3), source=classification_source,
                    task_category="simple_conversation")
        return {"route": "simple", "token_budget": budget,
                "selected_toolboxes": toolbox, "router_clarification_used": router_clarification_used,
                "skill_matched": skill_matched,
                "router_metadata": metadata}

    # Stage 2: complex variant selection
    route, toolbox = _resolve_complex_route(user_text, state, toolbox)

    # If cloud route but cloud unavailable, downgrade
    swap_from_route = route
    if route == "complex-cloud" and not cloud_available:
        estimated_input = 4000 + (len(user_text) // 4)
        if estimated_input > _MEDIUM_DEFAULT_CONTEXT * 0.80:
            route = "complex-longctx"
        else:
            route = "complex-default"
        logger.warning(f"[router] Cloud unavailable, downgraded from complex-cloud to {route}")
        audit_warn("agent.model", "router_cloud_downgrade",
                    from_route="complex-cloud", to_route=route, reason="cloud_unavailable")
        swap_decision = "swapped"
        swap_to = route

    budget = estimate_token_budget(user_text, route)
    task_type = _detect_task_type(user_text)
    metadata = _build_router_metadata(
        route, confidence=confidence, reasoning=f"llm_classified_complex:{task_type}",
        classification_source=classification_source, cloud_available=cloud_available,
        has_images=has_images, task_category=task_type, estimated_tokens=budget, web_on=web_on,
        swap_decision=swap_decision, swap_from=swap_from_route, swap_to=swap_to,
    )

    logger.info(f"[router] → {route} (confidence={confidence:.2f}, toolbox={toolbox})")
    audit_info("agent.lifecycle", "router_decision", route=route,
                confidence=round(confidence, 3), source=classification_source,
                task_category=task_type, toolbox=toolbox)
    return {"route": route, "token_budget": budget,
            "selected_toolboxes": toolbox, "router_clarification_used": router_clarification_used,
            "skill_matched": skill_matched,
            "router_metadata": metadata}


# ── Skill category → toolbox fallback map ──────────────────────────────
_SKILL_CATEGORY_TOOLBOX: dict[str, list[str]] = {
    "research": ["web_search"],
    "writing": ["data_viz"],
    "data": ["data_viz"],
    "productivity": ["productivity"],
    "communication": ["data_viz"],
}


def _toolbox_for_skill(skill) -> list[str]:
    """Derive router toolbox categories from a SkillDefinition.

    Priority order:
    1. Skill's own ``tools_used`` field — map tool names to toolbox categories
    2. Category fallback via ``_SKILL_CATEGORY_TOOLBOX``
    3. ``["all"]`` when nothing matches
    """
    from src.tools.skills import SkillDefinition

    # ── Stage 1: tools_used → toolbox mapping ──────────────────────────
    if isinstance(skill, SkillDefinition) and skill.tools_used:
        toolbox: list[str] = []
        tools = [t.lower() for t in skill.tools_used]
        if any("web" in t or "fetch" in t or "search" in t or "http" in t for t in tools):
            toolbox.append("web_search")
        if any("file" in t or "read" in t or "write" in t or "edit" in t
               or "dir" in t or "list" in t or "path" in t for t in tools):
            toolbox.append("file_ops")
        if any("data" in t or "viz" in t or "chart" in t or "graph" in t
               or "plot" in t or "document" in t for t in tools):
            toolbox.append("data_viz")
        if any("terminal" in t or "shell" in t or "run" in t or "execute" in t
               or "bash" in t or "notebook" in t for t in tools):
            toolbox.append("productivity")
        if toolbox:
            return toolbox

    # ── Stage 2: category fallback ─────────────────────────────────────
    toolbox = _SKILL_CATEGORY_TOOLBOX.get(skill.category, ["all"])

    # ── Stage 3: amend web+file tools even when category already matched ─
    if isinstance(skill, SkillDefinition) and skill.tools_used:
        tools = [t.lower() for t in skill.tools_used]
        if any("web" in t or "fetch" in t for t in tools) and "web_search" not in toolbox:
            toolbox.insert(0, "web_search")
        if any("file" in t or "read" in t or "write" in t or "edit" in t for t in tools) and "file_ops" not in toolbox:
            toolbox.insert(0, "file_ops")

    return toolbox


def _detect_task_type(text: str) -> str:
    """Heuristic task category detection for router telemetry."""
    lower = text.lower()
    if any(hint in lower for hint in _WEBISH_HINTS):
        return "web_search"
    if any(kw in lower for kw in ("write", "create", "implement", "build", "generate", "refactor", "code")):
        return "coding"
    if any(kw in lower for kw in ("explain", "analyze", "compare", "review", "summarize")):
        return "analysis"
    if any(kw in lower for kw in ("translate", "convert")):
        return "translation"
    return "general"


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
            "web_intent": web_on and bool(any(h in reasoning.lower() for h in ["web", "search"])),
        },
    }


# ── Chat title generation (unchanged) ───────────────────────────────────

CHAT_TITLE_PROMPT = """You are a helpful assistant that proposes a short chat title.

Rules:
- Output ONLY valid JSON (no markdown, no extra keys).
- Title must be concise and human-friendly.
- Prefer the main intent/topic from the user's message.

JSON format:
{{"title":"..."}}

User message: {user_input}
Attached file names: {file_names}
"""


def _parse_title_json(content: str) -> str:
    """
    Best-effort extraction of `{"title":"..."}` from model output.
    Returns empty string if parsing fails.
    """
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return ""
        parsed = json.loads(match.group(0))
        title = str(parsed.get("title", "")).strip()
        return title
    except Exception:
        return ""


async def generate_chat_title_router_llm(
    user_text: str,
    file_names: list[str] | None = None,
) -> str:
    """
    Generate a chat title using the router's small LLM.

    This is intentionally lightweight: we only ask for a single JSON title object.
    Falls back to a truncated excerpt of the user message when the LLM is unavailable.
    """
    user_text = str(user_text or "").strip()
    if not user_text:
        return ""

    file_names = file_names or []
    joined_files = ", ".join([str(n).strip() for n in file_names if n])
    joined_files = joined_files[:int(config.get("file_decode.filename_join_max_chars", 400))]

    # Try LLM-based title generation
    try:
        small_llm = await get_small_llm()

        router_llm = small_llm.bind(
            temperature=float(config.get("chat_title.temperature", 0.2)),
            max_tokens=int(config.get("chat_title.max_tokens", 64)),
        )
        response = await router_llm.ainvoke(
            [HumanMessage(content=CHAT_TITLE_PROMPT.format(
                user_input=user_text[:int(config.get("file_decode.user_text_preview_chars", 1000))],
                file_names=joined_files
            ))]
        )

        title = _parse_title_json(getattr(response, "content", "") or "")
        # Normalize / truncate to keep UI clean (frontend also truncates as fallback).
        title = re.sub(r"\s+", " ", title).strip()
        if title:
            return title[:60]
    except Exception:
        logger.warning("[chat_title] LLM unavailable, using text fallback")

    # Fallback: use the first meaningful line/segment of the user message
    fallback = user_text.split("\n")[0].strip()
    # Strip common prefixes that don't make good titles
    fallback = re.sub(r"^(hi|hey|hello|ok|okay|yes|no|thanks|please)[,.\s]*", "", fallback, flags=re.IGNORECASE).strip()
    if not fallback:
        from datetime import datetime
        return f"Chat \u2014 {datetime.now().strftime('%b %d, %I:%M %p')}"
    fallback = re.sub(r"\s+", " ", fallback).strip()
    return fallback[:60]
