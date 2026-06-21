"""Tests for cloud invoke retry and circuit breaker integration."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules["mem0"] = MagicMock()

import pytest


@pytest.mark.anyio
class TestCloudInvokeRetry:
    async def test_circuit_breaker_open_raises(self):
        from src.agent.cloud.cloud_invoke import invoke_cloud_chat
        from src.agent.cloud.cloud_payload import CloudThinkingConfig

        mock_client = MagicMock()
        with patch(
            "src.agent.cloud.cloud_circuit_breaker.get_circuit_breaker"
        ) as mock_cb:
            mock_cb.return_value.is_open.return_value = True
            with pytest.raises(RuntimeError, match="Circuit breaker open"):
                await invoke_cloud_chat(
                    llm_client=mock_client,
                    model_name="deepseek-v4-flash",
                    messages=[],
                    max_tokens=100,
                    thinking=CloudThinkingConfig(
                        thinking_enabled=False,
                        extra_body={"thinking": {"type": "disabled"}},
                    ),
                )
            mock_client.chat.completions.create.assert_not_called()

    async def test_retry_on_429_then_success(self):
        from src.agent.cloud.cloud_invoke import invoke_cloud_chat
        from src.agent.cloud.cloud_payload import CloudThinkingConfig

        mock_response = MagicMock()
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=5,
            prompt_cache_hit_tokens=0,
            prompt_cache_miss_tokens=10,
        )
        mock_response.choices = [
            MagicMock(message=MagicMock(content="ok", tool_calls=None))
        ]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                Exception("429 Rate limit"),
                mock_response,
            ]
        )

        with patch(
            "src.agent.cloud.cloud_circuit_breaker.get_circuit_breaker"
        ) as mock_cb:
            mock_cb.return_value.is_open.return_value = False
            with patch("asyncio.sleep", AsyncMock()):
                raw, usage = await invoke_cloud_chat(
                    llm_client=mock_client,
                    model_name="deepseek-v4-flash",
                    messages=[],
                    max_tokens=100,
                    thinking=CloudThinkingConfig(
                        thinking_enabled=False,
                        extra_body={"thinking": {"type": "disabled"}},
                    ),
                )
        assert raw is mock_response
        assert usage.get("prompt_tokens", 0) >= 0
        assert mock_client.chat.completions.create.call_count == 2
        mock_cb.return_value.record_success.assert_called()

    async def test_user_id_passed_to_api(self):
        from src.agent.cloud.cloud_invoke import invoke_cloud_chat
        from src.agent.cloud.cloud_payload import CloudThinkingConfig

        mock_response = MagicMock()
        mock_response.usage = MagicMock(
            prompt_tokens=1,
            completion_tokens=1,
            prompt_cache_hit_tokens=0,
            prompt_cache_miss_tokens=1,
        )
        mock_response.choices = [
            MagicMock(message=MagicMock(content="ok", tool_calls=None))
        ]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch(
            "src.agent.cloud.cloud_circuit_breaker.get_circuit_breaker"
        ) as mock_cb:
            mock_cb.return_value.is_open.return_value = False
            await invoke_cloud_chat(
                llm_client=mock_client,
                model_name="deepseek-v4-flash",
                messages=[],
                max_tokens=100,
                thinking=CloudThinkingConfig(
                    thinking_enabled=False,
                    extra_body={"thinking": {"type": "disabled"}},
                ),
                user_id="thread-abc",
            )

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs.get("user") == "thread-abc"
