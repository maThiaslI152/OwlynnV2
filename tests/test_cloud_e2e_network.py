"""R3: E2E complex-cloud path with valid DeepSeek API key (network)."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

sys.modules["mem0"] = MagicMock()


def _api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


@pytest.mark.network
@pytest.mark.asyncio
async def test_complex_cloud_e2e_with_valid_key():
    """Invoke complex_llm_node on complex-cloud route with real DeepSeek."""
    if not _api_key():
        pytest.skip("DEEPSEEK_API_KEY not set")

    from src.agent.nodes.complex import complex_llm_node
    from src.memory.user_profile import get_profile

    profile = get_profile()
    state = {
        "route": "complex-cloud",
        "mode": "tools_off",
        "messages": [
            HumanMessage(
                content="In one sentence: what is 17 + 25? Reply with the number only."
            )
        ],
        "memory_context": "None",
        "knowledge_context": "None",
        "persona": "No persona",
        "web_search_enabled": False,
        "thread_id": "network-e2e-test",
        "token_budget": 256,
    }

    with patch("src.agent.nodes.complex.get_profile", return_value=profile):
        result = await complex_llm_node(state)

    assert "large-cloud" in (result.get("model_used") or "")
    usage = result.get("api_tokens_used") or {}
    assert int(usage.get("prompt_tokens", 0)) > 0
    msgs = result.get("messages") or []
    assert msgs
    content = str(getattr(msgs[0], "content", "") or "")
    assert "42" in content
