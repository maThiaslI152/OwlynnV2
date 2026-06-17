"""Tests for strict cloud mode (no local Qwen fallback)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from src.agent.cloud_strict import (
    CLOUD_FAILED_MODEL,
    SMALL_FAILED_MODEL,
    block_cloud_local_fallback,
    cloud_no_local_fallback_enabled,
)


@pytest.mark.parametrize(
    "profile_val,config_val,expected",
    [
        (True, False, True),
        (False, True, False),
        (None, True, True),
        (None, False, False),
    ],
)
def test_cloud_no_local_fallback_enabled(profile_val, config_val, expected):
    profile = {}
    if profile_val is not None:
        profile["cloud_no_local_fallback"] = profile_val
    with (
        patch("src.memory.user_profile.get_profile", return_value=profile),
        patch("src.agent.cloud_strict.config.get", return_value=config_val),
    ):
        assert cloud_no_local_fallback_enabled() is expected


def test_block_cloud_local_fallback_when_disabled():
    with patch(
        "src.agent.cloud_strict.cloud_no_local_fallback_enabled", return_value=False
    ):
        assert block_cloud_local_fallback(fallback_chain=[], reason="test") is None


def test_block_cloud_local_fallback_returns_failure_state():
    with patch(
        "src.agent.cloud_strict.cloud_no_local_fallback_enabled", return_value=True
    ):
        out = block_cloud_local_fallback(
            fallback_chain=[{"model": "large-cloud", "status": "failed"}],
            reason="vision_proxy_failed",
        )
    assert out is not None
    assert out["model_used"] == CLOUD_FAILED_MODEL
    assert isinstance(out["messages"][0], AIMessage)
    assert "Strict cloud mode" in out["messages"][0].content
    assert out["fallback_chain"][-1]["status"] == "blocked"
    assert out["fallback_chain"][-1]["reason"] == "vision_proxy_failed"


@pytest.mark.asyncio
async def test_simple_node_blocks_medium_fallback_when_strict():
    from src.agent.nodes import simple as simple_mod

    state = {
        "messages": [AIMessage(content="hi")],
        "persona": "Owlynn",
        "token_budget": 256,
    }
    with (
        patch(
            "src.agent.nodes.simple.cloud_no_local_fallback_enabled",
            return_value=True,
        ),
        patch(
            "src.agent.nodes.simple.get_small_llm",
            side_effect=RuntimeError("small down"),
        ),
    ):
        out = await simple_mod.simple_node(state)
    assert out["model_used"] == SMALL_FAILED_MODEL
    assert "Strict cloud mode" in out["messages"][0].content


def test_eval_cloud_qwen_fallback_large_cloud_failed():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_local_frontier_eval import eval_cloud_qwen_fallback

    exchange = {
        "route": "complex-cloud",
        "model_badge": "large-cloud-failed",
        "fallback_chain": [
            {"reason": "fallback_generic_cloud_error", "status": "blocked"}
        ],
    }
    expected = {"expected_route": "complex"}
    assert eval_cloud_qwen_fallback(exchange, expected, profile="cloud")


def test_eval_cloud_qwen_fallback_simple_strict_fail():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_local_frontier_eval import eval_cloud_qwen_fallback

    exchange = {
        "route": "simple",
        "model_badge": "small-local-failed",
    }
    expected = {"expected_route": "simple"}
    assert eval_cloud_qwen_fallback(exchange, expected, profile="cloud")
