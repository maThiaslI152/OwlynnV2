"""
Property-based tests for the Complex Node behavior.

# Feature: deepseek-hybrid-integration
# Property 7: Model Provenance Matches Route
# Property 8: Cloud-Only Anonymization
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules["mem0"] = MagicMock()

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agent.state import AgentState


# ── Valid domains ────────────────────────────────────────────────────────

VALID_ROUTES = {
    "simple",
    "complex-cloud",
}
COMPLEX_ROUTES = {
    "complex-cloud",
}

ROUTE_TO_MODEL = {
    "complex-cloud": "large-cloud",
}

LOCAL_ROUTES: set[str] = set()


# ── Strategies ───────────────────────────────────────────────────────────

route_st = st.sampled_from(sorted(COMPLEX_ROUTES))
local_route_st = st.sampled_from(sorted(LOCAL_ROUTES))
bool_st = st.booleans()
user_text_st = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
    ),
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_state(route: str, text: str = "Hello", anon_enabled: bool = True) -> dict:
    """Build a minimal AgentState dict for complex_llm_node."""
    return {
        "messages": [HumanMessage(content=text)],
        "route": route,
        "mode": "tools_on",
        "web_search_enabled": True,
        "memory_context": "None",
        "persona": "Test persona",
        "response_style": None,
        "security_decision": None,
        "security_reason": None,
        "token_budget": 4096,
        "selected_toolboxes": ["all"],
    }


def _mock_profile(anon_enabled: bool = True) -> dict:
    """Return a profile dict with configurable anonymization toggle."""
    return {
        "name": "TestUser",
        "small_llm_base_url": "http://127.0.0.1:1234/v1",
        "cloud_llm_base_url": "https://api.deepseek.com/v1",
        "cloud_anonymization_enabled": anon_enabled,
        "cloud_brief_enabled": False,
        "custom_sensitive_terms": [],
        "lm_studio_fold_system": True,
    }


def _make_mock_llm():
    """Create a mock LLM that returns a simple AIMessage."""
    mock_llm = MagicMock()
    mock_llm.async_client = None
    mock_response = AIMessage(content="Test response")
    mock_bound = MagicMock()
    mock_bound.ainvoke = AsyncMock(return_value=mock_response)
    mock_bound.bind = MagicMock(return_value=mock_bound)
    mock_llm.bind_tools = MagicMock(return_value=mock_bound)
    mock_llm.bind = MagicMock(return_value=mock_bound)
    return mock_llm


async def _passthrough_cloud_path(
    *,
    llm,
    prompt_messages,
    tools,
    budget,
    state,
    profile,
    mode,
    tools_bound,
):
    """Bypass circuit breaker / raw API — invoke bound LLM directly."""
    if tools_bound and tools:
        bound = llm.bind_tools(tools, strict=True).bind(max_tokens=budget)
    else:
        bound = llm.bind(max_tokens=budget)
    response = await bound.ainvoke(prompt_messages)
    return response, {"prompt_tokens": 0, "completion_tokens": 0}


# ═════════════════════════════════════════════════════════════════════════
# Property 7: Model Provenance Matches Route
# ═════════════════════════════════════════════════════════════════════════


class TestModelProvenanceMatchesRoute:
    """
    For any route value processed by the Complex_Node, the model_used field
    in the returned AgentState SHALL correspond to the route.
    """

    @given(route=route_st, text=user_text_st)
    @settings(max_examples=100, deadline=10000)
    @pytest.mark.asyncio
    async def test_model_used_matches_route_for_all_complex_routes(
        self, route: str, text: str
    ):
        """model_used always corresponds to the route when no errors occur."""
        state = _make_state(route, text)
        mock_llm = _make_mock_llm()
        profile = _mock_profile()
        with (
            patch(
                "src.agent.nodes.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch("src.agent.nodes.complex.get_profile", return_value=profile),
            patch(
                "src.agent.nodes.complex._invoke_cloud_path",
                side_effect=_passthrough_cloud_path,
            ),
        ):
            from src.agent.nodes.complex import complex_llm_node

            result = await complex_llm_node(state)

        expected_label = ROUTE_TO_MODEL[route]
        assert result["model_used"] == expected_label, (
            f"Route {route!r} should produce model_used={expected_label!r}, "
            f"got {result['model_used']!r}"
        )

    @pytest.mark.asyncio
    async def test_cloud_route_produces_large_cloud(self):
        """complex-cloud route must set model_used to large-cloud."""
        state = _make_state("complex-cloud")
        mock_llm = _make_mock_llm()
        profile = _mock_profile()
        with (
            patch(
                "src.agent.nodes.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch("src.agent.nodes.complex.get_profile", return_value=profile),
            patch(
                "src.agent.nodes.complex._invoke_cloud_path",
                side_effect=_passthrough_cloud_path,
            ),
        ):
            from src.agent.nodes.complex import complex_llm_node

            result = await complex_llm_node(state)

        assert result["model_used"] == "large-cloud"
