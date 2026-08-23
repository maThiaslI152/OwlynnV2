"""Router node — classification, toolbox selection, HITL clarification.

See docs/development/EXTENDING_AGENT.md for routing change points and tests/test_router_*.py.

Decomposed into:
- deterministic.py — keyword/heuristic fast paths
- resolver.py — route resolution, cloud availability, budget estimation
- modes.py — pentest/study mode logic
- budget.py — standalone budget estimation (consolidated)
- pentest_classifier.py — pentest query categorization
- classifier.py — LLM-based classification
- feature_extractor.py — task feature extraction
- selector.py — swap-aware route selector
- models.py — data models
"""

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from src.agent.core.state import AgentState
from src.agent.llm import get_main_llm

get_small_llm = get_main_llm
from src.agent.routing.classifier import (
    parse_classification,
)
from src.agent.routing.deterministic import (
    _has_image_content,
    _is_simple_informational_query,
    _last_user_text,
    _user_wants_data_viz,
    _user_wants_file_work,
    _user_wants_screen_assist,
    check_deterministic_bypasses,
)
from src.agent.routing.modes import (
    apply_learning_mode,
    augment_toolbox_for_scenario,
    handle_pentest_mode,
)

# Re-export from decomposed modules for backward compatibility
from src.agent.routing.resolver import (
    _build_router_metadata,
    _check_cloud_available,
    _check_travel_mode,
    _memory_gate_fields,
    _preferred_complex_route,
    _resolve_complex_route,
    estimate_token_budget,
)
from src.agent.routing.resolver import (
    _needs_frontier_quality as _needs_frontier_quality,
)
from src.config.audit_log import audit_debug, audit_info
from src.config.config_loader import config
from src.config.log_middleware import log_node
from src.memory.user_profile import get_profile
from src.tools.skills import MatchResult, SkillMatcher
from src.tools.skills import _default_loader as _skill_loader


def parse_routing(
    content: str,
) -> tuple[str, float, list[str], str | None, bool, str | None]:
    """Legacy tuple-unpacking helper for route parsing."""
    classification = parse_classification(content)
    return (
        classification.route,
        classification.confidence,
        classification.toolbox,
        None,
        False,
        None,
    )


import json
import logging
import re

logger = logging.getLogger(__name__)


def _build_low_confidence_router_choices(
    user_text: str, *, cloud_available: bool | None = None
) -> list[dict]:
    """Contextual router HITL options — omit irrelevant tool paths."""
    route = _preferred_complex_route(cloud_available)
    choices: list[dict] = [
        {
            "label": "Search the web",
            "route": route,
            "toolbox": ["web_search"],
        },
    ]
    if _user_wants_file_work(user_text):
        choices.append(
            {
                "label": "Work with local files",
                "route": route,
                "toolbox": ["file_ops"],
            }
        )
    if _user_wants_data_viz(user_text):
        choices.append(
            {
                "label": "Create documents/visualizations",
                "route": route,
                "toolbox": ["data_viz"],
            }
        )
    if _user_wants_screen_assist(user_text):
        choices.append(
            {
                "label": "Read terminal or screen context",
                "route": route,
                "toolbox": ["screen_assist"],
            }
        )
    choices.append(
        {
            "label": "Just answer directly",
            "route": route,
            "toolbox": ["all"],
        }
    )
    return choices


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
        if any(
            "web" in t or "fetch" in t or "search" in t or "http" in t for t in tools
        ):
            toolbox.append("web_search")
        if any(
            "file" in t
            or "read" in t
            or "write" in t
            or "edit" in t
            or "dir" in t
            or "list" in t
            or "path" in t
            for t in tools
        ):
            toolbox.append("file_ops")
        if any(
            "data" in t
            or "viz" in t
            or "chart" in t
            or "graph" in t
            or "plot" in t
            or "document" in t
            or "notebook" in t
            for t in tools
        ):
            toolbox.append("data_viz")
        if any(
            "capture_local_terminal" in t
            or "capture_kali" in t
            or "screen_element" in t
            or "browser_context" in t
            for t in tools
        ):
            toolbox.append("screen_assist")
        if any("todo" in t or "skill" in t or "invoke" in t for t in tools):
            toolbox.append("productivity")
        if any("recall" in t or "memory" in t or "forget" in t for t in tools):
            toolbox.append("memory")
        if any(
            "flashcard" in t
            or "course_" in t
            or "study_" in t
            or "quiz_" in t
            or "mastery" in t
            or "export_study" in t
            for t in tools
        ):
            toolbox.append("study")
        if toolbox:
            return toolbox

    # ── Stage 2: category fallback ─────────────────────────────────────
    toolbox = _SKILL_CATEGORY_TOOLBOX.get(skill.category, ["all"])

    # ── Stage 3: amend web+file tools even when category already matched ─
    if isinstance(skill, SkillDefinition) and skill.tools_used:
        tools = [t.lower() for t in skill.tools_used]
        if (
            any("web" in t or "fetch" in t for t in tools)
            and "web_search" not in toolbox
        ):
            toolbox.insert(0, "web_search")
        if (
            any(
                "file" in t or "read" in t or "write" in t or "edit" in t for t in tools
            )
            and "file_ops" not in toolbox
        ):
            toolbox.insert(0, "file_ops")

    return toolbox


def _detect_task_type(text: str) -> str:
    """Heuristic task category detection for router telemetry."""
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
    lower = text.lower()
    if any(hint in lower for hint in _WEBISH_HINTS):
        return "web_search"
    if any(
        kw in lower
        for kw in (
            "write",
            "create",
            "implement",
            "build",
            "generate",
            "refactor",
            "code",
        )
    ):
        return "coding"
    if any(
        kw in lower for kw in ("explain", "analyze", "compare", "review", "summarize")
    ):
        return "analysis"
    if any(kw in lower for kw in ("translate", "convert")):
        return "translation"
    return "general"


# ── Main router node ─────────────────────────────────────────────────────


@log_node("router")
async def router_node(state: AgentState) -> AgentState:
    """Route to simple or complex path with 5-way variant selection and toolbox."""
    messages = state.get("messages", [])
    if not messages:
        empty_cloud = _check_cloud_available()
        empty_route = _preferred_complex_route(empty_cloud)
        return {
            "route": empty_route,
            "selected_toolboxes": ["all"],
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": _build_router_metadata(
                empty_route, classification_source="empty_state_fallback"
            ),
        }

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

    # ── Deterministic bypasses (delegated to deterministic.py) ───────────
    bypass_result = await check_deterministic_bypasses(
        state,
        cloud_available=cloud_available,
        has_images=has_images,
        web_on=web_on,
    )
    if bypass_result is not None:
        return bypass_result

    # ── Deterministic pentest-mode bypass (delegated to modes.py) ────────
    pentest_result = handle_pentest_mode(
        user_text,
        state,
        cloud_available=cloud_available,
        has_images=has_images,
        web_on=web_on,
    )
    if pentest_result is not None:
        return pentest_result

    # ── Stage 1: Fast routing (LLM bypassed for Local-First) ──────────────
    decision = "complex"
    confidence = 1.0
    toolbox = ["all"]
    parsed_needs: bool | None = None
    parsed_scenario: str | None = None
    execution_plan: str | None = None
    classification_source = "hardcoded_local_first"

    # ── HITL clarification and proactive skill matching ────────────────
    profile = get_profile()
    router_hitl_enabled = profile.get("router_hitl_enabled", True)
    routing_confidence_threshold = float(
        profile.get("route_confidence_threshold")
        or config.get("routing.confidence_threshold", 0.6)
    )
    skill_clarification_threshold = float(
        profile.get("skill_clarification_threshold")
        or config.get("routing.skill_clarification_threshold", 0.5)
    )

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
            confidence < routing_confidence_threshold  # LLM uncertain
            or match_result.is_ambiguous  # Skill ambiguous
        )

        if has_images:
            hitl_needed = False
            logger.info(
                "[router] Skipping HITL — image attachment present (vision route)"
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
                match_result.top_match.name,
                match_result.best_score * 100,
            )
            audit_info(
                "agent.hitl",
                "router_hitl_skipped",
                reason="confident_skill_match",
                skill=match_result.top_match.name,
                score=round(match_result.best_score, 3),
            )

        # Set skill_matched when skill match is strong and unambiguous,
        # even when HITL is not needed (high LLM confidence).
        if (
            match_result.top_match
            and not match_result.is_ambiguous
            and match_result.best_score >= skill_clarification_threshold
        ):
            skill_toolbox = _toolbox_for_skill(match_result.top_match)
            skill_matched = {
                "name": match_result.top_match.name,
                "toolbox": skill_toolbox,
                "score": match_result.best_score,
            }

        # When the request is a build/create action, delegate to the
        # scope_clarify node instead of asking skill-routing questions.
        if hitl_needed:
            try:
                from src.agent.hitl.scope_heuristics import needs_clarification

                if needs_clarification(user_text)[0]:
                    hitl_needed = False
                    logger.info(
                        "[router] Delegating to scope_clarify — build/create request detected: %r",
                        user_text[:80],
                    )
                    audit_info(
                        "agent.hitl",
                        "router_delegated_to_scope_clarify",
                        reason="build_create_request",
                    )
            except ImportError:
                pass

        # Simple factual questions — no toolbox picker.
        if (
            hitl_needed
            and confidence < routing_confidence_threshold
            and not match_result.is_ambiguous
            and _is_simple_informational_query(user_text)
        ):
            hitl_needed = False
            logger.info(
                "[router] Skipping HITL — simple informational query: %r",
                user_text[:80],
            )
            audit_info(
                "agent.hitl",
                "router_hitl_skipped",
                reason="simple_informational_query",
            )

        # HITL requires a checkpointer AND an interactive context.
        _can_interrupt = False
        try:
            from langgraph.config import get_config as _get_config

            _cp = _get_config().get("configurable", {}).get("__pregel_checkpointer")
            _can_interrupt = _cp is not None
        except RuntimeError:
            pass

        if state.get("mode") in ("api", "noninteractive"):
            _can_interrupt = False

        if get_profile().get("execution_policy") == "auto_approve":
            _can_interrupt = False

        if hitl_needed and _can_interrupt:
            if match_result.is_ambiguous and match_result.candidate_skills:
                hitl_route = _preferred_complex_route(cloud_available)
                choices: list[dict] = []
                for skill, score in match_result.candidate_skills[:5]:
                    skill_toolbox = _toolbox_for_skill(skill)
                    choices.append(
                        {
                            "label": f"{skill.name} — {skill.description} ({score:.0%})",
                            "route": hitl_route,
                            "toolbox": skill_toolbox,
                            "skill_name": skill.file,
                        }
                    )
                choices.append(
                    {
                        "label": "Others (describe what you need)",
                        "route": hitl_route,
                        "toolbox": ["all"],
                        "skill_name": None,
                        "allows_user_input": True,
                    }
                )
                try:
                    clarification = interrupt(
                        {
                            "type": "ask_user",
                            "question": (
                                "I'm not sure which approach fits best — "
                                f"{match_result.ambiguity_reason}\n"
                                "Which would help you most?"
                            ),
                            "choices": choices,
                        }
                    )
                    audit_info(
                        "agent.hitl",
                        "router_hitl_interrupt",
                        reason="skill_ambiguity",
                        candidate_count=len(choices) - 1,
                    )
                except (RuntimeError, ValueError):
                    logger.debug(
                        "[router] HITL unavailable (no checkpointer or outside graph context)"
                    )
                    clarification = None
            else:
                try:
                    clarification = interrupt(
                        {
                            "type": "ask_user",
                            "question": (
                                "I'm not quite sure what you need — can you clarify?"
                            ),
                            "choices": _build_low_confidence_router_choices(
                                user_text, cloud_available=cloud_available
                            ),
                        }
                    )
                    audit_info(
                        "agent.hitl",
                        "router_hitl_interrupt",
                        reason="low_confidence",
                        confidence=round(confidence, 3),
                    )
                except (RuntimeError, ValueError):
                    logger.debug(
                        "[router] HITL unavailable (no checkpointer or outside graph context)"
                    )
                    clarification = None

            if clarification is not None:
                if isinstance(clarification, dict):
                    chosen_route = clarification.get("route")
                    chosen_toolbox = clarification.get("toolbox")
                    chosen_skill = clarification.get("skill_name")
                    if chosen_route:
                        decision = chosen_route
                    if chosen_toolbox:
                        toolbox = chosen_toolbox
                    if chosen_skill:
                        skill_matched = chosen_skill
                    confidence = 1.0
                    classification_source = "user_clarification"
                    router_clarification_used = True
                    audit_info(
                        "agent.hitl",
                        "router_hitl_resolved",
                        source="user_clarification",
                        route=decision,
                        toolbox=toolbox,
                    )

    # ── Resolve final route ──────────────────────────────────────────────
    if decision == "simple":
        route = "simple"
    elif decision == "browser_local":
        route = "browser_local"
    elif (
        decision.startswith("complex-")
        and classification_source == "user_clarification"
    ):
        route = decision
    else:
        route, toolbox = _resolve_complex_route(
            user_text, state, toolbox, cloud_available=cloud_available
        )

    # ── Eco-Mode / Travel Mode Routing Override ──────────────────────────
    if route != "simple" and route != "browser_local" and _check_travel_mode():
        if cloud_available:
            route = "complex-cloud"
            logger.info(
                "[router] Eco-Mode/Travel Mode active: offloading to DeepSeek cloud"
            )
            classification_source = "eco_mode_battery_cloud_offload"
        else:
            route = "complex-default"
            logger.info(
                "[router] Eco-Mode active but cloud unavailable: running on local main model"
            )
            classification_source = "eco_mode_local_main"

    # ── Apply mode-specific toolbox augmentation ─────────────────────────
    toolbox = augment_toolbox_for_scenario(toolbox, state.get("scenario_id"), user_text)

    # ── Apply learning mode (study) ──────────────────────────────────────
    gate_fields = _memory_gate_fields(
        state,
        user_text,
        decision,
        parsed_needs=parsed_needs,
        parsed_scenario=parsed_scenario,
    )
    gate_fields, toolbox = apply_learning_mode(state, gate_fields, toolbox)

    # ── Budget estimation ────────────────────────────────────────────────
    budget = estimate_token_budget(user_text, route)

    # ── Build metadata ───────────────────────────────────────────────────
    metadata = _build_router_metadata(
        route,
        confidence=confidence,
        reasoning=classification_source,
        classification_source=classification_source,
        cloud_available=cloud_available,
        has_images=has_images,
        task_category=_detect_task_type(user_text),
        estimated_tokens=budget,
        web_on=web_on,
        swap_decision=swap_decision,
        swap_from=swap_from,
        swap_to=swap_to,
    )

    audit_debug(
        "agent.lifecycle",
        "router_final_decision",
        route=route,
        confidence=round(confidence, 3),
        toolbox=toolbox,
        classification_source=classification_source,
    )

    return {
        "route": route,
        "token_budget": budget,
        "selected_toolboxes": toolbox,
        "router_clarification_used": router_clarification_used,
        "skill_matched": skill_matched,
        "router_metadata": metadata,
        **gate_fields,
    }


# ── Chat title generation ────────────────────────────────────────────────

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
    """Best-effort extraction of `{"title":"..."}` from model output."""
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return ""
        parsed = json.loads(match.group(0))
        title = str(parsed.get("title", "")).strip()
        return title
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return ""


async def generate_chat_title_router_llm(
    user_text: str,
    file_names: list[str] | None = None,
) -> str:
    """Generate a chat title using the router's small LLM.

    Falls back to a truncated excerpt of the user message when the LLM is unavailable.
    """
    user_text = str(user_text or "").strip()
    if not user_text:
        return ""

    file_names = file_names or []
    joined_files = ", ".join([str(n).strip() for n in file_names if n])
    joined_files = joined_files[
        : int(config.get("file_decode.filename_join_max_chars", 400))
    ]

    try:
        main_llm = await get_main_llm()

        router_llm = main_llm.bind(
            temperature=float(config.get("chat_title.temperature", 0.2)),
            max_tokens=int(config.get("chat_title.max_tokens")),
        )
        response = await router_llm.ainvoke(
            [
                HumanMessage(
                    content=CHAT_TITLE_PROMPT.format(
                        user_input=user_text[
                            : int(
                                config.get("file_decode.user_text_preview_chars", 1000)
                            )
                        ],
                        file_names=joined_files,
                    )
                )
            ]
        )

        title = _parse_title_json(getattr(response, "content", "") or "")
        title = re.sub(r"\s+", " ", title).strip()
        if title:
            return title[:60]
    except Exception:
        logger.warning("[chat_title] LLM unavailable, using text fallback")

    fallback = user_text.split("\n")[0].strip()
    fallback = re.sub(
        r"^(hi|hey|hello|ok|okay|yes|no|thanks|please)[,.\s]*",
        "",
        fallback,
        flags=re.IGNORECASE,
    ).strip()
    if not fallback:
        from datetime import datetime

        return f"Chat \u2014 {datetime.now().strftime('%b %d, %I:%M %p')}"
    fallback = re.sub(r"\s+", " ", fallback).strip()
    return fallback[:60]
