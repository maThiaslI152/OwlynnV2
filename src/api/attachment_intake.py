"""Normalize chat file attachments for multimodal LLM intake and vision-only detection."""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import re

logger = logging.getLogger(__name__)

VISION_INTAKE_MIMES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
    }
)

VISION_FILE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".heic",
        ".heif",
    }
)

_DATA_URL_RE = re.compile(r"^data:([^;,]+)?(?:;[^,]*)?,(.+)$", re.DOTALL)


def is_vision_filename(filename: str) -> bool:
    """True when the file extension is treated as vision-only (skip RAG plaintext pipeline)."""
    ext = os.path.splitext(filename or "")[1].lower()
    return ext in VISION_FILE_EXTENSIONS


def is_vision_mime(mime: str) -> bool:
    if not mime:
        return False
    base = mime.split(";", 1)[0].strip().lower()
    if base == "image/jpg":
        base = "image/jpeg"
    return base in VISION_INTAKE_MIMES


def infer_mime_from_name(name: str) -> str:
    mime, _ = mimetypes.guess_type(name or "")
    if not mime:
        return ""
    if mime == "image/jpg":
        return "image/jpeg"
    return mime


def normalize_file_attachment(f: dict) -> dict | None:
    """Parse WS/API attachment payloads into normalized name, mime, raw base64, bytes.

    Returns None when the attachment cannot be decoded (logged at warning level).
    """
    name = (f.get("name") or "file").strip() or "file"
    explicit_type = (f.get("type") or "").strip()
    raw_data = f.get("data") or ""

    mime = explicit_type
    payload = raw_data

    if isinstance(payload, str) and payload.startswith("data:"):
        match = _DATA_URL_RE.match(payload.strip())
        if match:
            header_mime = (match.group(1) or "").strip()
            payload = match.group(2)
            if header_mime and not mime:
                mime = header_mime
        else:
            logger.warning("Invalid data URL for attachment %s", name)
            return None
    elif isinstance(payload, str) and "," in payload and not mime:
        # Legacy: data URL without data: prefix
        payload = payload.split(",", 1)[1]

    if not mime:
        mime = infer_mime_from_name(name)
    if mime == "image/jpg":
        mime = "image/jpeg"

    if not isinstance(payload, str) or not payload.strip():
        logger.warning("Empty attachment payload for %s", name)
        return None

    try:
        raw_bytes = base64.b64decode(payload, validate=False)
    except Exception as exc:
        logger.warning("Base64 decode failed for attachment %s: %s", name, exc)
        return None

    if not raw_bytes:
        logger.warning("Zero-length attachment payload for %s", name)
        return None

    return {
        "name": name,
        "type": mime,
        "data": payload.strip(),
        "raw_bytes": raw_bytes,
    }
