"""Tests for the secret store (Local env-backed API key storage)."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.modules["mem0"] = MagicMock()


class TestSecretStore:
    """Unit tests for secret_store functions."""

    def test_resolve_from_env_var(self):
        """Env var takes priority when set."""
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-api-key"}),
            patch(
                "src.memory.user_profile.get_profile",
                return_value={"deepseek_api_key": ""},
            ),
        ):
            from src.config.secret_store import resolve_deepseek_api_key

            assert resolve_deepseek_api_key() == "env-api-key"

    def test_resolve_from_profile_fallback(self):
        """Profile is fallback when env is empty and file doesn't exist."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("pathlib.Path.exists", return_value=False),
            patch(
                "src.memory.user_profile.get_profile",
                return_value={"deepseek_api_key": "profile-key"},
            ),
        ):
            from src.config.secret_store import resolve_deepseek_api_key

            assert resolve_deepseek_api_key() == "profile-key"

    def test_resolve_empty_when_none_configured(self):
        """Returns empty string when no key source has a key."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("pathlib.Path.exists", return_value=False),
            patch(
                "src.memory.user_profile.get_profile",
                return_value={"deepseek_api_key": ""},
            ),
        ):
            from src.config.secret_store import resolve_deepseek_api_key

            assert resolve_deepseek_api_key() == ""

    def test_store_rejects_empty_key(self):
        from src.config.secret_store import store_deepseek_api_key

        with pytest.raises(ValueError):
            store_deepseek_api_key("")
        with pytest.raises(ValueError):
            store_deepseek_api_key("   ")

    def test_store_writes_secrets_env(self):
        """store_deepseek_api_key writes to secrets.env."""
        with (
            patch("src.config.secret_store._write_secrets_env") as mock_write,
            patch("src.config.secret_store._clear_profile_key"),
        ):
            from src.config.secret_store import store_deepseek_api_key

            store_deepseek_api_key("sk-test-key-123")
            mock_write.assert_called_once_with("DEEPSEEK_API_KEY", "sk-test-key-123")
            assert os.environ["DEEPSEEK_API_KEY"] == "sk-test-key-123"

    def test_delete_clears_secrets_env(self):
        with (
            patch("src.config.secret_store._write_secrets_env") as mock_write,
            patch("src.config.secret_store._clear_profile_key"),
        ):
            from src.config.secret_store import delete_deepseek_api_key

            os.environ["DEEPSEEK_API_KEY"] = "something"
            delete_deepseek_api_key()
            mock_write.assert_called_once_with("DEEPSEEK_API_KEY", "")
            assert "DEEPSEEK_API_KEY" not in os.environ

    def test_verify_valid_key(self):
        """verify_deepseek_api_key returns True for 200 response."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch.object(httpx.Client, "post", return_value=mock_response),
            patch(
                "src.memory.user_profile.get_profile",
                return_value={
                    "cloud_llm_base_url": "https://api.deepseek.com/v1",
                    "cloud_llm_model_name": "deepseek-v4",
                },
            ),
        ):
            from src.config.secret_store import verify_deepseek_api_key

            valid, msg = verify_deepseek_api_key("sk-test-key")
            assert valid is True

    def test_verify_invalid_key_401(self):
        """verify_deepseek_api_key returns False for 401."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 401

        with (
            patch.object(httpx.Client, "post", return_value=mock_response),
            patch(
                "src.memory.user_profile.get_profile",
                return_value={
                    "cloud_llm_base_url": "https://api.deepseek.com/v1",
                    "cloud_llm_model_name": "deepseek-v4",
                },
            ),
        ):
            from src.config.secret_store import verify_deepseek_api_key

            valid, msg = verify_deepseek_api_key("sk-bad-key")
            assert valid is False
            assert "401" in msg
