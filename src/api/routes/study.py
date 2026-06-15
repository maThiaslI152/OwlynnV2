"""Study personal assistant API routes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

from src.config.settings import DATA_DIR
from src.tools.todo import _load_todos

router = APIRouter()

_COURSES_PATH = DATA_DIR / "courses.json"
_FLASHCARDS_DIR = DATA_DIR / "flashcards"


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


@router.get("/api/courses")
async def list_courses():
    courses = _read_json(_COURSES_PATH, [])
    return {"status": "ok", "courses": courses}


@router.get("/api/flashcards")
async def list_flashcard_decks():
    decks = []
    if _FLASHCARDS_DIR.is_dir():
        for path in sorted(_FLASHCARDS_DIR.glob("*.json")):
            deck = _read_json(path, {})
            cards = deck.get("cards") or []
            decks.append(
                {
                    "deck_id": deck.get("deck_id") or path.stem,
                    "name": deck.get("name") or path.stem,
                    "course_id": deck.get("course_id"),
                    "card_count": len(cards),
                }
            )
    return {"status": "ok", "decks": decks}


@router.get("/api/study/dashboard")
async def study_dashboard():
    """Aggregate courses, upcoming exams, course todos, and deck counts."""
    courses = _read_json(_COURSES_PATH, [])
    todos = _load_todos()
    pending = [t for t in todos if t.get("status") == "pending"]
    today = datetime.now().date().isoformat()

    upcoming_exams = []
    for c in courses:
        exam = c.get("exam_date")
        if exam and exam >= today:
            days = (datetime.fromisoformat(exam).date() - datetime.now().date()).days
            upcoming_exams.append(
                {
                    "course_id": c.get("course_id"),
                    "name": c.get("name"),
                    "exam_date": exam,
                    "days_until": days,
                }
            )
    upcoming_exams.sort(key=lambda x: x["exam_date"])

    course_todos = [
        {
            "id": t.get("id"),
            "task": t.get("task"),
            "course_id": t.get("course_id"),
            "due_date": t.get("due_date"),
            "priority": t.get("priority"),
        }
        for t in pending
        if t.get("course_id") or t.get("due_date")
    ][:20]

    decks_resp = await list_flashcard_decks()

    return {
        "status": "ok",
        "courses": courses,
        "upcoming_exams": upcoming_exams[:5],
        "course_todos": course_todos,
        "flashcard_decks": decks_resp.get("decks", []),
    }
