"""
Persona Manager — Dynamic Agent Personas & Tone Profiles
======================================================

Manages built-in and custom agent personalities, allowing the user to select
tailored system behaviors, custom instructions, and restricted toolboxes.
"""

import os
import json
import logging
from src.config.settings import DATA_DIR

logger = logging.getLogger(__name__)

PERSONAS_DIR = DATA_DIR / "personas"
PERSONAS_DIR.mkdir(parents=True, exist_ok=True)

# ── Built-In Personas ────────────────────────────────────────────────
BUILTIN_PERSONAS = {
    "default": {
        "id": "default",
        "name": "Owlynn",
        "role": "General Workspace Assistant",
        "tone": "friendly, encouraging, and clear",
        "instructions": "Help the user with coding, research, and data analysis tasks.",
        "allowed_toolboxes": ["all"],
    },
    "coder": {
        "id": "coder",
        "name": "Owlynn Coder",
        "role": "Expert Software Engineering Lead",
        "tone": "precise, technical, and dry",
        "instructions": "Write clean, idiomatic code. Enforce robust error handling, test coverage, and documentation. Focus tools on python sandboxes and file operations.",
        "allowed_toolboxes": ["file_ops", "data_viz", "memory"],
    },
    "writer": {
        "id": "writer",
        "name": "Owlynn Editor",
        "role": "Creative Director and Writing Coach",
        "tone": "literary, articulate, and supportive",
        "instructions": "Help the user draft, refine, and polish emails, reports, and stories. Improve clarity and flow without altering the core voice.",
        "allowed_toolboxes": ["productivity", "memory"],
    },
    "researcher": {
        "id": "researcher",
        "name": "Owlynn Research",
        "role": "Academic Investigator and Fact-Checker",
        "tone": "objective, analytical, and structured",
        "instructions": "Conduct deep investigations. Always synthesize multiple sources, cite URL references cleanly, and outline pros/cons explicitly.",
        "allowed_toolboxes": ["web_search", "memory", "file_ops"],
    },
    "learning": {
        "id": "learning",
        "name": "Owlynn Tutor",
        "role": "Learning and Study Guide",
        "tone": "educational, Socratic, and patient",
        "instructions": "Act as a tutor. Do not just provide answers. Guide the user through problems, ask Socratic questions, and help them understand the material deeply.",
        "allowed_toolboxes": ["study_tools", "memory", "web_search"],
    },
}


def get_persona_by_id(persona_id: str | None) -> dict:
    """Retrieve a persona profile by its ID (checking custom files first, then built-ins)."""
    pid = (persona_id or "").strip().lower()
    if not pid or pid == "none":
        pid = "default"

    # Check custom folder first
    custom_path = PERSONAS_DIR / f"{pid}.json"
    if custom_path.exists():
        try:
            return json.loads(custom_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to read custom persona %s: %s", pid, e)

    # Check built-ins
    if pid in BUILTIN_PERSONAS:
        return BUILTIN_PERSONAS[pid].copy()

    # Fallback to default
    return BUILTIN_PERSONAS["default"].copy()


def list_personas() -> list[dict]:
    """List all available personas (built-ins + custom files)."""
    all_personas = list(BUILTIN_PERSONAS.values())
    seen_ids = {p["id"] for p in all_personas}

    try:
        for filename in os.listdir(PERSONAS_DIR):
            if filename.endswith(".json"):
                pid = filename[:-5]
                if pid not in seen_ids:
                    p = get_persona_by_id(pid)
                    all_personas.append(p)
                    seen_ids.add(pid)
    except Exception as e:
        logger.error("Error reading custom personas directory: %s", e)

    return all_personas


def save_custom_persona(persona: dict) -> bool:
    """Save a new custom persona definition to disk."""
    pid = persona.get("id", "").strip().lower()
    if not pid or pid in BUILTIN_PERSONAS:
        logger.warning("Cannot overwrite built-in persona: %s", pid)
        return False

    try:
        path = PERSONAS_DIR / f"{pid}.json"
        path.write_text(
            json.dumps(persona, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return True
    except Exception as e:
        logger.error("Failed to save custom persona: %s", e)
        return False
