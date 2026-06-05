"""Tests for the secret store (Keychain-backed API key storage)."""

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.modules["mem0"] = MagicMock()


@pytest.fixture(autouse=True)
def _reset_keyring_cache():
    """Reset the lazy keyring cache between tests."""
    import src.config.secret_store as ss

    ss._keyring = None


class TestSecretStore:
    """Unit tests for secret_store functions."""

    def _mock_keyring(self, get_password_return=None):
        """Patch keyring module into the secret store's lazy cache."""
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = get_password_return
        import src.config.secret_store as ss

        ss._keyring = mock_kr
        return mock_kr

    def test_resolve_from_env_var(self):
        """Env var takes priority when set."""
        self._mock_keyring(None)
        with (
            patch("src.config.settings.DEEPSEEK_API_KEY", "env-api-key"),
            patch(
                "src.memory.user_profile.get_profile",
                return_value={"deepseek_api_key": ""},
            ),
        ):
            from src.config.secret_store import resolve_deepseek_api_key

            assert resolve_deepseek_api_key() == "env-api-key"

    def test_resolve_from_keychain(self):
        """Keychain key is used when env var is empty."""
        self._mock_keyring("keychain-key")
        with patch("src.config.settings.DEEPSEEK_API_KEY", ""):
            from src.config.secret_store import resolve_deepseek_api_key

            assert resolve_deepseek_api_key() == "keychain-key"

    def test_resolve_from_profile_fallback(self):
        """Profile is fallback when keychain and env are empty."""
        self._mock_keyring(None)
        with (
            patch("src.config.settings.DEEPSEEK_API_KEY", ""),
            patch(
                "src.memory.user_profile.get_profile",
                return_value={"deepseek_api_key": "profile-key"},
            ),
        ):
            from src.config.secret_store import resolve_deepseek_api_key

            assert resolve_deepseek_api_key() == "profile-key"

    def test_resolve_empty_when_none_configured(self):
        """Returns empty string when no key source has a key."""
        self._mock_keyring(None)
        with (
            patch("src.config.settings.DEEPSEEK_API_KEY", ""),
            patch(
                "src.memory.user_profile.get_profile",
                return_value={"deepseek_api_key": ""},
            ),
        ):
            from src.config.secret_store import resolve_deepseek_api_key

            assert resolve_deepseek_api_key() == ""

    def test_store_calls_keyring_set_password(self):
        """store_deepseek_api_key writes to Keychain."""
        mock_kr = self._mock_keyring()
        with patch("src.config.secret_store._clear_profile_key"):
            from src.config.secret_store import store_deepseek_api_key

            store_deepseek_api_key("sk-test-key-123")
            mock_kr.set_password.assert_called_once_with(
                "com.owlynn.deepseek", "deepseek_api_key", "sk-test-key-123"
            )

    def test_store_rejects_empty_key(self):
        self._mock_keyring()
        with patch("src.config.secret_store._clear_profile_key"):
            from src.config.secret_store import store_deepseek_api_key

            with pytest.raises(ValueError):
                store_deepseek_api_key("")
            with pytest.raises(ValueError):
                store_deepseek_api_key("   ")

    def test_delete_removes_from_keychain(self):
        mock_kr = self._mock_keyring()
        with patch("src.config.secret_store._clear_profile_key"):
            from src.config.secret_store import delete_deepseek_api_key

            delete_deepseek_api_key()
            mock_kr.delete_password.assert_called_once_with(
                "com.owlynn.deepseek", "deepseek_api_key"
            )

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
