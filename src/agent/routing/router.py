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
from src.agent.llm import get_small_llm
from src.config.config_loader import config
from src.memory.user_profile import get_profile
from src.tools.skills import SkillMatcher, MatchResult, _default_loader as _skill_loader

from src.config.audit_log import audit_info, audit_debug, audit_warn
from src.config.log_middleware import log_node

# Re-export from decomposed modules for backward compatibility
from src.agent.routing.resolver import (
    estimate_token_budget,
    _check_cloud_available,
    _preferred_complex_route,
    _resolve_complex_route,
    _resolve_memory_gate,
    _resolve_scenario_id,
    _memory_gate_fields,
    _build_router_metadata,
    _knowledge_cache_likely_answers,
    _check_travel_mode,
)
from src.agent.routing.deterministic import (
    check_deterministic_bypasses,
    _last_user_text,
    _has_image_content,
    _needs_frontier_quality,
    _user_wants_file_work,
    _user_wants_data_viz,
    _user_wants_screen_assist,
    _is_simple_informational_query,
    _is_followup_continuation,
)
from src.agent.routing.modes import (
    augment_toolbox_for_scenario,
    apply_learning_mode,
    handle_pentest_mode,
)

import json
import re
import logging

logger = logging.getLogger(__name__)


# ── Router prompt with toolbox classification ────────────────────────────
ROUTER_PROMPT = """Classify in one shot. No reasoning, no preamble, no markdown.

simple = casual chatter, acknowledgements (ok, got it, cool), short conversational praises, greetings/thanks ONLY. If the user asks ANY factual question, trivia, or asks about a topic/event that might require research or internet access, MUST classify as complex.
complex = code/math/writing, multi-step work, OR needs live web/news/weather/prices. ANY mention of code, python, bugs, review, OR factual questions MUST be classified as complex.
browser_local = user explicitly asks to interact with the browser extension (clicking, typing, reading DOM). The local model will drive the extension natively.

Toolbox categories (pick one or more, or "all" if unsure):
- web_search: web lookup, live data, current information, news, weather, prices. IMPORTANT: If the requested factual information is fully answered by the provided Knowledge Cache, DO NOT include web_search.
- file_ops: read/write/edit/list/delete workspace files
- data_viz: create documents/spreadsheets/presentations/PDFs, run code, data analysis, charts
- productivity: task management, todos, skills, workflow templates
- memory: recall past conversations, user preferences, stored facts
- screen_assist: local tmux terminal, macOS UI context, browser tab, remote Kali SSH tmux (read-only)
- mcp: external MCP servers (e.g. pentest SSH/tmux on Kali) — only when configured in mcp_config.json
- all: when unsure or multiple categories needed

Reply with exactly one JSON object (nothing else). OUTPUT ONLY RAW VALID JSON. NO MARKDOWN. NO CODE BLOCKS. NO PREAMBLE.
The execution_plan should briefly break down the steps required to solve the user's request (e.g. 1. search for X, 2. write to file Y). If simple routing, set execution_plan to "none" and needs_memory_retrieval to false. If the Knowledge Cache fully answers the question, set needs_memory_retrieval to false and omit web_search from toolbox:
{{"routing":"simple"|"complex"|"browser_local","confidence":0.0-1.0,"toolbox":["name1","name2"],"execution_plan":"Step 1... Step 2..." | "none","needs_memory_retrieval":true|false,"scenario_id":"pentest"|"research"|"study"|null}}

Knowledge Cache:
{knowledge_context}

Message: {user_input}

JSON:"""


def parse_routing(
    content: str,
) -> tuple[str, float, list[str], str | None, bool | None, str | None]:
    """Extract routing decision, confidence, toolbox, plan, memory gate, and scenario."""
    # Strip thinking blocks — handles both Gemma (<think>) and Qwen (<thinking>) formats.
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    content = re.sub(r"<thinking>.*?</thinking>", "", content, flags=re.DOTALL).strip()
    content = re.sub(
        r"Thinking Process:.*?(?=\n\n[^\d]|\Z)", "", content, flags=re.DOTALL
    ).strip()
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            decision = parsed.get("routing", "complex").lower().strip()
            if decision not in ("simple", "complex", "browser_local"):
                decision = "complex"
            confidence = float(parsed.get("confidence", 0.5))
            toolbox = parsed.get("toolbox", "all")
            if isinstance(toolbox, str):
                toolbox = [toolbox]
            execution_plan = parsed.get("execution_plan")
            needs_memory = parsed.get("needs_memory_retrieval")
            if needs_memory is not None:
                needs_memory = bool(needs_memory)
            scenario_id = parsed.get("scenario_id")
            if scenario_id is not None and str(scenario_id).lower() in {
                "null",
                "none",
                "",
            }:
                scenario_id = None
            elif scenario_id is not None:
                scenario_id = str(scenario_id).strip().lower() or None
            return (
                decision,
                confidence,
                toolbox,
                execution_plan,
                needs_memory,
                scenario_id,
            )
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        pass
    return "complex", 0.5, ["all"], None, None, None


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

    # ── Stage 1: Ask Small LLM for simple/complex + toolbox ──────────────
    small_llm = await get_small_llm()
    decision = "complex"
    confidence = 0.5
    toolbox = ["all"]
    parsed_needs: bool | None = None
    parsed_scenario: str | None = None
    execution_plan: str | None = None

    try:
        router_llm = small_llm.bind(
            temperature=float(config.get("router_llm.temperature", 0.05)),
            max_tokens=int(config.get("router_llm.max_tokens")),
        )
        response = await router_llm.ainvoke(
            [
                HumanMessage(
                    content=ROUTER_PROMPT.format(
                        knowledge_context=state.get("knowledge_context") or "None",
                        user_input=json.dumps(
                            user_text[: int(config.get("routing.max_input_chars", 500))]
                        ),
                    )
                )
            ]
        )
        decision, confidence, toolbox, execution_plan, parsed_needs, parsed_scenario = (
            parse_routing(str(response.content))
        )
        classification_source = "llm_classifier"

        # ── Override: Enforce complex for factual questions ──
        if decision == "simple":
            _question_words = re.compile(
                r"\b(what|who|where|when|why|how much|how many|is there|are there|can you|could you)\b",
                re.IGNORECASE,
            )
            if "?" in user_text or _question_words.search(user_text):
                # Exempt casual small talk / conversational inquiries
                if not re.search(
                    r"\b(how are you|how do you do|what's up|whats up|what do you think|how are you doing|are you sure|make sense\?|makes sense\?|got it\?)\b",
                    user_text,
                    re.IGNORECASE,
                ):
                    logger.info(
                        "[router] Overriding 'simple' to 'complex' due to question detection"
                    )
                    decision = "complex"
                    confidence = 0.9  # Confident override
                    classification_source = "question_heuristic_override"
                    if "web_search" not in toolbox and "all" not in toolbox:
                        toolbox.append("web_search")
    except Exception as e:
        logger.error(f"[router] Error during routing: {e}")
        audit_warn("agent.lifecycle", "router_llm_error", error=str(e)[:120])
        decision, confidence, toolbox = "complex", 0.5, ["all"]
        classification_source = "llm_classifier"

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
    else:
        route, toolbox = _resolve_complex_route(
            user_text, state, toolbox, cloud_available=cloud_available
        )

    # ── Eco-Mode / Travel Mode Routing Override ──────────────────────────
    if route != "simple" and route != "browser_local" and _check_travel_mode():
        if cloud_available:
            route = "complex-cloud"
            logger.info("[router] Travel Mode active: forced route to complex-cloud")
            classification_source = "travel_mode_force_cloud"
        else:
            route = "complex-local"
            logger.info(
                "[router] Travel Mode active but cloud missing: fallback to complex-local"
            )
            classification_source = "travel_mode_cloud_unavailable"

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
        small_llm = await get_small_llm()

        router_llm = small_llm.bind(
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
