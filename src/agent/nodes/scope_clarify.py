"""
Scope clarification node — runs after router for underspecified build/create requests.

Uses cheap heuristics first (no LLM), then Small LLM classifier to generate
targeted clarifying questions before ``complex_llm`` commits to code or files.
"""

import json
import logging
from typing import Any

from langgraph.types import interrupt, Command

from src.agent.state import AgentState
from src.agent.hitl.scope_heuristics import needs_clarification
from src.memory.user_profile import get_profile

logger = logging.getLogger(__name__)

from src.config.log_middleware import log_hitl_event, log_node
from src.config.audit_log import audit_info

_CLASSIFIER_PROMPT = """You are helping clarify a user's vague build request by generating targeted questions.

User message: {message}

This request is missing critical details — specifically: {missing_dimensions}

Generate 1-3 multiple-choice questions to fill these gaps. Consider:
- Language/runtime (Python, JavaScript, etc.)
- UI surface (Web GUI, Desktop GUI, CLI, TUI)
- Feature scope (basic, advanced, specific features)
- Platform/target

Return ONLY valid JSON:
{{
  "task_summary": "short summary of what's being built",
  "questions": [
    {{
      "id": "language",
      "question": "Which language/runtime?",
      "choices": [{{"label": "Python"}}, {{"label": "JavaScript/TypeScript"}}, {{"label": "Rust"}}],
      "allows_user_input": true
    }}
  ],
  "pitfalls_if_assumed": ["Assuming wrong framework wastes a full pass."]
}}"""


@log_node("scope_clarify")
async def scope_clarify_node(state: AgentState) -> AgentState | Command:
    """Run proactive scope clarification when a build request is underspecified.

    Skips (returns early) when:
    - Route is ``simple`` (router already decided no tools needed)
    - ``scope_clarification_enabled`` is false in profile
    - ``router_clarification_used`` is true (avoid back-to-back HITL)
    - Heuristic + Small LLM agree no clarification needed
    """
    route = state.get("route") or ""
    if not route.startswith("complex"):
        logger.debug("[scope_clarify] Skipped — route does not require complex toolbox: %s", route)
        return {}

    profile = get_profile()
    if not profile.get("scope_clarification_enabled", True):
        logger.debug("[scope_clarify] Skipped — disabled in profile")
        return {}

    if state.get("router_clarification_used"):
        logger.debug("[scope_clarify] Skipped — router already handled clarification")
        return {}

    messages = list(state.get("messages") or [])
    user_text = ""
    from langchain_core.messages import HumanMessage
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_text = str(msg.content or "")
            break

    if not user_text:
        return {}

    # ── Heuristic gate (fast, no LLM) ─────────────────────────────
    needs, missing = needs_clarification(user_text)
    if not needs:
        logger.debug("[scope_clarify] Heuristic passed — no clarification needed")
        audit_info("agent.hitl", "scope_clarify_skipped", reason="heuristic_passed")
        return {}

    logger.info("[scope_clarify] Heuristic flagged as underspecified: missing=%s", missing)
    audit_info("agent.hitl", "scope_clarify_triggered", missing_dimensions=missing)

    # ── Small LLM: generate questions ──────────────────────────────
    # The heuristic already determined clarification is needed.
    # The Small LLM only generates better questions; it cannot override.
    questions: list[dict] = []
    task_summary = ""
    pitfalls: list[str] = []

    try:
        from src.agent.llm import get_small_llm
        small_llm = await get_small_llm()
    except Exception as e:
        logger.warning("[scope_clarify] Small LLM unavailable: %s", e)
        small_llm = None

    if small_llm is not None:
        prompt = _CLASSIFIER_PROMPT.format(
            message=_truncate(user_text, 2000),
            missing_dimensions=", ".join(missing),
        )
        try:
            response = await small_llm.ainvoke(prompt)
            result = _parse_json(response.content)
            questions = (result.get("questions") or [])[:3]
            task_summary = result.get("task_summary", "")
            pitfalls = result.get("pitfalls_if_assumed", [])
            logger.info("[scope_clarify] Small LLM generated %d questions", len(questions))
        except Exception as e:
            logger.warning("[scope_clarify] Small LLM question generation failed: %s", e)

    # ── Fallback: build generic questions from heuristic ───────────
    if not questions:
        questions = _build_fallback_questions(missing, user_text)
        task_summary = _extract_task_summary(user_text)
        logger.info("[scope_clarify] Using fallback questions: %d", len(questions))

    if not questions:
        # Shouldn't happen, but guard against empty questions
        logger.warning("[scope_clarify] No questions generated, skipping interrupt")
        return {}

    # ── Build interrupt payload ───────────────────────────────────
    from src.agent.hitl.context import build_hitl_context
    ctx = build_hitl_context(state)

    interrupt_payload = {
        "type": "scope_clarification_required",
        "task_summary": task_summary,
        "questions": questions,
        "pitfalls": pitfalls,
        "conversation_snippet": ctx.get("conversation_snippet", ""),
    }

    decision = interrupt(interrupt_payload)

    # ── Resume: parse answers ─────────────────────────────────────
    clarified_scope = _parse_clarification_response(decision, questions)
    log_hitl_event("scope_clarified", decision="answered",
                    dimensions=list(clarified_scope.keys()),
                    question_count=len(questions))
    return {
        "clarified_scope": clarified_scope,
        "router_clarification_used": True,
    }


def _parse_json(content) -> dict:
    content = str(content or "").strip()
    # Extract JSON from possible markdown code fences
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    return json.loads(content)


def _parse_clarification_response(decision: Any, questions: list[dict]) -> dict:
    """Parse the user's response to scope clarification questions."""
    scope: dict[str, Any] = {}

    if isinstance(decision, dict):
        answers = decision.get("answers", decision)
        if isinstance(answers, dict):
            for q in questions:
                qid = q.get("id", "")
                answer = answers.get(qid)
                if answer is None:
                    continue
                if isinstance(answer, dict):
                    scope[qid] = answer
                else:
                    scope[qid] = {"label": str(answer)}
        elif answers is not None:
            scope["_raw"] = str(answers)
    elif isinstance(decision, str) and decision.strip().lower() in ("skip", "use your best judgment"):
        scope["skipped"] = True
    elif isinstance(decision, str):
        scope["_raw"] = decision

    return scope


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _extract_task_summary(text: str) -> str:
    """Extract a short task summary from the user message."""
    text = text.strip().rstrip("?!. ")
    if len(text) > 120:
        text = text[:117] + "..."
    return text


def _build_fallback_questions(missing: list[str], _user_text: str) -> list[dict]:
    """Build generic clarification questions when the Small LLM is unavailable."""
    questions: list[dict] = []

    for dim in missing:
        if dim == "language":
            questions.append({
                "id": "language",
                "question": "Which programming language or runtime should I use?",
                "choices": [
                    {"label": "Python"},
                    {"label": "JavaScript / TypeScript"},
                    {"label": "Rust"},
                    {"label": "No preference — recommend one"},
                ],
                "allows_user_input": True,
            })
        elif dim == "ui_surface":
            questions.append({
                "id": "ui_surface",
                "question": "What kind of interface should this have?",
                "choices": [
                    {"label": "Web GUI (browser)"},
                    {"label": "Desktop GUI"},
                    {"label": "CLI (command line)"},
                    {"label": "TUI (terminal interface)"},
                ],
                "allows_user_input": True,
            })

    return questions[:3]
