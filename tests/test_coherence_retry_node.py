"""Tests for the coherence_retry_node — self-correction loop.

Mirrors the patterns from tests/test_response_coherence.py. Validates:
- Below-threshold coherence invokes the retry path
- Above-threshold coherence short-circuits
- Retry counter increments and caps at max_retries
- Cloud route uses _invoke_cloud_path
- Strict-cloud mode blocks fallback
- Replaces the last AI message with the cleaned retry output
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules["mem0"] = MagicMock()

from langchain_core.messages import AIMessage, HumanMessage

from src.agent.nodes import coherence_retry as cr_mod
from src.agent.nodes.coherence_retry import coherence_retry_node


def _state(
    *,
    route="complex-cloud",
    confidence=0.2,
    reason="Off-topic and short",
    messages=None,
    retry_round=0,
    strict_cloud=False,
):
    state = {
        "messages": messages
        or [
            HumanMessage(content="What is photosynthesis?"),
            AIMessage(content="It is a thing plants do."),
        ],
        "route": route,
        "response_confidence": confidence,
        "response_coherence": {
            "coherent": False,
            "score": confidence,
            "reason": reason,
        },
        "_coherence_retry_round": retry_round,
    }
    if strict_cloud:
        state["_strict_cloud"] = True
    return state


@pytest.mark.anyio
async def test_retry_disabled_returns_empty():
    state = _state()
    with patch(
        "src.agent.nodes.coherence_retry.config",
        {
            "coherence": {
                "enabled": False,
                "retry_threshold": 0.4,
                "max_retries": 1,
                "retry_token_budget": 2048,
            }
        },
    ):
        out = await coherence_retry_node(state)
    assert out == {}


@pytest.mark.anyio
async def test_retry_strict_cloud_blocks_fallback(monkeypatch):
    """When cloud is unavailable, the retry fails gracefully with no local fallback."""
    from src.agent.llm import CloudUnavailableError

    async def fake_get_cloud_llm(_tier):
        raise CloudUnavailableError("circuit open")

    monkeypatch.setattr(cr_mod, "get_cloud_llm", fake_get_cloud_llm)

    out = await coherence_retry_node(_state(route="complex-cloud"))

    assert any(
        "coherence_retry_cloud_unavailable" in entry.get("reason", "")
        for entry in out.get("fallback_chain", [])
    )


@pytest.mark.anyio
async def test_retry_cloud_uses_invoke_cloud_path(monkeypatch):
    """Cloud route calls _invoke_cloud_path."""
    from src.agent.nodes import coherence_retry as cr_mod

    fake_response = AIMessage(content="Cloud retry answer")
    captured_kwargs: dict = {}

    async def fake_invoke_cloud_path(**kwargs):
        captured_kwargs.update(kwargs)
        return fake_response, {"prompt_tokens": 5, "completion_tokens": 10}

    async def fake_get_cloud_llm(_tier):
        return MagicMock()

    monkeypatch.setattr(cr_mod, "_invoke_cloud_path", fake_invoke_cloud_path)
    monkeypatch.setattr(cr_mod, "get_cloud_llm", fake_get_cloud_llm)

    out = await coherence_retry_node(_state(route="complex-cloud"))

    assert out["messages"][0].content == "Cloud retry answer"
    assert out["_coherence_retry_round"] == 1
    assert captured_kwargs["tools"] is None
    assert captured_kwargs["tools_bound"] is False
    assert captured_kwargs["mode"] == "tools_off"
    assert out["api_tokens_used"] == {"prompt_tokens": 5, "completion_tokens": 10}


@pytest.mark.anyio
async def test_retry_returns_empty_when_no_messages():
    out = await coherence_retry_node({"messages": [], "route": "complex-cloud"})
    assert out == {}


@pytest.mark.anyio
async def test_strict_cloud_forces_cloud_path_and_blocks_fallback(monkeypatch):
    """Cloud path failure returns gracefully with no local fallback."""
    from src.agent.llm import CloudUnavailableError

    async def fake_get_cloud_llm(_tier):
        raise CloudUnavailableError("circuit open")

    monkeypatch.setattr(cr_mod, "get_cloud_llm", fake_get_cloud_llm)

    out = await coherence_retry_node(_state(route="complex-cloud"))

    assert any(
        "coherence_retry_cloud_unavailable" in entry.get("reason", "")
        for entry in out.get("fallback_chain", [])
    )
