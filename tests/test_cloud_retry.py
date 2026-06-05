"""Tests for the cloud LLM retry logic in complex.py."""

import sys
from unittest.mock import MagicMock

# Force mem0 mock before any other imports — other test files may have
# already loaded the real mem0 module when running under CI.
sys.modules["mem0"] = MagicMock()

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.anyio
class TestCloudRetry:
    async def test_success_first_try(self):
        """Returns response on first successful attempt."""
        from src.agent.nodes.complex import _invoke_with_cloud_retry

        mock_response = MagicMock()
        mock_response.response_metadata = {
            "token_usage": {"input_tokens": 10, "output_tokens": 5}
        }
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        fallback_chain = []
        result = await _invoke_with_cloud_retry(
            mock_llm,
            [MagicMock()],
            fallback_chain=fallback_chain,
            model_label="large-cloud",
            route="complex-cloud",
        )
        assert result is mock_response
        assert mock_llm.ainvoke.call_count == 1

    async def test_retry_on_429(self):
        """Exponential backoff retry on 429."""
        from src.agent.nodes.complex import _invoke_with_cloud_retry

        mock_response = MagicMock()
        mock_response.response_metadata = {
            "token_usage": {"input_tokens": 10, "output_tokens": 5}
        }
        mock_llm = MagicMock()
        # Fails twice with 429, succeeds on third attempt
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                Exception("429 Rate limit exceeded"),
                Exception("429 Too many requests"),
                mock_response,
            ]
        )

        fallback_chain = []
        result = await _invoke_with_cloud_retry(
            mock_llm,
            [MagicMock()],
            fallback_chain=fallback_chain,
            model_label="large-cloud",
            route="complex-cloud",
        )
        assert result is mock_response
        assert mock_llm.ainvoke.call_count == 3

    async def test_retry_on_500(self):
        """Retry on 5xx server errors."""
        from src.agent.nodes.complex import _invoke_with_cloud_retry

        mock_response = MagicMock()
        mock_response.response_metadata = {"token_usage": {}}
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                Exception("500 Internal Server Error"),
                mock_response,
            ]
        )

        fallback_chain = []
        result = await _invoke_with_cloud_retry(
            mock_llm,
            [MagicMock()],
            fallback_chain=fallback_chain,
            model_label="large-cloud",
            route="complex-cloud",
        )
        assert result is mock_response
        assert mock_llm.ainvoke.call_count == 2

    async def test_no_retry_on_401(self):
        """No retry on auth errors."""
        from src.agent.nodes.complex import _invoke_with_cloud_retry

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("401 Unauthorized"))

        fallback_chain = []
        with pytest.raises(Exception, match="401"):
            await _invoke_with_cloud_retry(
                mock_llm,
                [MagicMock()],
                fallback_chain=fallback_chain,
                model_label="large-cloud",
                route="complex-cloud",
            )
        assert mock_llm.ainvoke.call_count == 1

    async def test_exhausted_retries_raises(self):
        """Raises after max retries exhausted."""
        from src.agent.nodes.complex import _invoke_with_cloud_retry

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("429 Rate limit"))

        fallback_chain = []
        with pytest.raises(Exception, match="429"):
            await _invoke_with_cloud_retry(
                mock_llm,
                [MagicMock()],
                fallback_chain=fallback_chain,
                model_label="large-cloud",
                route="complex-cloud",
            )
        # 1 initial + 3 retries = 4 attempts
        assert mock_llm.ainvoke.call_count == 4

    async def test_circuit_breaker_open_skips_call(self):
        """When circuit breaker is open, cloud call is skipped."""
        from src.agent.nodes.complex import _invoke_with_cloud_retry

        mock_llm = MagicMock()

        fallback_chain = []
        with patch("src.agent.cloud_circuit_breaker.get_circuit_breaker") as mock_cb:
            mock_cb.return_value.is_open.return_value = True
            with pytest.raises(Exception, match="Circuit breaker open"):
                await _invoke_with_cloud_retry(
                    mock_llm,
                    [MagicMock()],
                    fallback_chain=fallback_chain,
                    model_label="large-cloud",
                    route="complex-cloud",
                )
            mock_llm.ainvoke.assert_not_called()
