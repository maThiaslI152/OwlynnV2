"""
PII scrubber for long-term storage and background extraction.

Runs before Qdrant writes and the 8B extraction worker. Reuses detection
patterns from ``anonymization`` but replaces values with redaction tokens
(no round-trip mapping needed for storage).
"""

from __future__ import annotations

from src.agent.cloud.anonymization import anonymize
from src.memory.user_profile import get_profile


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
