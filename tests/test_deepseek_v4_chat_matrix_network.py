"""Live DeepSeek V4 chat matrix — flash/pro × thinking on/off.

Run via CI (loads .env automatically):

    ./scripts/ci.sh --network

Or manually:

    set -a && source .env && set +a
    PYTHONPATH=$(pwd) python -m pytest -m network -v \\
      tests/test_deepseek_v4_chat_matrix_network.py \\
      tests/test_deepseek_cache_network.py

See docs/guides/deepseek-v4-testing.md for the full matrix and manual UI checklist.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.modules["mem0"] = MagicMock()

PROMPT = "In exactly 2 sentences, compare REST and GraphQL for a mobile app backend."
MIN_CONTENT_LEN = 80


def _api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


@pytest.mark.network
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tier,thinking_enabled",
    [
        ("flash", False),
        ("flash", True),
        ("pro", False),
        ("pro", True),
    ],
)
async def test_deepseek_v4_chat_matrix(tier, thinking_enabled):
    """Each tier/thinking combo returns substantive visible content."""
    if not _api_key():
        pytest.skip("DEEPSEEK_API_KEY not set")

    from openai import AsyncOpenAI

    from src.agent.nodes.complex_utils.cloud_payload import (
        COMPLEX_PROMPT_STABLE,
        finalize_cloud_visible_content,
    )
    from src.config.config_loader import config

    base_url = config.get("models.cloud.base_url", "https://api.deepseek.com/v1")
    model = config.get(f"models.cloud.tiers.{tier}")
    client = AsyncOpenAI(api_key=_api_key(), base_url=base_url)

    kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": COMPLEX_PROMPT_STABLE.format(style_hint=""),
            },
            {"role": "user", "content": PROMPT},
        ],
        "max_tokens": 512,
        "temperature": 0.4,
        "extra_body": {
            "thinking": {"type": "enabled" if thinking_enabled else "disabled"}
        },
    }
    if thinking_enabled:
        kwargs["reasoning_effort"] = "high"

    response = await client.chat.completions.create(**kwargs)
    msg = response.choices[0].message
    reasoning = getattr(msg, "reasoning_content", None) or ""
    visible = finalize_cloud_visible_content(msg.content or "", reasoning)

    assert len(visible) >= MIN_CONTENT_LEN, (
        f"{tier} thinking={thinking_enabled}: content too short ({len(visible)!r})"
    )
    lower = visible.lower()
    assert "rest" in lower or "graphql" in lower, visible[:200]


@pytest.mark.network
@pytest.mark.asyncio
async def test_cloud_brief_multiturn_produces_substantive_reply():
    """Full brief path must keep the latest user task (regression for greeting overwrite)."""
    if not _api_key():
        pytest.skip("DEEPSEEK_API_KEY not set")

    from openai import AsyncOpenAI

    from src.agent.hitl.cloud_brief import build_cloud_brief
    from src.agent.nodes.complex_utils.cloud_payload import (
        COMPLEX_PROMPT_STABLE,
        finalize_cloud_visible_content,
    )
    from src.config.config_loader import config

    brief = build_cloud_brief(
        last_user_message="Compare REST vs GraphQL for a mobile app backend in 3 bullets each.",
        last_assistant_summary="Hi! I'm here to assist you. What would you like to discuss?",
        selected_toolboxes=["all"],
    )
    assert "Compare REST vs GraphQL" in brief

    base_url = config.get("models.cloud.base_url", "https://api.deepseek.com/v1")
    model = config.get("models.cloud.tiers.flash", "deepseek-v4-flash")
    client = AsyncOpenAI(api_key=_api_key(), base_url=base_url)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": COMPLEX_PROMPT_STABLE.format(style_hint=""),
            },
            {"role": "user", "content": brief},
        ],
        max_tokens=800,
        temperature=0.4,
        extra_body={"thinking": {"type": "enabled"}},
        reasoning_effort="high",
    )
    msg = response.choices[0].message
    reasoning = getattr(msg, "reasoning_content", None) or ""
    visible = finalize_cloud_visible_content(msg.content or "", reasoning)

    assert len(visible) >= MIN_CONTENT_LEN
    lower = visible.lower()
    assert "rest" in lower and "graphql" in lower
    assert "what can i help" not in lower
