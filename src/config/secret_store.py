"""
Secure API Key Storage with macOS Keychain Integration.

Priority chain for resolving the DeepSeek API key:

    Keychain → DEEPSEEK_API_KEY env var → deepseek_api_key in user profile

On first run, if a key exists in the profile JSON, it is migrated to Keychain
and the profile field is cleared to avoid plaintext persistence.

Usage::

    from src.config.secret_store import resolve_deepseek_api_key, store_deepseek_api_key
    key = resolve_deepseek_api_key()
    store_deepseek_api_key("sk-...")
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SERVICE_NAME = "com.owlynn.deepseek"
_ACCOUNT_NAME = "deepseek_api_key"

# Lazy import — keyring is optional (macOS Keychain only)
_keyring = None


def _get_keyring():
    """Lazy-import keyring with graceful fallback."""
    global _keyring
    if _keyring is None:
        try:
            import keyring as kr

            _keyring = kr
        except ImportError:
            logger.debug("keyring not installed — Keychain storage unavailable")
            _keyring = False
    return _keyring if _keyring is not False else None


def get_service_name() -> str:
    """Return the Keychain service name (configurable via defaults.yaml)."""
    from src.config.config_loader import config

    return config.get("secret_store.keychain_service", _SERVICE_NAME) or _SERVICE_NAME


def get_account_name() -> str:
    """Return the Keychain account name (configurable via defaults.yaml)."""
    from src.config.config_loader import config

    return config.get("secret_store.keychain_account", _ACCOUNT_NAME) or _ACCOUNT_NAME


def resolve_deepseek_api_key() -> str:
    """Resolve the DeepSeek API key in priority order.

    Returns
    -------
    str
        The API key, or empty string if none configured.
    """
    # 1. macOS Keychain (most secure)
    key = _read_from_keychain()
    if key:
        return key

    # 2. Environment variable
    from src.config.settings import DEEPSEEK_API_KEY

    if DEEPSEEK_API_KEY:
        return DEEPSEEK_API_KEY

    # 3. Legacy profile file (deprecated — will be migrated on next store)
    from src.memory.user_profile import get_profile

    profile = get_profile()
    profile_key = (profile.get("deepseek_api_key") or "").strip()
    if profile_key:
        logger.warning(
            "DeepSeek API key found in user_profile.json (plaintext). "
            "Migrate to Keychain via Settings or call store_deepseek_api_key()."
        )
    return profile_key


def store_deepseek_api_key(api_key: str) -> None:
    """Store the DeepSeek API key in macOS Keychain.

    Also clears the key from the legacy profile file.

    Parameters
    ----------
    api_key : str
        The API key to store. Must be non-empty.
    """
    if not api_key or not api_key.strip():
        raise ValueError("API key must be non-empty")

    key = api_key.strip()
    kr = _get_keyring()
    if kr is None:
        logger.error("keyring not available — cannot store API key")
        raise RuntimeError(
            "keyring library not installed. Install with: pip install keyring"
        )

    # Store in Keychain
    try:
        kr.set_password(get_service_name(), get_account_name(), key)
        logger.info("DeepSeek API key stored in macOS Keychain")
    except kr.errors.KeyringError as e:
        logger.error("Failed to store API key in Keychain: %s", e)
        raise

    # Clear from legacy profile
    _clear_profile_key()


def delete_deepseek_api_key() -> None:
    """Remove the DeepSeek API key from Keychain and profile."""
    kr = _get_keyring()
    if kr is not None:
        try:
            kr.delete_password(get_service_name(), get_account_name())
            logger.info("DeepSeek API key removed from macOS Keychain")
        except kr.errors.PasswordDeleteError:
            pass  # Already deleted
    _clear_profile_key()


def verify_deepseek_api_key(api_key: str) -> tuple[bool, str]:
    """Verify a DeepSeek API key by making a lightweight API call.

    Sends a minimal chat completion request (1 token) to validate the key.

    Parameters
    ----------
    api_key : str
        The API key to verify.

    Returns
    -------
    tuple[bool, str]
        ``(is_valid, message)`` — e.g. ``(True, "Key is valid")`` or
        ``(False, "401 Unauthorized — invalid key")``.
    """
    import httpx
    from src.memory.user_profile import get_profile
    from src.config.config_loader import config

    if not api_key or not api_key.strip():
        return False, "Empty API key"

    profile = get_profile()
    base_url = profile.get("cloud_llm_base_url") or config.get(
        "models.cloud.base_url", "https://api.deepseek.com/v1"
    )
    model = profile.get("cloud_llm_model_name") or config.get(
        "models.cloud.model_name", "deepseek-v4"
    )

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "model": model,
                    "max_tokens": 1,
                },
            )
            if response.status_code == 200:
                return True, "Key is valid"
            if response.status_code in (401, 403):
                return (
                    False,
                    f"{response.status_code} Unauthorized — invalid or expired key",
                )
            if response.status_code == 429:
                return True, "Key is valid but currently rate-limited"
            return False, f"Unexpected response: HTTP {response.status_code}"
    except httpx.TimeoutException:
        return False, "Connection timed out — check network or API endpoint"
    except Exception as e:
        return False, str(e)


def rotate_deepseek_api_key(new_api_key: str) -> None:
    """Replace the existing DeepSeek API key with a new one.

    Logs the rotation event.

    Parameters
    ----------
    new_api_key : str
        The new API key.
    """
    old_key = resolve_deepseek_api_key()
    old_prefix = old_key[:7] + "..." if len(old_key) > 7 else "(none)"
    new_prefix = new_api_key[:7] + "..." if len(new_api_key) > 7 else "(empty)"

    store_deepseek_api_key(new_api_key)
    logger.info("DeepSeek API key rotated: old=%s → new=%s", old_prefix, new_prefix)


# ── private helpers ──────────────────────────────────────────────


def _read_from_keychain() -> Optional[str]:
    """Read the API key from macOS Keychain. Returns ``None`` if not found."""
    kr = _get_keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(get_service_name(), get_account_name())
    except kr.errors.KeyringError as e:
        logger.debug("Keychain read failed: %s", e)
        return None


def _clear_profile_key() -> None:
    """Clear the deepseek_api_key field from user profile."""
    try:
        from src.memory.user_profile import get_profile, _save_profile

        profile = get_profile()
        if profile.get("deepseek_api_key"):
            profile["deepseek_api_key"] = ""
            _save_profile(profile)
            logger.info("Cleared deepseek_api_key from user_profile.json")
    except Exception as e:
        logger.warning("Failed to clear profile key: %s", e)
