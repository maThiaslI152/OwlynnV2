"""Interactive inline chat blocks — validate payloads and emit fenced markdown."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

from jsonschema import Draft7Validator
from langchain_core.tools import tool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = PROJECT_ROOT / "templates" / "interactive"

BLOCK_LANG: dict[str, str] = {
    "quiz": "owlynn-quiz",
    "steps": "owlynn-steps",
    "callout": "owlynn-callout",
    "embed": "owlynn-embed",
    "cell": "owlynn-cell",
}


def _load_schema(block_type: str) -> dict:
    path = TEMPLATES_DIR / f"{block_type}.schema.json"
    if not path.is_file():
        raise ValueError(
            f"Unknown block_type '{block_type}'. Supported: {', '.join(BLOCK_LANG)}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_payload(block_type: str, payload: dict) -> list[str]:
    schema = _load_schema(block_type)
    validator = Draft7Validator(schema)
    return [
        e.message for e in sorted(validator.iter_errors(payload), key=lambda e: e.path)
    ]


def format_interactive_fence(block_type: str, payload: dict) -> str:
    """Return fenced markdown for an interactive block."""
    errors = _validate_payload(block_type, payload)
    if errors:
        raise ValueError("; ".join(errors))
    lang = BLOCK_LANG[block_type]
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"```{lang}\n{body}\n```"


def _persist_artifact(project_id: str, block_type: str, payload: dict) -> str:
    from src.config.settings import get_project_workspace

    ws = Path(get_project_workspace(project_id))
    art_dir = ws / ".artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    artifact_id = uuid.uuid4().hex[:12]
    record = {
        "id": artifact_id,
        "block_type": block_type,
        "payload": payload,
    }
    (art_dir / f"{artifact_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return artifact_id


@tool
def render_interactive_block(block_type: str, payload: dict) -> str:
    """
    Validate an interactive block payload and return fenced markdown for the assistant reply.

    block_type: quiz | steps | callout | embed | cell
    payload: JSON object matching the block schema (see templates/interactive/).

    Include the returned fence verbatim in your final message. Keep surrounding prose brief.

    For ``cell`` blocks, ``runnable`` defaults to false (display-only). Only set
    ``runnable: true`` when the user explicitly asked to run code interactively.
    """
    if not isinstance(payload, dict):
        return "Error: payload must be a JSON object."

    try:
        block = block_type.strip().lower()
        payload = dict(payload)
        if block == "cell":
            payload.setdefault("runnable", False)
        fence = format_interactive_fence(block, payload)
    except ValueError as exc:
        return f"Error: {exc}"

    try:
        from src.tools.workspace_context import get_active_project_id

        project_id = get_active_project_id() or "default"
        _persist_artifact(project_id, block_type.strip().lower(), payload)
    except Exception:
        logger.warning("Failed to persist interactive artifact", exc_info=True)

    return (
        "Interactive block ready — include this fence verbatim in your reply:\n\n"
        f"{fence}\n\n"
        "Add 1–2 sentences of context before or after the block; do not duplicate the JSON in prose."
    )
