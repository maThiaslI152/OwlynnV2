"""Parse Florence-2 task-token OCR output into the shared vision payload schema."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from src.agent.nodes.complex_utils.vision_schema import normalize_vision_payload


def parse_florence_response(raw: str) -> dict[str, Any] | None:
    """
    Convert Florence-2 LM output to normalized vision payload dict.

    Handles plain OCR text, dict-like strings, and JSON fallbacks.
    """
    text = (raw or "").strip()
    if not text:
        return None

    # Try JSON first (some wrappers emit JSON)
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return _from_florence_dict(data)
        except json.JSONDecodeError:
            pass

    # Python dict literal from LM Studio / Florence post-process
    if text.startswith("{"):
        try:
            data = ast.literal_eval(text)
            if isinstance(data, dict):
                return _from_florence_dict(data)
        except (SyntaxError, ValueError):
            pass

    # Plain OCR prose
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    return normalize_vision_payload(
        {
            "text_blocks": [{"text": ln, "bbox": None} for ln in lines],
            "ui_elements": [],
            "subjects": _infer_subjects(text),
            "confidence": 0.75,
        }
    )


def _from_florence_dict(data: dict[str, Any]) -> dict[str, Any] | None:
    """Map Florence task keys to normalized payload."""
    if "<OCR_WITH_REGION>" in data:
        region = data["<OCR_WITH_REGION>"]
        return _from_ocr_with_region(region)
    if "<OCR>" in data:
        ocr = data["<OCR>"]
        if isinstance(ocr, str) and ocr.strip():
            return normalize_vision_payload(
                {
                    "text_blocks": [{"text": ocr.strip(), "bbox": None}],
                    "ui_elements": [],
                    "subjects": _infer_subjects(ocr),
                    "confidence": 0.85,
                }
            )
    # Already in our schema
    if "text_blocks" in data:
        return normalize_vision_payload(data)
    return None


def _from_ocr_with_region(region: Any) -> dict[str, Any] | None:
    if isinstance(region, str):
        return parse_florence_response(region)
    if not isinstance(region, dict):
        return None

    labels = region.get("labels") or []
    text_blocks = []
    ui_elements = []
    if isinstance(labels, list):
        for item in labels:
            if isinstance(item, str) and item.strip():
                text_blocks.append({"text": item.strip(), "bbox": None})
            elif isinstance(item, dict):
                label = str(item.get("text") or item.get("label") or "").strip()
                if label:
                    text_blocks.append({"text": label, "bbox": item.get("bbox")})
                    ui_elements.append(
                        {"role": "other", "label": label},
                    )

    quad_boxes = region.get("quad_boxes") or []
    if isinstance(quad_boxes, list) and labels and len(labels) == len(quad_boxes):
        for i, label in enumerate(labels):
            if isinstance(label, str) and label.strip():
                if i < len(text_blocks):
                    text_blocks[i]["bbox"] = quad_boxes[i]

    if not text_blocks and isinstance(region.get("text"), str):
        text_blocks.append({"text": region["text"].strip(), "bbox": None})

    if not text_blocks:
        return None

    joined = " ".join(str(b["text"]) for b in text_blocks if b.get("text"))
    return normalize_vision_payload(
        {
            "text_blocks": text_blocks,
            "ui_elements": ui_elements[:20],
            "subjects": _infer_subjects(joined),
            "confidence": 0.9,
        }
    )


def _infer_subjects(text: str) -> list[str]:
    """Heuristic subject tags from OCR text."""
    lower = text.lower()
    tags: list[str] = []
    for token, tag in (
        ("terminal", "terminal"),
        ("error", "error"),
        ("http", "web"),
        ("button", "ui"),
        ("form", "form"),
        ("chart", "diagram"),
        ("code", "code"),
    ):
        if token in lower and tag not in tags:
            tags.append(tag)
    return tags[:5] or ["image"]
