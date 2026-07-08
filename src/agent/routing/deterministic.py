"""Deterministic routing bypasses — keyword/heuristic fast paths.

These bypasses run before the LLM classifier and return a routing decision
immediately when a pattern matches. Extracted from router.py during the
router decomposition refactor.

Each bypass function returns ``dict | None`` — ``None`` means "no match,
fall through to next bypass or LLM classifier".
"""

from __future__ import annotations

import logging
import re

from src.agent.core.state import AgentState
from src.config.audit_log import audit_info

logger = logging.getLogger(__name__)

# ── Vision toolbox (workspace + memory only) ─────────────────────────────
_VISION_TOOLBOX = ["file_ops", "memory"]

# ── Frontier-quality hints ───────────────────────────────────────────────
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

# ── Web / live-data hints ────────────────────────────────────────────────
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

_EXPLICIT_WEB_REQUESTS = (
    "search the web",
    "search for",
    "look up",
    "google ",
)

_TIME_SENSITIVE_WEB_HINTS = (
    "weather",
    "forecast",
    "temperature in",
    "humidity in",
    "stock price",
    "crypto price",
    "news ",
    "breaking",
    "current price",
    "price in ",
    "today's ",
    "right now",
    "live score",
)

# ── File / screen / data-viz hints ───────────────────────────────────────
_FILE_WORK_HINTS = (
    "workspace",
    "uploaded",
    "attached file",
    "[attached",
    "read_workspace",
    "local file",
    "in my project",
    "in the repo",
)

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

_DATA_VIZ_HINTS = (
    "chart",
    "graph",
    "plot",
    "visualiz",
    "diagram",
    "spreadsheet",
    "create a document",
    "create a report",
    "generate a report",
    "export to pdf",
    "export to xlsx",
    "make a ppt",
    "build a dashboard",
)

_SIMPLE_INFO_RE = re.compile(
    r"\b("
    r"what is|what are|what's|who is|who are|where is|where are|"
    r"when was|when did|how many|how much|capital of|population of|"
    r"list of|name of"
    r")\b",
    re.IGNORECASE,
)

_CASUAL_HINTS = {
    "hi",
    "hello",
    "hey",
    "howdy",
    "sup",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
    "thanks",
    "thank you",
    "cheers",
    "ok",
    "okay",
    "cool",
    "nice",
    "got it",
    "understood",
    "sure",
    "right",
    "yep",
    "nope",
    "lol",
    "haha",
    "wow",
    "awesome",
    "great",
    "perfect",
    "excellent",
    "amazing",
    "wonderful",
    "brilliant",
    "lol",
    "lmao",
    "rofl",
    "heh",
    "hmm",
    "huh",
    "oh",
    "ah",
    "ugh",
    "oops",
    "whoops",
    "yay",
    "woohoo",
    "congrats",
    "congratulations",
    "good job",
    "well done",
    "nice work",
    "keep it up",
    "you're welcome",
    "no problem",
    "my pleasure",
    "glad to help",
    "glad i could help",
    "glad i helped",
    "glad you liked it",
    "glad you enjoyed it",
    "glad it helped",
    "glad it worked",
    "glad it made sense",
    "glad you think so",
    "glad you agree",
    "glad you approve",
    "glad you're happy",
    "glad you're satisfied",
    "glad you're pleased",
    "glad you're impressed",
    "glad you're amazed",
    "glad you're wowed",
    "glad you're blown away",
    "glad you're mind-blown",
    "glad you're speechless",
    "glad you're in awe",
    "glad you're thrilled",
    "glad you're excited",
    "glad you're delighted",
    "glad you're overjoyed",
    "glad you're ecstatic",
    "glad you're elated",
    "glad you're jubilant",
    "glad you're euphoric",
    "glad you're on cloud nine",
    "glad you're on top of the world",
    "glad you're over the moon",
    "glad you're walking on air",
    "glad you're floating on air",
    "glad you're flying high",
    "glad you're riding high",
    "glad you're feeling great",
    "glad you're feeling good",
    "glad you're feeling awesome",
    "glad you're feeling amazing",
    "glad you're feeling wonderful",
    "glad you're feeling excellent",
    "glad you're feeling fantastic",
    "glad you're feeling brilliant",
    "glad you're feeling perfect",
    "glad you're feeling incredible",
    "glad you're feeling phenomenal",
    "glad you're feeling extraordinary",
    "glad you're feeling remarkable",
    "glad you're feeling outstanding",
    "glad you're feeling exceptional",
    "glad you're feeling magnificent",
    "glad you're feeling marvelous",
    "glad you're feeling splendid",
    "glad you're feeling fabulous",
    "glad you're feeling terrific",
    "glad you're feeling fantastic",
    "glad you're feeling wonderful",
    "glad you're feeling excellent",
    "glad you're feeling amazing",
    "glad you're feeling awesome",
    "glad you're feeling great",
    "glad you're feeling good",
}

_PERSONAL_INFO_PATTERNS = re.compile(
    r"\b("
    r"my name is|i'm called|i go by|call me|"
    r"i live in|i'm from|i'm based in|i work at|i work for|"
    r"i'm a |i am a |my job|i'm currently|"
    r"my email|my phone|my address"
    r")\b",
    re.IGNORECASE,
)

_CONVERSATION_RECALL_PATTERNS = re.compile(
    r"\b("
    r"what did (?:we|i|you) (?:talk|discuss|say|mention|cover) about|"
    r"(?:do you|can you) remember|"
    r"earlier (?:you|we) (?:said|mentioned|talked|discussed)|"
    r"last (?:time|session|conversation|chat)|"
    r"what (?:was|were) (?:the|our) (?:previous|last|prior)|"
    r"repeat (?:what|that)|"
    r"go back to (?:what|the)|"
    r"you (?:just|recently) (?:said|mentioned)"
    r")\b",
    re.IGNORECASE,
)

_CREATIVE_WRITING_HINTS = (
    "write a poem",
    "write a song",
    "write a story",
    "write a script",
    "write a dialogue",
    "write a monologue",
    "write a haiku",
    "write a limerick",
    "write a sonnet",
    "write a haiku",
    "creative writing",
    "fiction",
    "novel",
    "short story",
    "flash fiction",
    "micro fiction",
    "poetry",
    "lyrics",
    "screenplay",
    "dialogue",
    "monologue",
    "narrative",
)


# ── Helpers ──────────────────────────────────────────────────────────────


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


def _needs_frontier_quality(text: str) -> bool:
    """Check if the task needs frontier-class model quality."""
    lower = text.lower()
    return any(hint in lower for hint in _FRONTIER_HINTS)


def _user_wants_file_work(text: str) -> bool:
    lower = text.lower()
    return any(h in lower for h in _FILE_WORK_HINTS)


def _user_wants_data_viz(text: str) -> bool:
    lower = text.lower()
    return any(h in lower for h in _DATA_VIZ_HINTS)


def _user_wants_screen_assist(text: str) -> bool:
    lower = text.lower()
    return any(h in lower for h in _SCREEN_ASSIST_HINTS)


def _is_casual_chatter(text: str) -> bool:
    """Detect casual greetings, thanks, acknowledgements."""
    lower = text.lower().strip()
    return any(lower.startswith(hint) for hint in _CASUAL_HINTS)


def _is_personal_info_disclosure(text: str) -> bool:
    """Detect user sharing personal info (name, location, job)."""
    return bool(_PERSONAL_INFO_PATTERNS.search(text))


def _is_conversation_recall(text: str) -> bool:
    """Detect user asking about previous conversation content."""
    return bool(_CONVERSATION_RECALL_PATTERNS.search(text))


def _is_creative_writing(text: str) -> bool:
    """Detect creative writing requests."""
    lower = text.lower()
    return any(hint in lower for hint in _CREATIVE_WRITING_HINTS)


def _is_simple_informational_query(text: str) -> bool:
    """Factual Q&A that should not trigger toolbox picker HITL."""
    if _user_wants_file_work(text) or _user_wants_data_viz(text):
        return False
    return bool(_SIMPLE_INFO_RE.search(text))


def _has_tool_history(state: AgentState) -> bool:
    """Check if the conversation has recent tool usage (stay complex)."""
    messages = state.get("messages") or []
    for msg in messages[-6:]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            return True
    return False


def _has_browser_context(state: AgentState) -> bool:
    """Check if browser extension context is available."""
    return bool(state.get("browser_page_context"))


# ── Bypass result type ───────────────────────────────────────────────────


from typing import TypedDict


class BypassResult(TypedDict, total=False):
    route: str
    token_budget: int
    selected_toolboxes: list[str]
    router_clarification_used: bool
    skill_matched: None
    router_metadata: dict
    needs_memory_retrieval: bool
    scenario_id: str | None


# ── Main bypass checker ──────────────────────────────────────────────────


async def check_deterministic_bypasses(
    state: AgentState,
    *,
    cloud_available: bool,
    has_images: bool,
    web_on: bool,
) -> BypassResult | None:
    """Run all deterministic bypasses in priority order.

    Returns a complete router result dict if a bypass matches, or ``None``
    to fall through to the LLM classifier.
    """
    from src.agent.routing.resolver import (
        _preferred_complex_route,
        _resolve_complex_route,
        estimate_token_budget,
        _build_router_metadata,
    )

    user_text = _last_user_text(state)
    user_lower = user_text.lower()

    # ── 1. Image attachments ─────────────────────────────────────────────
    if has_images:
        from src.agent.core.complex_utils.lm_studio_vision import (
            ensure_vision_vlm_loaded,
        )

        vision_ready = False
        try:
            vision_ready = await ensure_vision_vlm_loaded()
        except Exception as e:
            logger.warning("[router] Vision VLM load preflight failed: %s", e)

        if not vision_ready:
            logger.warning(
                "[router] Vision VLM is not ready. Falling back to complex-cloud."
            )
            route = "complex-cloud"
            toolbox = list(_VISION_TOOLBOX)
            task_category = "vision_fallback"
            reasoning = "image_attachment_vision_proxy_unavailable"
        else:
            # Cloud available → use cloud vision proxy; else local VLM
            route = "complex-cloud" if cloud_available else "complex-default"
            toolbox = list(_VISION_TOOLBOX)
            task_category = "vision_cloud" if route == "complex-cloud" else "vision"
            reasoning = (
                "image_attachment_cloud_proxy"
                if route == "complex-cloud"
                else "image_attachment"
            )

        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.95,
            reasoning=reasoning,
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=True,
            task_category=task_category,
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.95,
            source=reasoning,
            task_category=task_category,
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 2. Casual chatter / greetings ────────────────────────────────────
    if _is_casual_chatter(user_text) and len(user_text) < 80:
        route = "simple"
        budget = 256
        metadata = _build_router_metadata(
            route,
            confidence=0.98,
            reasoning="casual_chatter_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="chatter",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.98,
            source="casual_chatter_bypass",
            task_category="chatter",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": ["all"],
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": False,
            "scenario_id": None,
        }

    # ── 3. Personal info disclosure ──────────────────────────────────────
    if _is_personal_info_disclosure(user_text):
        route, toolbox = _resolve_complex_route(
            user_text, state, ["memory"], cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.95,
            reasoning="personal_info_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="personal_info",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.95,
            source="personal_info_bypass",
            task_category="personal_info",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 4. Conversation recall ───────────────────────────────────────────
    if _is_conversation_recall(user_text):
        route, toolbox = _resolve_complex_route(
            user_text, state, ["memory"], cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.95,
            reasoning="conversation_recall_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="recall",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.95,
            source="conversation_recall_bypass",
            task_category="recall",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 5. Browser extension context ─────────────────────────────────────
    if _has_browser_context(state):
        route = "browser_local"
        toolbox = ["screen_assist"]
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=1.0,
            reasoning="browser_context_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="browser",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=1.0,
            source="browser_context_bypass",
            task_category="browser",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": False,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 6. Sticky browser_local ──────────────────────────────────────────
    if state.get("route") == "browser_local":
        route = "browser_local"
        toolbox = ["screen_assist"]
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.9,
            reasoning="sticky_browser_local",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="browser",
            estimated_tokens=budget,
            web_on=web_on,
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": False,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 7. Tool history in conversation ──────────────────────────────────
    if _has_tool_history(state):
        # Check for data viz or file work intent in follow-up
        if _user_wants_data_viz(user_text):
            toolbox_seed = ["data_viz"]
            task_category = "data_viz"
        elif _user_wants_file_work(user_text):
            toolbox_seed = ["file_ops"]
            task_category = "file_ops"
        else:
            toolbox_seed = ["all"]
            task_category = "continuation"

        route, toolbox = _resolve_complex_route(
            user_text, state, toolbox_seed, cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.9,
            reasoning="tool_history_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category=task_category,
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.9,
            source="tool_history_bypass",
            task_category=task_category,
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 8. Web / live-data intent ────────────────────────────────────────
    if web_on and any(hint in user_lower for hint in _WEBISH_HINTS):
        # Check if knowledge cache covers the query — skip web_search if so
        # BUT: time-sensitive queries (weather, prices) always need web_search
        from src.agent.routing.resolver import _knowledge_cache_likely_answers

        knowledge_context = state.get("knowledge_context")
        is_time_sensitive = any(
            hint in user_lower for hint in _TIME_SENSITIVE_WEB_HINTS
        )
        if (
            knowledge_context
            and not is_time_sensitive
            and _knowledge_cache_likely_answers(user_text, knowledge_context)
        ):
            # Knowledge cache likely answers — skip web_search
            route, toolbox = _resolve_complex_route(
                user_text, state, ["all"], cloud_available=cloud_available
            )
            budget = estimate_token_budget(user_text, route)
            metadata = _build_router_metadata(
                route,
                confidence=0.9,
                reasoning="knowledge_cache_sufficient",
                classification_source="deterministic",
                cloud_available=cloud_available,
                has_images=has_images,
                task_category="analysis",
                estimated_tokens=budget,
                web_on=web_on,
            )
            audit_info(
                "agent.lifecycle",
                "router_decision",
                route=route,
                confidence=0.9,
                source="knowledge_cache_sufficient",
                task_category="analysis",
            )
            return {
                "route": route,
                "token_budget": budget,
                "selected_toolboxes": toolbox,
                "router_clarification_used": False,
                "skill_matched": None,
                "router_metadata": metadata,
                "needs_memory_retrieval": True,
                "scenario_id": state.get("scenario_id"),
            }

        route, toolbox = _resolve_complex_route(
            user_text, state, ["web_search"], cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.9,
            reasoning="web_intent_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="web_search",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.9,
            source="web_intent_bypass",
            task_category="web_search",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 9. Workspace / attachment context ────────────────────────────────
    if _user_wants_file_work(user_text):
        route, toolbox = _resolve_complex_route(
            user_text, state, ["file_ops"], cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.9,
            reasoning="file_work_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="file_ops",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.9,
            source="file_work_bypass",
            task_category="file_ops",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 10. Code review patterns ─────────────────────────────────────────
    _code_review_hints = (
        "review my code",
        "code review",
        "check my code",
        "look at this code",
        "review this pr",
        "review this pull request",
        "review this commit",
        "review this diff",
    )
    if any(hint in user_lower for hint in _code_review_hints):
        route, toolbox = _resolve_complex_route(
            user_text, state, ["file_ops"], cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.9,
            reasoning="code_review_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="code_review",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.9,
            source="code_review_bypass",
            task_category="code_review",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 11. Explain / compare patterns ───────────────────────────────────
    _explain_hints = (
        "explain how",
        "explain the",
        "explain what",
        "what is the difference",
        "compare",
        "contrast",
        "pros and cons",
        "trade off",
        "tradeoff",
        "versus",
        " vs ",
        " vs. ",
    )
    if any(hint in user_lower for hint in _explain_hints):
        route, toolbox = _resolve_complex_route(
            user_text, state, ["all"], cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.9,
            reasoning="explain_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="analysis",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.9,
            source="explain_bypass",
            task_category="analysis",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 12. Creative writing ─────────────────────────────────────────────
    if _is_creative_writing(user_text):
        route, toolbox = _resolve_complex_route(
            user_text, state, ["all"], cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.95,
            reasoning="creative_writing_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="creative_writing",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.95,
            source="creative_writing_bypass",
            task_category="creative_writing",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # ── 13. Screen assist ────────────────────────────────────────────────
    if _user_wants_screen_assist(user_text):
        route, toolbox = _resolve_complex_route(
            user_text, state, ["screen_assist"], cloud_available=cloud_available
        )
        budget = estimate_token_budget(user_text, route)
        metadata = _build_router_metadata(
            route,
            confidence=0.9,
            reasoning="screen_assist_bypass",
            classification_source="deterministic",
            cloud_available=cloud_available,
            has_images=has_images,
            task_category="screen_assist",
            estimated_tokens=budget,
            web_on=web_on,
        )
        audit_info(
            "agent.lifecycle",
            "router_decision",
            route=route,
            confidence=0.9,
            source="screen_assist_bypass",
            task_category="screen_assist",
        )
        return {
            "route": route,
            "token_budget": budget,
            "selected_toolboxes": toolbox,
            "router_clarification_used": False,
            "skill_matched": None,
            "router_metadata": metadata,
            "needs_memory_retrieval": True,
            "scenario_id": state.get("scenario_id"),
        }

    # No deterministic bypass matched — fall through to LLM classifier
    return None
