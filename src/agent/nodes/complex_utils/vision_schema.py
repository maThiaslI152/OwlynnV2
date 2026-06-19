"""Structured vision proxy output — OCR/layout JSON for cloud path."""

from __future__ import annotations

import json
import re
from typing import Any

VISION_OCR_SYSTEM = """You are an OCR sensor. Output ALL visible text exactly as it appears — transcribe every word, number, symbol, and code snippet verbatim. Then list any UI elements (buttons, fields, menus). Do NOT describe the image, do NOT add interpretation, do NOT say 'the image shows' — output raw transcription only."""

VISION_OCR_USER = "Extract the exact text from this image. List all visible text, UI elements (buttons, fields, menus), and code verbatim."

# Legacy Florence-2 task tokens (kept for florence mode backward compat)
VISION_FLORENCE_OCR_TASK = "<OCR>"
VISION_FLORENCE_CAPTION_TASK = "<DETAILED_CAPTION>"


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_vision_payload(raw: str) -> dict[str, Any] | None:
    """Parse VLM JSON output; return normalized dict or None."""
    text = _strip_fences(raw)
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return normalize_vision_payload(data)


def normalize_vision_payload(data: dict[str, Any]) -> dict[str, Any]:
    text_blocks = []
    for item in data.get("text_blocks") or []:
        if not isinstance(item, dict):
            continue
        t = str(item.get("text", "")).strip()
        if t:
            text_blocks.append({"text": t, "bbox": item.get("bbox")})

    ui_elements = []
    for item in data.get("ui_elements") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if label:
            ui_elements.append(
                {
                    "role": str(item.get("role", "other")),
                    "label": label,
                }
            )

    subjects = [str(s).strip() for s in (data.get("subjects") or []) if str(s).strip()][
        :8
    ]

    try:
        confidence = float(data.get("confidence", 0.8))
    except (TypeError, ValueError):
        confidence = 0.8
    confidence = max(0.0, min(1.0, confidence))

    return {
        "text_blocks": text_blocks,
        "ui_elements": ui_elements,
        "subjects": subjects,
        "confidence": confidence,
    }


def format_vision_for_cloud(payload: dict[str, Any]) -> str:
    """Dense block injected into cloud prompt."""
    lines = ["[Image content transcribed by vision sensor]"]
    if payload.get("subjects"):
        lines.append(f"Subjects: {', '.join(payload['subjects'])}")
    for block in payload.get("text_blocks") or []:
        lines.append(f"Visible text: {block['text']}")
    for el in payload.get("ui_elements") or []:
        lines.append(f"UI {el.get('role', 'other')}: {el.get('label', '')}")
    conf = payload.get("confidence")
    if conf is not None:
        lines.append(f"confidence={conf}")
    return "\n".join(lines)
