"""Per-engagement credential encryption using Fernet (AES-128-CBC).

Phase 3 — Unified State Management: credential blobs are now stored in the
PentestCredentials table (PostgreSQL) instead of credentials.enc flat files.
The Fernet master key continues to be stored in macOS Keychain; only the
I/O layer has changed (file → DB row).

Usage::

    from src.config.engagement_crypto import encrypt_credentials, decrypt_credentials
    await encrypt_credentials("eng-abc123", {"users": [...]})
    creds = await decrypt_credentials("eng-abc123")
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_cached_key: bytes | None = None


def _get_master_key() -> bytes:
    """Get or create the Fernet master key from macOS Keychain."""
    global _cached_key
    if _cached_key:
        return _cached_key

    import subprocess

    from cryptography.fernet import Fernet

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
        logger.error("Failed to store master key in Keychain: %s", e)
        raise RuntimeError("Could not secure master key in macOS Keychain") from e

    _cached_key = new_key
    return new_key


def _get_fernet():
    """Get a Fernet instance with the master key."""
    from cryptography.fernet import Fernet

    return Fernet(_get_master_key())


# ---------------------------------------------------------------------------
# DB-backed encrypt / decrypt
# ---------------------------------------------------------------------------


async def encrypt_credentials(engagement_id: str, credentials: dict) -> None:
    """Encrypt and store credentials for an engagement in the DB.

    Args:
        engagement_id: The engagement ID.
        credentials: Dict of credential data (e.g., {"users": [{"username": "...", "password": "...", "note": "..."}]}).
    """
    from sqlalchemy import select

    from src.memory.db_models import PentestCredentials
    from src.models.db import AsyncSessionLocal

    fernet = _get_fernet()
    plaintext = json.dumps(credentials, ensure_ascii=False).encode("utf-8")
    ciphertext = fernet.encrypt(plaintext)

    async with AsyncSessionLocal() as session, session.begin():
        # Replace any existing credential row for this engagement.
        stmt = select(PentestCredentials).where(
            PentestCredentials.engagement_id == engagement_id
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.data = ciphertext
            session.add(existing)
        else:
            row = PentestCredentials(
                engagement_id=engagement_id,
                data=ciphertext,
            )
            session.add(row)

    logger.info("Encrypted credentials for engagement %s", engagement_id)


async def decrypt_credentials(engagement_id: str) -> dict:
    """Decrypt and return credentials for an engagement from the DB.

    Returns empty dict if no credential row exists or decryption fails.
    """
    from sqlalchemy import select

    from src.memory.db_models import PentestCredentials
    from src.models.db import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = select(PentestCredentials).where(
            PentestCredentials.engagement_id == engagement_id
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

    if row is None:
        return {}

    try:
        fernet = _get_fernet()
        plaintext = fernet.decrypt(row.data)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        logger.warning("Failed to decrypt credentials for %s: %s", engagement_id, e)
        return {}


async def add_credential(
    engagement_id: str,
    username: str,
    password: str,
    note: str = "",
) -> None:
    """Add a single credential to the engagement's encrypted store."""
    creds = await decrypt_credentials(engagement_id)
    users = creds.get("users", [])
    users.append(
        {
            "username": username,
            "password": password,
            "note": note,
        }
    )
    creds["users"] = users
    await encrypt_credentials(engagement_id, creds)


async def list_credentials(engagement_id: str) -> list[dict]:
    """List credential metadata (usernames + notes, no passwords)."""
    creds = await decrypt_credentials(engagement_id)
    return [
        {"username": u.get("username", ""), "note": u.get("note", "")}
        for u in creds.get("users", [])
    ]
