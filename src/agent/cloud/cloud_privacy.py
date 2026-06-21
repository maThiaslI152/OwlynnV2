"""Privacy helpers for cloud API calls."""

from __future__ import annotations

import hashlib


def cloud_user_fingerprint(thread_id: str | None) -> str | None:
    """
    Opaque per-installation fingerprint for DeepSeek ``user`` field.

    Avoids sending stable LangGraph thread_id verbatim to the provider.
    """
    if not thread_id:
        return None
    digest = hashlib.sha256(f"owlynn-cloud:{thread_id}".encode("utf-8")).hexdigest()
    return digest[:20]
