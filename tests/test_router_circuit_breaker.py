"""Router cloud availability respects circuit breaker state."""

from unittest.mock import patch

from src.agent.routing.router import _check_cloud_available


def test_cloud_unavailable_when_breaker_open():
    with (
        patch(
            "src.config.secret_store.resolve_deepseek_api_key",
            return_value="sk-test",
        ),
        patch(
            "src.memory.user_profile.get_profile",
            return_value={"cloud_escalation_enabled": True},
        ),
        patch("src.agent.cloud.cloud_circuit_breaker.get_circuit_breaker") as mock_cb,
    ):
        mock_cb.return_value.is_open.return_value = True
        assert _check_cloud_available() is False
