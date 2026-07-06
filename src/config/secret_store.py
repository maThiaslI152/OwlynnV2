"""
Secure API Key Storage using local environment files.

Priority chain for resolving the DeepSeek API key:

    DEEPSEEK_API_KEY env var → ~/.owlynn/secrets.env → deepseek_api_key in user profile

On first run, if a key exists in the profile JSON, it is migrated to secrets.env
and the profile field is cleared to avoid plaintext persistence in the profile.

``store_deepseek_api_key`` writes to ``~/.owlynn/secrets.env`` so that
terminal sessions can source the file.

Usage::

    from src.config.secret_store import resolve_deepseek_api_key, store_deepseek_api_key
    key = resolve_deepseek_api_key()
    store_deepseek_api_key("sk-...")
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the shell-sourceable secrets file for terminal fallback
_SECRETS_ENV_PATH = Path.home() / ".owlynn" / "secrets.env"


def resolve_deepseek_api_key() -> str:
    """Resolve the DeepSeek API key in priority order.

    Returns
    -------
    str
        The API key, or empty string if none configured.
    """
    # 1. Environment variable (includes keys set via store_deepseek_api_key in this process)
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key

    # 2. ~/.owlynn/secrets.env — shell-sourceable file written by store_deepseek_api_key
    try:
        if _SECRETS_ENV_PATH.exists():
            for line in _SECRETS_ENV_PATH.read_text(encoding="utf-8").splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    file_key = line.split("=", 1)[1].strip()
                    if file_key:
                        return file_key
    except Exception as e:
        logger.debug("Failed to read secrets.env: %s", e)

    # 3. Legacy profile file (deprecated — will be migrated on next store)
    from src.memory.user_profile import get_profile

    profile = get_profile()
    profile_key = (profile.get("deepseek_api_key") or "").strip()
    if profile_key:
        logger.warning(
            "DeepSeek API key found in user_profile.json. "
            "Call store_deepseek_api_key() to migrate to secrets.env."
        )
    return profile_key


def store_deepseek_api_key(api_key: str) -> None:
    """Store the DeepSeek API key in ~/.owlynn/secrets.env.

    Also updates ``os.environ`` immediately so the running process and future
    terminal sessions can use it.

    Parameters
    ----------
    api_key : str
        The API key to store. Must be non-empty.
    """
    if not api_key or not api_key.strip():
        raise ValueError("API key must be non-empty")

    key = api_key.strip()

    # Always update current process environment immediately
    os.environ["DEEPSEEK_API_KEY"] = key

    # Write to ~/.owlynn/secrets.env for terminal session sourcing
    _write_secrets_env(key)

    # Clear from legacy profile
    _clear_profile_key()


def delete_deepseek_api_key() -> None:
    """Remove the DeepSeek API key from secrets.env and profile."""
    _clear_profile_key()
    # Remove from env and secrets file
    os.environ.pop("DEEPSEEK_API_KEY", None)
    _write_secrets_env("")


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
        logger.warning("Error suppressed: %s", e)
        return False, str(e)


def rotate_deepseek_api_key(new_api_key: str) -> None:
    """Replace the existing DeepSeek API key with a new one.

    Logs the rotation event.

    Parameters
    ----------
    new_api_key : str
        The new API key.
    """
    store_deepseek_api_key(new_api_key)
    logger.info("DeepSeek API key rotated successfully")


# ── private helpers ──────────────────────────────────────────────


def _write_secrets_env(api_key: str) -> None:
    """Write (or clear) DEEPSEEK_API_KEY in ~/.owlynn/secrets.env.

    The file is shell-sourceable: ``source ~/.owlynn/secrets.env``.
    An empty ``api_key`` removes the line from the file.
    """
    try:
        _SECRETS_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing_lines: list[str] = []
        if _SECRETS_ENV_PATH.exists():
            existing_lines = _SECRETS_ENV_PATH.read_text(encoding="utf-8").splitlines()
        # Remove any previous DEEPSEEK_API_KEY line
        filtered = [
            ln for ln in existing_lines if not ln.startswith("DEEPSEEK_API_KEY=")
        ]
        if api_key:
            filtered.append(f"DEEPSEEK_API_KEY={api_key}")
        _SECRETS_ENV_PATH.write_text(
            "\n".join(filtered) + ("\n" if filtered else ""), encoding="utf-8"
        )
        _SECRETS_ENV_PATH.chmod(0o600)  # owner read/write only
        logger.info(
            "DeepSeek API key %s in %s",
            "written" if api_key else "removed",
            _SECRETS_ENV_PATH,
        )
    except Exception as e:
        logger.warning("Failed to update secrets.env: %s", e)


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


def _store_profile_key(api_key: str) -> None:
    """Store the deepseek_api_key in the user profile."""
    try:
        from src.memory.user_profile import get_profile, _save_profile

        profile = get_profile()
        profile["deepseek_api_key"] = api_key
        _save_profile(profile)
        logger.info("DeepSeek API key stored in user_profile.json (fallback)")
    except Exception as e:
        logger.warning("Failed to store profile key: %s", e)
