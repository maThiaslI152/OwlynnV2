"""Compress retrieved memory atoms into dense docstrings for cloud brief injection."""

from __future__ import annotations

import re


def compress_memory_for_cloud(
    memory_context: str | None,
    knowledge_context: str | None = None,
    *,
    max_chars: int = 800,
) -> str:
    """Produce a token-efficient memory block for DeepSeek cloud brief."""
    chunks: list[str] = []
    for block in (memory_context, knowledge_context):
        if not block or not str(block).strip():
            continue
        chunks.append(_condense_block(str(block)))

    if not chunks:
        return ""

    merged = "\n".join(chunks)
    merged = re.sub(r"\n{3,}", "\n", merged).strip()
    if len(merged) > max_chars:
        merged = merged[: max_chars - 3].rstrip() + "..."
    return f'"""Memory context (compressed):\n{merged}\n"""'


def _condense_block(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s*", "", line)
        line = re.sub(r"\s+", " ", line)
        if line.lower() in {"none", "n/a"}:
            continue
        lines.append(line)
    return "\n".join(lines[:24])
