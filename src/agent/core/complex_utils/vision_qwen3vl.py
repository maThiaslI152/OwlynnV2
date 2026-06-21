"""Parse Qwen3-VL natural-language vision output into the shared vision payload schema."""

from __future__ import annotations

import json
from typing import Any

from src.agent.core.complex_utils.vision_schema import normalize_vision_payload


def parse_qwen3vl_response(raw: str) -> dict[str, Any] | None:
    """
    Convert Qwen3-VL natural-language output to normalized vision payload dict.

    Qwen3-VL is prompted to describe visible text, UI elements, and structure.
    This parser extracts structured content from its prose response.

    Handles: plain text descriptions and JSON-structured outputs.
    """
    text = (raw or "").strip()
    if not text:
        return None

    # Try JSON first (some Qwen3-VL variants output structured JSON)
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return normalize_vision_payload(data)
        except json.JSONDecodeError:
            pass

    # Natural language prose — extract structured content
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None

    text_blocks = []
    ui_elements = []
    subjects = _infer_subjects(text)

    for line in lines:
        # Detect UI element mentions
        ui_label = _extract_ui_element(line)
        if ui_label:
            role, label = ui_label
            ui_elements.append({"role": role, "label": label})
            # Also add to text_blocks if has useful text
            if label and len(label) > 1:
                text_blocks.append({"text": label, "bbox": None})
        else:
            text_blocks.append({"text": line, "bbox": None})

    # Deduplicate text blocks preserving order
    seen = set()
    deduped = []
    for block in text_blocks:
        t = block["text"].strip()
        if t and t not in seen:
            seen.add(t)
            deduped.append({"text": t, "bbox": block.get("bbox")})

    if not deduped:
        return None

    return normalize_vision_payload(
        {
            "text_blocks": deduped,
            "ui_elements": ui_elements[:20],
            "subjects": subjects,
            "confidence": 0.75,
        }
    )


_UI_PATTERNS = {
    "button": ("button", "btn", "click"),
    "field": ("text field", "input", "textbox", "text box"),
    "heading": ("heading", "title", "header"),
    "menu": ("menu", "dropdown", "select"),
    "link": ("link", "hyperlink", "url"),
    "code": ("code block", "syntax", "function"),
    "terminal": ("terminal", "console", "command line"),
}


def _extract_ui_element(line: str) -> tuple[str, str] | None:
    """Extract UI element role and label from a description line."""
    lower = line.lower()
    for role, keywords in _UI_PATTERNS.items():
        for kw in keywords:
            if kw in lower:
                return (role, line.strip())
    return None


_SUBJECT_TOKENS = (
    ("terminal", "terminal"),
    ("console", "terminal"),
    ("command line", "terminal"),
    ("error", "error"),
    ("http", "web"),
    ("url", "web"),
    ("button", "ui"),
    ("form", "form"),
    ("chart", "diagram"),
    ("graph", "diagram"),
    ("table", "table"),
    ("code", "code"),
    ("screenshot", "screenshot"),
    ("photo", "photo"),
    ("document", "document"),
    ("spreadsheet", "spreadsheet"),
    ("browser", "browser"),
    ("desktop", "desktop"),
    ("window", "ui"),
    ("dialog", "ui"),
    ("menu", "ui"),
    ("toolbar", "ui"),
)


def _infer_subjects(text: str) -> list[str]:
    """Heuristic subject tags from vision VLM output."""
    lower = text.lower()
    tags: list[str] = []
    for token, tag in _SUBJECT_TOKENS:
        if token in lower and tag not in tags:
            tags.append(tag)
    return tags[:5] or ["image"]
