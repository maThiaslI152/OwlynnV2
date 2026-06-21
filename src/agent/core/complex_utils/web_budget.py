"""Per-turn web tool budgets keyed by router task category."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from langchain_core.messages import ToolMessage

from src.config.config_loader import config

WEB_TOOL_NAMES = frozenset({"web_search", "fetch_webpage", "deep_research"})

_FALLBACK_BUDGETS: dict[str, dict[str, int]] = {
    "default": {"web_search": 2, "fetch_webpage": 3, "deep_research": 1},
    "web_search": {"web_search": 2, "fetch_webpage": 4, "deep_research": 1},
    "data_viz": {"web_search": 0, "fetch_webpage": 0, "deep_research": 0},
    "tool_followup": {"web_search": 0, "fetch_webpage": 0, "deep_research": 0},
    "file_operations": {"web_search": 0, "fetch_webpage": 1, "deep_research": 0},
    "simple_conversation": {"web_search": 1, "fetch_webpage": 1, "deep_research": 0},
}


@dataclass
class WebBudgetStatus:
    """Resolved web-tool allowance for the current user turn."""

    task_category: str
    usage: dict[str, int]
    limits: dict[str, int]
    tool_round: int
    max_tool_rounds: int
    force_synthesis: bool
    blocked_tools: set[str] = field(default_factory=set)


def resolve_task_category(state: dict) -> str:
    meta = state.get("router_metadata") or {}
    return (
        meta.get("task_category")
        or (meta.get("features") or {}).get("task_category")
        or "default"
    )


def count_web_tool_usage(messages: list) -> Counter[str]:
    usage: Counter[str] = Counter()
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        name = getattr(msg, "name", "") or ""
        if name in WEB_TOOL_NAMES:
            usage[name] += 1
    return usage


def get_web_tool_limits(task_category: str) -> dict[str, int]:
    configured = config.get("complex.web_tool_budgets") or {}
    if task_category in configured:
        return {str(k): int(v) for k, v in configured[task_category].items()}
    if task_category in _FALLBACK_BUDGETS:
        return dict(_FALLBACK_BUDGETS[task_category])
    return dict(_FALLBACK_BUDGETS["default"])


def evaluate_web_budget(
    turn_messages: list,
    *,
    task_category: str,
    tool_round: int,
    max_tool_rounds: int,
) -> WebBudgetStatus:
    """Return usage, per-tool caps, and whether to force a synthesis-only hop."""
    usage = count_web_tool_usage(turn_messages)
    limits = get_web_tool_limits(task_category)
    blocked = {
        tool for tool in WEB_TOOL_NAMES if usage.get(tool, 0) >= limits.get(tool, 0)
    }

    any_web_allowed = any(limits.get(tool, 0) > 0 for tool in WEB_TOOL_NAMES)
    all_allowed_exhausted = any_web_allowed and blocked >= {
        tool for tool in WEB_TOOL_NAMES if limits.get(tool, 0) > 0
    }
    round_exhausted = tool_round >= max_tool_rounds and any(usage.values())

    # Zero web limits (e.g. data_viz) block web tools but must not force prose-only
    # synthesis — non-web tools such as notebook_run still apply.
    force_synthesis = all_allowed_exhausted or round_exhausted

    return WebBudgetStatus(
        task_category=task_category,
        usage=dict(usage),
        limits=limits,
        tool_round=tool_round,
        max_tool_rounds=max_tool_rounds,
        force_synthesis=force_synthesis,
        blocked_tools=blocked,
    )


def filter_tools_for_web_budget(tools: list, status: WebBudgetStatus) -> list | None:
    """Drop web tools that hit per-tool caps; None when no tools remain."""
    if status.force_synthesis:
        filtered = [t for t in tools if getattr(t, "name", "") not in WEB_TOOL_NAMES]
        return filtered or None

    if not status.blocked_tools:
        return tools

    filtered = [t for t in tools if getattr(t, "name", "") not in status.blocked_tools]
    return filtered or None
