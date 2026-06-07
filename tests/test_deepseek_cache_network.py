"""Network integration test for DeepSeek prompt cache hits."""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.modules["mem0"] = MagicMock()


@pytest.mark.network
@pytest.mark.asyncio
async def test_deepseek_prompt_cache_hit_on_repeated_prefix():
    """Second call with identical stable prefix should report cache hit tokens."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY not set")

    from openai import AsyncOpenAI

    from src.agent.nodes.complex_utils.cloud_payload import COMPLEX_PROMPT_STABLE
    from src.config.config_loader import config

    base_url = config.get("models.cloud.base_url", "https://api.deepseek.com/v1")
    model = config.get("models.cloud.tiers.flash", "deepseek-v4-flash")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    stable = COMPLEX_PROMPT_STABLE.format(style_hint="")
    messages = [
        {"role": "system", "content": stable},
        {"role": "user", "content": "Reply with exactly: CACHE_TEST_OK"},
    ]

    first = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=16,
        extra_body={"thinking": {"type": "disabled"}},
    )
    second = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=16,
        extra_body={"thinking": {"type": "disabled"}},
    )

    hit = getattr(second.usage, "prompt_cache_hit_tokens", 0) or 0
    assert getattr(first.usage, "prompt_tokens", 0) > 0
    assert hit > 0, (
        f"Expected prompt_cache_hit_tokens > 0 on second call; "
        f"first={first.usage}, second={second.usage}"
    )
