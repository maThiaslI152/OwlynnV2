"""JSON schema validation for L1 memory atoms."""

from __future__ import annotations

import json
import re
from typing import Any

ALLOWED_FORMATS = frozenset({"json", "jsdoc", "docstring"})
ALLOWED_TIERS = frozenset({"L0", "L1"})


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_extraction_response(raw: str) -> list[dict[str, Any]]:
    """Parse and validate extractor LLM output into atom dicts."""
    text = _strip_fences(raw)
    if not text:
        return []

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    if isinstance(payload, dict) and "atoms" in payload:
        items = payload["atoms"]
    elif isinstance(payload, list):
        items = payload
    else:
        return []

    valid: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        atom = validate_atom(item)
        if atom:
            valid.append(atom)
    return valid


def validate_atom(item: dict[str, Any]) -> dict[str, Any] | None:
    """Return normalized atom or None if invalid."""
    tier = str(item.get("tier", "L1")).upper()
    if tier not in ALLOWED_TIERS:
        tier = "L1"

    fmt = str(item.get("format", "jsdoc")).lower()
    if fmt not in ALLOWED_FORMATS:
        fmt = "jsdoc"

    content = str(item.get("content", "")).strip()
    if len(content) < 8:
        return None

    tags = item.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags if str(t).strip()][:12]

    try:
        confidence = float(item.get("confidence", 0.8))
    except (TypeError, ValueError):
        confidence = 0.8
    confidence = max(0.0, min(1.0, confidence))

    return {
        "tier": tier,
        "format": fmt,
        "content": content,
        "tags": tags,
        "confidence": confidence,
        "source": str(item.get("source", "conversation")),
    }
