"""
PII scrubber for long-term storage and background extraction.

Runs before Qdrant writes and the 8B extraction worker. Reuses detection
patterns from ``anonymization`` but replaces values with redaction tokens
(no round-trip mapping needed for storage).
"""

from __future__ import annotations

import re

from src.agent.cloud.anonymization import anonymize
from src.memory.user_profile import get_profile

# Common prompt injection patterns that could manipulate future LLM behavior
_INJECTION_PATTERNS = [
    re.compile(
        r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|prompts|rules|context)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:you\s+are\s+now|from\s+now\s+on|new\s+instructions?|system\s*(?:prompt|override|message))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:act\s+as|pretend\s+to\s+be|roleplay\s+as|you\s+must\s+always|never\s+reveal)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\]\]|-->|</?(?:system|assistant|user|instruction|context))",
        re.IGNORECASE,
    ),
]


def _neutralize_injection(text: str) -> tuple[str, bool]:
    """Detect and neutralize prompt injection patterns in memory-stored text.

    Returns ``(neutralized_text, was_neutralized)``.
    Wraps matching segments in [REDACTED: potential instruction override] to
    preserve readability while preventing the text from being interpreted as
    instructions when retrieved and injected into a future system prompt.
    """
    if not text:
        return text, False

    neutralized = text
    found = False
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(neutralized):
            neutralized = pattern.sub(
                "[REDACTED: potential instruction override]", neutralized
            )
            found = True

    return neutralized, found


def scrub_for_storage(
    text: str, *, extra_terms: list[str] | None = None
) -> tuple[str, int]:
    """Scrub PII/sensitive patterns before LTM persistence.

    Returns ``(scrubbed_text, redaction_count)``.
    """
    if not text or not text.strip():
        return ("", 0)

    try:
        profile = get_profile()
        name = (profile.get("name") or "").strip()
        custom = list(profile.get("custom_sensitive_terms") or [])
    except Exception:
        name = ""
        custom = []

    if extra_terms:
        custom.extend(extra_terms)

    context = {"name": name, "custom_sensitive_terms": custom}
    scrubbed, mapping = anonymize(text, context)
    return scrubbed, len(mapping)


def scrub_for_memory_write(text: str) -> tuple[str, int, bool]:
    """Full scrub pipeline for memory writes: PII + prompt injection neutralization.

    Returns ``(scrubbed_text, pii_redaction_count, injection_neutralized)``.
    """
    scrubbed, pii_count = scrub_for_storage(text)
    clean, injection_found = _neutralize_injection(scrubbed)
    return clean, pii_count, injection_found
