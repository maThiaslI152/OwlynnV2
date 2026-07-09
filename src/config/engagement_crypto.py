"""Per-engagement credential encryption using Fernet (AES-128-CBC).

Master key is stored in ~/.owlynn/.engagement_master_key.
Credentials are encrypted per-engagement and stored in credentials.enc files.

Usage::

    from src.config.engagement_crypto import encrypt_credentials, decrypt_credentials
    encrypt_credentials("eng-abc123", {"user": "admin", "pass": "secret"})
    creds = decrypt_credentials("eng-abc123")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config.settings import DATA_DIR

logger = logging.getLogger(__name__)

_cached_key: bytes | None = None


def _get_master_key() -> bytes:
    """Get or create the Fernet master key from macOS Keychain."""
    global _cached_key
    if _cached_key:
        return _cached_key

    from cryptography.fernet import Fernet
    import subprocess

    service = "OwlynnPentest"
    account = "MasterKey"

    # Try reading from Keychain
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True,
            text=True,
            check=True,
        )
        key_str = result.stdout.strip()
        if key_str:
            _cached_key = key_str.encode("utf-8")
            return _cached_key
    except subprocess.CalledProcessError:
        logger.info(
            "Engagement master key not found in Keychain. Generating a new one."
        )

    # Generate new key
    new_key = Fernet.generate_key()

    # Store securely in Keychain
    try:
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",
                new_key.decode("utf-8"),
                "-U",  # Update if exists
            ],
            check=True,
            capture_output=True,
        )
        logger.info("Successfully stored new engagement master key in macOS Keychain.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to store master key in Keychain: {e}")
        raise RuntimeError("Could not secure master key in macOS Keychain") from e

    _cached_key = new_key
    return new_key


def _get_fernet():
    """Get a Fernet instance with the master key."""
    from cryptography.fernet import Fernet

    return Fernet(_get_master_key())


def _credentials_path(engagement_id: str) -> Path:
    return DATA_DIR / "pentest_engagements" / engagement_id / "credentials.enc"


def encrypt_credentials(engagement_id: str, credentials: dict) -> None:
    """Encrypt and store credentials for an engagement.

    Args:
        engagement_id: The engagement ID.
        credentials: Dict of credential data (e.g., {"users": [{"username": "...", "password": "...", "note": "..."}]}).
    """
    fernet = _get_fernet()
    plaintext = json.dumps(credentials, ensure_ascii=False).encode("utf-8")
    ciphertext = fernet.encrypt(plaintext)

    path = _credentials_path(engagement_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ciphertext)
    logger.info("Encrypted credentials for engagement %s", engagement_id)


def decrypt_credentials(engagement_id: str) -> dict:
    """Decrypt and return credentials for an engagement.

    Returns empty dict if no credentials file exists or decryption fails.
    """
    path = _credentials_path(engagement_id)
    if not path.exists():
        return {}

    try:
        fernet = _get_fernet()
        ciphertext = path.read_bytes()
        plaintext = fernet.decrypt(ciphertext)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        logger.warning("Failed to decrypt credentials for %s: %s", engagement_id, e)
        return {}


def add_credential(
    engagement_id: str,
    username: str,
    password: str,
    note: str = "",
) -> None:
    """Add a single credential to the engagement's encrypted store."""
    creds = decrypt_credentials(engagement_id)
    users = creds.get("users", [])
    users.append(
        {
            "username": username,
            "password": password,
            "note": note,
        }
    )
    creds["users"] = users
    encrypt_credentials(engagement_id, creds)


def list_credentials(engagement_id: str) -> list[dict]:
    """List credential metadata (usernames + notes, no passwords)."""
    creds = decrypt_credentials(engagement_id)
    return [
        {"username": u.get("username", ""), "note": u.get("note", "")}
        for u in creds.get("users", [])
    ]
