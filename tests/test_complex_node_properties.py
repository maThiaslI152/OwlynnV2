"""
Property-based tests for the Complex Node behavior.

# Feature: deepseek-hybrid-integration
# Property 7: Model Provenance Matches Route
# Property 8: Cloud-Only Anonymization
"""

import sys
from unittest.mock import MagicMock

sys.modules["mem0"] = MagicMock()

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agent.state import AgentState


# ── Valid domains ────────────────────────────────────────────────────────

VALID_ROUTES = {
    "simple",
    "complex-default",
    "complex-vision",
    "complex-longctx",
    "complex-cloud",
}
COMPLEX_ROUTES = {
    "complex-default",
    "complex-vision",
    "complex-longctx",
    "complex-cloud",
}

ROUTE_TO_MODEL = {
    "complex-default": "medium-default",
    "complex-vision": "medium-vision",
    "complex-longctx": "medium-longctx",
    "complex-cloud": "large-cloud",
}

LOCAL_ROUTES = {"complex-default", "complex-vision", "complex-longctx"}


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
        "custom_sensitive_terms": [],
        "lm_studio_fold_system": True,
        "medium_models": {
            "default": "medium-default-model",
            "vision": "zai-org/glm-4.6v-flash",
            "longctx": "LFM2 8B A1B GGUF Q8_0",
        },
    }


def _make_mock_llm():
    """Create a mock LLM that returns a simple AIMessage."""
    mock_llm = MagicMock()
    mock_response = AIMessage(content="Test response")
    mock_bound = MagicMock()
    mock_bound.ainvoke = AsyncMock(return_value=mock_response)
    mock_bound.bind = MagicMock(return_value=mock_bound)
    mock_llm.bind_tools = MagicMock(return_value=mock_bound)
    mock_llm.bind = MagicMock(return_value=mock_bound)
    return mock_llm


async def _passthrough_cloud_retry(
    bound_llm, prompt_messages, *, fallback_chain, model_label, route
):
    """Bypass circuit breaker / cost tracker — just call ainvoke directly."""
    return await bound_llm.ainvoke(prompt_messages)


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
                "src.agent.nodes.complex.get_medium_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "src.agent.nodes.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch("src.agent.nodes.complex.get_profile", return_value=profile),
            patch(
                "src.agent.nodes.complex._invoke_with_cloud_retry",
                side_effect=_passthrough_cloud_retry,
            ),
        ):
            from src.agent.nodes.complex import complex_llm_node

            result = await complex_llm_node(state)

        expected_label = ROUTE_TO_MODEL[route]
        assert result["model_used"] == expected_label, (
            f"Route {route!r} should produce model_used={expected_label!r}, "
            f"got {result['model_used']!r}"
        )

    @given(route=local_route_st, text=user_text_st)
    @settings(max_examples=100, deadline=10000)
    @pytest.mark.asyncio
    async def test_local_routes_never_produce_cloud_label(self, route: str, text: str):
        """Local routes must never set model_used to large-cloud."""
        state = _make_state(route, text)
        mock_llm = _make_mock_llm()
        profile = _mock_profile()

        with (
            patch(
                "src.agent.nodes.complex.get_medium_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "src.agent.nodes.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch("src.agent.nodes.complex.get_profile", return_value=profile),
        ):
            from src.agent.nodes.complex import complex_llm_node

            result = await complex_llm_node(state)

        assert "cloud" not in result["model_used"], (
            f"Local route {route!r} should not produce cloud model_used, "
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
                "src.agent.nodes.complex.get_medium_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "src.agent.nodes.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch("src.agent.nodes.complex.get_profile", return_value=profile),
            patch(
                "src.agent.nodes.complex._invoke_with_cloud_retry",
                side_effect=_passthrough_cloud_retry,
            ),
        ):
            from src.agent.nodes.complex import complex_llm_node

            result = await complex_llm_node(state)

        assert result["model_used"] == "large-cloud"

    @pytest.mark.asyncio
    async def test_default_route_produces_medium_default(self):
        """complex-default route must set model_used to medium-default."""
        state = _make_state("complex-default")
        mock_llm = _make_mock_llm()
        profile = _mock_profile()

        with (
            patch(
                "src.agent.nodes.complex.get_medium_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "src.agent.nodes.complex.get_cloud_llm",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch("src.agent.nodes.complex.get_profile", return_value=profile),
        ):
            from src.agent.nodes.complex import complex_llm_node

            result = await complex_llm_node(state)

        assert result["model_used"] == "medium-default"
