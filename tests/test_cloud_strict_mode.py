"""Tests for cloud-only behavior (no local fallback)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.modules["mem0"] = MagicMock()


@pytest.mark.anyio
async def test_complex_node_blocks_fallback_on_cloud_failure():
    """When cloud LLM fails, the complex node produces a graceful error
    without falling back to any local model."""
    from src.agent.llm import CloudUnavailableError
    from src.agent.core.complex import complex_llm_node

    async def _cloud_raises(*_args, **_kwargs):
        raise CloudUnavailableError("No API key")

    state = {
        "messages": [HumanMessage(content="Write a Python function")],
        "route": "complex-cloud",
        "mode": "tools_on",
        "web_search_enabled": True,
        "memory_context": "None",
        "persona": "Owlynn",
        "token_budget": 4096,
        "selected_toolboxes": ["all"],
    }
    profile = {
        "name": "TestUser",
        "cloud_anonymization_enabled": False,
        "cloud_brief_enabled": False,
        "custom_sensitive_terms": [],
        "lm_studio_fold_system": True,
    }

    with (
        patch("src.agent.core.complex.get_cloud_llm", side_effect=_cloud_raises),
        patch("src.agent.core.complex.get_profile", return_value=profile),
    ):
        result = await complex_llm_node(state)

    assert result["model_used"] == "large-cloud-failed"
    msgs = result.get("messages", [])
    assert len(msgs) > 0
    assert any(
        word in msgs[0].content.lower()
        for word in ("error", "unavailable", "try again")
    )


@pytest.mark.anyio
async def test_coherence_retry_blocks_fallback_on_cloud_failure():
    """Coherence retry node returns graceful failure when cloud is unavailable."""
    from src.agent.llm import CloudUnavailableError
    from src.agent.nodes.coherence_retry import coherence_retry_node

    async def fake_get_cloud_llm(_tier):
        raise CloudUnavailableError("circuit open")

    with patch("src.agent.nodes.coherence_retry.get_cloud_llm", fake_get_cloud_llm):
        out = await coherence_retry_node(
            {
                "messages": [
                    HumanMessage(content="What is photosynthesis?"),
                    AIMessage(content="It is a thing plants do."),
                ],
                "route": "complex-cloud",
                "response_confidence": 0.2,
                "response_coherence": {
                    "coherent": False,
                    "score": 0.2,
                    "reason": "Off-topic and short",
                },
                "_coherence_retry_round": 0,
            }
        )

    assert any(
        entry.get("reason") == "coherence_retry_cloud_unavailable:CloudUnavailableError"
        for entry in out.get("fallback_chain", [])
    )


def test_eval_cloud_fallback_detection():
    """Verify eval scoring detects cloud failures via CLOUD_FAILURE_BADGES."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_local_frontier_eval import score_exchange

    exchange = {
        "route": "complex-cloud",
        "model_badge": "large-cloud-failed",
    }
    expected = {"expected_route": "complex"}
    scores = score_exchange(exchange, expected, profile="cloud")
    assert scores.get("cloud_fallback_fail")
    assert scores.get("cloud_regression")


def test_eval_simple_route_small_local_not_regression():
    """Simple route with small-local badge should NOT trigger regression."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_local_frontier_eval import score_exchange

    exchange = {
        "route": "simple",
        "model_badge": "small-local",
    }
    expected = {"expected_route": "simple"}
    scores = score_exchange(exchange, expected, profile="cloud")
    assert not scores.get("cloud_fallback_fail")
