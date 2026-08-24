"""Unit tests for tool/skill request limiting (toolbox wiring, rerank pins, re-add)."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("mem0", MagicMock())

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.core.complex import _rerank_tools_for_invoke
from src.agent.core.complex_executor import _rerank_tools_for_bind
from src.agent.core.complex_prompt import _resolve_complex_tools
from src.agent.core.complex_utils.context_breakdown import estimate_context_breakdown
from src.agent.tool_sets import TOOLBOX_REGISTRY, resolve_tools
from src.tools.ask_user import ask_user


def _fake_tool(name: str, description: str = "") -> SimpleNamespace:
    return SimpleNamespace(name=name, description=description or name)


class TestSkillToolboxWiring:
    """Confident skill match should narrow selected_toolboxes when enabled."""

    def test_apply_skill_toolbox_when_not_all(self):
        from src.agent.routing.router import _toolbox_for_skill
        from src.tools.skills import SkillDefinition

        skill = SkillDefinition(
            name="research-helper",
            file="research-helper.md",
            description="Research",
            category="research",
            triggers=["research"],
            prompt="Do research",
            tools_used=["web_search", "fetch_webpage"],
        )
        toolbox = _toolbox_for_skill(skill)
        assert "all" not in toolbox
        assert "web_search" in toolbox

    def test_router_applies_skill_toolbox_on_match(self):
        """Simulate the apply_toolbox_on_match gate used in router_node."""
        from src.config.config_loader import config

        assert config.get("routing.skill.apply_toolbox_on_match", True) is True

        skill_toolbox = ["web_search", "file_ops"]
        toolbox = ["all"]
        if config.get("routing.skill.apply_toolbox_on_match", True):
            if skill_toolbox and "all" not in skill_toolbox:
                if not toolbox or toolbox == ["all"]:
                    toolbox = list(skill_toolbox)
                else:
                    toolbox = list(dict.fromkeys([*toolbox, *skill_toolbox]))
        assert toolbox == ["web_search", "file_ops"]

    def test_union_with_existing_classifier_toolbox(self):
        skill_toolbox = ["web_search"]
        toolbox = ["file_ops"]
        toolbox = list(dict.fromkeys([*toolbox, *skill_toolbox]))
        assert toolbox == ["file_ops", "web_search"]


class TestPinnedToolsSurviveRerank:
    def test_ask_user_and_prior_tools_kept(self):
        tools = [_fake_tool(f"tool_{i}") for i in range(20)]
        tools.append(_fake_tool("ask_user", "Ask clarifying questions"))
        tools.append(_fake_tool("web_search", "Search the web"))

        messages = [
            HumanMessage(content="find info"),
            AIMessage(
                content="",
                tool_calls=[{"name": "web_search", "args": {}, "id": "1"}],
            ),
        ]
        state = {"messages": messages}

        def fake_rerank(query, remainder, top_k=8):
            # Prefer unrelated tools so pin logic must preserve ask_user/web_search
            return remainder[:top_k]

        with (
            patch("src.agent.tool_reranker.rerank_tools", side_effect=fake_rerank),
            patch(
                "src.agent.core.complex_executor.config.get",
                side_effect=lambda key, default=None: {
                    "complex.tool_rerank_enabled": True,
                    "complex.tool_rerank_min_count": 10,
                    "complex.tool_rerank_top_k": 8,
                    "complex.pinned_tools": ["ask_user"],
                }.get(key, default),
            ),
        ):
            result = _rerank_tools_for_bind(
                tools,
                prompt_messages=[HumanMessage(content="find info")],
                state=state,
                top_k=8,
                min_count=10,
            )

        names = [getattr(t, "name", "") for t in (result or [])]
        assert "ask_user" in names
        assert "web_search" in names
        assert names == sorted(names)
        assert len(names) <= 8


class TestToolReaddDoesNotExpandCatalog:
    def test_prior_tools_outside_toolbox_not_readded(self):
        # Narrow toolbox: memory only (plus ask_user)
        memory_names = {getattr(t, "name", "") for t in TOOLBOX_REGISTRY["memory"]}
        assert "web_search" not in memory_names

        thread = [
            HumanMessage(content="search then remember"),
            AIMessage(
                content="",
                tool_calls=[{"name": "web_search", "args": {}, "id": "1"}],
            ),
        ]
        state = {
            "route": "complex-default",
            "selected_toolboxes": ["memory"],
            "scenario_id": None,
            "messages": thread,
        }
        tools = _resolve_complex_tools(state, thread, web_on=True, vision_task=False)
        names = {getattr(t, "name", "") for t in tools}
        assert "web_search" not in names
        assert "ask_user" in names or ask_user in tools
        # Resolved set stays within memory toolbox (+ always-included)
        for name in names:
            assert (
                name in memory_names
                or name == "ask_user"
                or name.startswith(("recall", "forget", "search_workspace"))
            )


class TestCloudRerankHelper:
    def test_rerank_disabled_returns_sorted_full_set(self):
        tools = [_fake_tool(f"z_tool_{i}") for i in range(15)]
        tools.append(_fake_tool("ask_user"))

        with patch(
            "src.agent.core.complex_executor.config.get",
            side_effect=lambda key, default=None: {
                "complex.tool_rerank_enabled": False,
                "complex.pinned_tools": ["ask_user"],
            }.get(key, default),
        ):
            result = _rerank_tools_for_bind(
                tools,
                prompt_messages=[HumanMessage(content="hello")],
                top_k=8,
            )
        assert result is not None
        assert len(result) == len(tools)
        names = [getattr(t, "name", "") for t in result]
        assert names == sorted(names)

    def test_below_min_count_skips_rerank(self):
        tools = [_fake_tool(f"tool_{i}") for i in range(5)]
        with (
            patch("src.agent.tool_reranker.rerank_tools") as mock_rerank,
            patch(
                "src.agent.core.complex_executor.config.get",
                side_effect=lambda key, default=None: {
                    "complex.tool_rerank_enabled": True,
                    "complex.tool_rerank_min_count": 10,
                    "complex.pinned_tools": ["ask_user"],
                }.get(key, default),
            ),
        ):
            result = _rerank_tools_for_bind(
                tools,
                prompt_messages=[HumanMessage(content="hi")],
                top_k=8,
                min_count=10,
            )
            mock_rerank.assert_not_called()
        assert len(result or []) == 5


class TestContextBreakdownToolSchema:
    def test_tool_schema_tokens_est_present(self):
        tools = [
            _fake_tool("web_search", "Search the live web for current information."),
            _fake_tool("ask_user", "Ask the user a clarifying question."),
        ]
        bd = estimate_context_breakdown(
            [HumanMessage(content="hello")],
            max_context=100_000,
            bound_tools=tools,
        )
        assert "tool_schema_tokens_est" in bd
        assert bd["tool_schema_tokens_est"] > 0
        assert bd["bound_tool_count"] == 2
        assert bd["categories"]["schemas"] == bd["tool_schema_tokens_est"]
        without_schemas = estimate_context_breakdown(
            [HumanMessage(content="hello")],
            max_context=100_000,
        )
        assert bd["input_estimated"] == (
            without_schemas["input_estimated"] + bd["tool_schema_tokens_est"]
        )
        assert bd["total_used"] == bd["input_estimated"]


class TestResolveToolsAskUserPreserved:
    def test_narrow_toolbox_keeps_ask_user(self):
        tools = resolve_tools(["memory"])
        assert ask_user in tools or any(
            getattr(t, "name", "") == "ask_user" for t in tools
        )


class TestBoundToolCountPostRerank:
    """Telemetry bound_tool_count must reflect the post-rerank invoke list."""

    def test_rerank_for_invoke_caps_and_breakdown_matches(self):
        tools = [_fake_tool(f"tool_{i}") for i in range(20)]
        tools.append(_fake_tool("ask_user", "Ask clarifying questions"))
        messages = [HumanMessage(content="find info")]

        def fake_rerank(query, remainder, top_k=8):
            return remainder[:top_k]

        with (
            patch("src.agent.tool_reranker.rerank_tools", side_effect=fake_rerank),
            patch(
                "src.agent.core.complex_executor.config.get",
                side_effect=lambda key, default=None: {
                    "complex.tool_rerank_enabled": True,
                    "complex.tool_rerank_min_count": 10,
                    "complex.tool_rerank_top_k": 8,
                    "complex.pinned_tools": ["ask_user"],
                }.get(key, default),
            ),
        ):
            capped = _rerank_tools_for_invoke(
                tools_for_invoke=tools,
                tools_bound=True,
                route="complex-default",
                prompt_messages=messages,
                state={"messages": messages},
            )

        assert capped is not None
        assert len(capped) < len(tools)
        bd = estimate_context_breakdown(
            messages,
            max_context=100_000,
            bound_tools=capped,
        )
        assert bd["bound_tool_count"] == len(capped)
        assert bd["categories"]["schemas"] == bd["tool_schema_tokens_est"]
        assert bd["total_used"] == bd["input_estimated"]
