"""
Integration tests for the router node's Skill Matcher HITL round-trip.

Covers:
- Test 1: HITL fires when confidence is low and skill match is ambiguous
- Test 2: HITL resume sets correct toolbox from chosen skill
- Test 3: HITL fires when LLM is confident but skill match is ambiguous (Gap 2 fix)
- Test 4: No HITL when LLM is confident and skill is strongly aligned (Gap 2 fix)
"""

import sys
from unittest.mock import MagicMock, AsyncMock, patch

sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import HumanMessage

from src.agent.routing.router import router_node
from src.agent.core.state import AgentState
from src.tools.skills import SkillDefinition, MatchResult


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_skill(
    name: str,
    triggers: list[str],
    description: str = "",
    file: str = "",
    category: str = "general",
    tools_used: list[str] | None = None,
) -> SkillDefinition:
    return SkillDefinition(
        file=file or f"{name.lower().replace(' ', '_')}.md",
        name=name,
        triggers=triggers,
        description=description or f"A skill for {name.lower()}",
        prompt=f"Do the {name} thing with {{context}}",
        category=category,
        tools_used=tools_used or [],
    )


def _make_empty_state() -> dict:
    """Build a minimal AgentState dict with no messages (returns early route)."""
    return {"messages": [], "web_search_enabled": True}


def _make_text_state(text: str) -> dict:
    """Build a minimal AgentState dict with a text message."""
    return {"messages": [HumanMessage(content=text)], "web_search_enabled": True}


def _make_mock_llm(content: str) -> MagicMock:
    """Create a mock Small LLM that returns the given JSON content."""
    mock_llm = MagicMock()
    mock_llm.bind.return_value = mock_llm
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=content))
    return mock_llm


# ═════════════════════════════════════════════════════════════════════════
# Test 1: HITL fires on low confidence + ambiguous skill match
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
@patch("src.agent.routing.router.get_profile")
@patch("src.agent.routing.router.interrupt")
@patch("src.agent.routing.router.SkillMatcher")
@patch("src.agent.routing.router.get_small_llm", new_callable=AsyncMock)
@patch("langgraph.config.get_config")
async def test_router_skill_hitl_round_trip(
    mock_get_config,
    mock_get_llm,
    MockSkillMatcher,
    mock_interrupt,
    mock_get_profile,
):
    """
    When LLM confidence is below routing_confidence_threshold (0.6) AND
    SkillMatcher returns ambiguous candidates, interrupt() must be called
    with the correct ask_user payload containing skill-derived choices.
    """
    # ── Arrange ──────────────────────────────────────────────────────
    mock_get_config.return_value = {"configurable": {"__pregel_checkpointer": object()}}
    mock_get_profile.return_value = {
        "execution_policy": "interactive",
        "cloud_escalation_enabled": False,
    }
    mock_get_llm.return_value = _make_mock_llm(
        '{"routing":"complex","confidence":0.45,"toolbox":"all"}'
    )
    mock_interrupt.return_value = {
        "toolbox": ["web_search"],
        "route": "complex-cloud",
    }

    research_skill = _make_skill(
        "Research Assistant",
        ["research"],
        "Source-backed research",
        category="research",
    )
    viz_skill = _make_skill(
        "Data Visualization", ["chart", "graph"], "Create charts", category="data"
    )

    mock_matcher = MockSkillMatcher.return_value
    mock_matcher.match_with_confidence.return_value = MatchResult(
        is_ambiguous=True,
        top_match=research_skill,
        candidate_skills=[(research_skill, 0.55), (viz_skill, 0.42)],
        ambiguity_reason="Multiple skills are close matches",
        best_score=0.55,
    )

    state = _make_text_state("I need to research data trends")

    # ── Act ──────────────────────────────────────────────────────────
    result = await router_node(state)

    # ── Assert interrupt called ──────────────────────────────────────
    mock_interrupt.assert_called_once()
    call_args = mock_interrupt.call_args[0][0]
    assert call_args["type"] == "ask_user"
    assert "question" in call_args
    assert "choices" in call_args
    choices = call_args["choices"]
    assert len(choices) >= 2  # at least the 2 skills + "Others"
    # Verify choices contain actual skill names
    choice_names = [c.get("label", "") for c in choices if c.get("skill_name")]
    assert any("Research Assistant" in name for name in choice_names)
    # Last choice is "Others"
    assert choices[-1]["label"].startswith("Others")
    assert choices[-1].get("allows_user_input") is True
    # Verify HITL was used
    assert result["router_clarification_used"] is True


# ═════════════════════════════════════════════════════════════════════════
# Test 2: HITL resume sets correct toolbox from chosen skill
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
@patch("src.agent.routing.router.get_profile")
@patch("src.agent.routing.router.interrupt")
@patch("src.agent.routing.router.SkillMatcher")
@patch("src.agent.routing.router.get_small_llm", new_callable=AsyncMock)
@patch("langgraph.config.get_config")
async def test_router_skill_hitl_resume(
    mock_get_config,
    mock_get_llm,
    MockSkillMatcher,
    mock_interrupt,
    mock_get_profile,
):
    """
    When HITL fires and the user picks a skill choice, the router must set
    the correct toolbox from that skill's definition and mark HITL as used.
    """
    # ── Arrange ──────────────────────────────────────────────────────
    mock_get_config.return_value = {"configurable": {"__pregel_checkpointer": object()}}
    mock_get_profile.return_value = {
        "execution_policy": "interactive",
        "cloud_escalation_enabled": False,
    }
    mock_get_llm.return_value = _make_mock_llm(
        '{"routing":"complex","confidence":0.40,"toolbox":"all"}'
    )
    # Simulate user choosing the research skill
    mock_interrupt.return_value = {
        "toolbox": ["web_search"],
        "route": "complex-cloud",
        "skill_name": "research_assistant.md",
    }

    research_skill = _make_skill(
        "Research Assistant",
        ["research"],
        "Source-backed research",
        category="research",
    )
    mock_matcher = MockSkillMatcher.return_value
    mock_matcher.match_with_confidence.return_value = MatchResult(
        is_ambiguous=True,
        top_match=research_skill,
        candidate_skills=[(research_skill, 0.55)],
        ambiguity_reason="Low confidence",
        best_score=0.55,
    )

    state = _make_text_state("find the latest AI papers")

    # ── Act ──────────────────────────────────────────────────────────
    with patch("src.agent.routing.router._check_cloud_available", return_value=True):
        result = await router_node(state)

    # ── Assert ───────────────────────────────────────────────────────
    assert result["router_clarification_used"] is True
    assert result["selected_toolboxes"] == ["web_search"]
    assert result["route"] == "complex-cloud"
    assert "router_metadata" in result


# ═════════════════════════════════════════════════════════════════════════
# Test 3: Confident LLM + ambiguous skill → HITL still fires (Gap 2 fix)
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
@patch("src.agent.routing.router.get_profile")
@patch("src.agent.routing.router.interrupt")
@patch("src.agent.routing.router.SkillMatcher")
@patch("src.agent.routing.router.get_small_llm", new_callable=AsyncMock)
@patch("langgraph.config.get_config")
async def test_router_confident_ambiguous_skill_hitl(
    mock_get_config,
    mock_get_llm,
    MockSkillMatcher,
    mock_interrupt,
    mock_get_profile,
):
    """
    Even when the LLM is confident (above routing_confidence_threshold),
    HITL must still fire if the skill match is ambiguous — this is the
    decoupling fix from Gap 2.
    """
    # ── Arrange ──────────────────────────────────────────────────────
    mock_get_config.return_value = {"configurable": {"__pregel_checkpointer": object()}}
    mock_get_profile.return_value = {
        "execution_policy": "interactive",
        "cloud_escalation_enabled": False,
    }
    mock_get_llm.return_value = _make_mock_llm(
        '{"routing":"complex","confidence":0.85,"toolbox":"data_viz"}'  # HIGH confidence
    )
    mock_interrupt.return_value = {
        "toolbox": ["web_search"],
        "route": "complex-cloud",
    }

    research_skill = _make_skill(
        "Research Assistant", ["research"], "Research", category="research"
    )
    writing_skill = _make_skill(
        "Writer", ["write", "draft"], "Draft content", category="writing"
    )

    mock_matcher = MockSkillMatcher.return_value
    mock_matcher.match_with_confidence.return_value = MatchResult(
        is_ambiguous=True,  # skill is ambiguous despite confident LLM
        top_match=research_skill,
        candidate_skills=[(research_skill, 0.48), (writing_skill, 0.40)],
        ambiguity_reason="Multiple skills are close matches",
        best_score=0.48,
    )

    state = _make_text_state("draft a research proposal about climate change")

    # ── Act ──────────────────────────────────────────────────────────
    result = await router_node(state)

    # ── Assert: HITL fired even though LLM was confident ─────────────
    mock_interrupt.assert_called_once()
    call_args = mock_interrupt.call_args[0][0]
    assert call_args["type"] == "ask_user"
    assert result["router_clarification_used"] is True


# ═════════════════════════════════════════════════════════════════════════
# Test 4: Confident LLM + aligned strong skill → NO HITL (Gap 2 fix)
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
@patch("src.agent.routing.router.interrupt")
@patch("src.agent.routing.router.SkillMatcher")
@patch("src.agent.routing.router.get_small_llm", new_callable=AsyncMock)
@patch("langgraph.config.get_config")
async def test_router_confident_aligned_skill_no_hitl(
    mock_get_config,
    mock_get_llm,
    MockSkillMatcher,
    mock_interrupt,
):
    """
    When the LLM is confident AND the skill match is strong and unambiguous,
    no HITL should fire. The skill_matched field must be set in state with
    skill name, toolbox, and score.
    """
    # ── Arrange ──────────────────────────────────────────────────────
    mock_get_config.return_value = {"configurable": {"__pregel_checkpointer": object()}}
    mock_get_llm.return_value = _make_mock_llm(
        '{"routing":"complex","confidence":0.90,"toolbox":"web_search"}'  # HIGH confidence
    )
    # interrupt should never be called — we don't set a return value

    research_skill = _make_skill(
        "Research Assistant",
        ["research"],
        "Source-backed research",
        category="research",
    )

    mock_matcher = MockSkillMatcher.return_value
    mock_matcher.match_with_confidence.return_value = MatchResult(
        is_ambiguous=False,  # strong, unambiguous match
        top_match=research_skill,
        candidate_skills=[(research_skill, 0.91)],
        ambiguity_reason="",  # empty — not ambiguous
        best_score=0.91,
    )

    state = _make_text_state("research the latest deep learning trends")

    # ── Act ──────────────────────────────────────────────────────────
    result = await router_node(state)

    # ── Assert: NO HITL, skill_matched set ───────────────────────────
    mock_interrupt.assert_not_called()
    assert result["router_clarification_used"] is False

    skill_info = result.get("skill_matched")
    assert skill_info is not None, (
        "skill_matched must be set when skill match is strong"
    )
    assert skill_info["name"] == "Research Assistant"
    assert skill_info["score"] == 0.91
    assert isinstance(skill_info["toolbox"], list)
    assert len(skill_info["toolbox"]) > 0
