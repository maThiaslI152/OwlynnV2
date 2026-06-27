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
_PROGRESS_PATH = DATA_DIR / "study_progress.json"
_QUIZ_DIR = DATA_DIR / "quiz_sessions"


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
            now = datetime.now().isoformat(timespec="seconds")
            due_count = sum(1 for c in cards if not c.get("due") or c.get("due") <= now)
            decks.append(
                {
                    "deck_id": deck.get("deck_id") or path.stem,
                    "name": deck.get("name") or path.stem,
                    "course_id": deck.get("course_id"),
                    "card_count": len(cards),
                    "due_cards": due_count,
                }
            )
    return {"status": "ok", "decks": decks}


@router.get("/api/study/exam-countdown")
async def exam_countdown():
    """Upcoming exams with study progress and remaining todos."""
    courses = _read_json(_COURSES_PATH, [])
    todos = _load_todos()
    progress = _read_json(_PROGRESS_PATH, {"sessions": [], "streaks": {}})
    today = datetime.now().date().isoformat()

    exams = []
    for c in courses:
        exam = c.get("exam_date")
        if not exam or exam < today:
            continue
        days = (datetime.fromisoformat(exam).date() - datetime.now().date()).days
        cid = c.get("course_id")

        # Count pending todos for this course
        pending_todos = sum(
            1
            for t in todos
            if t.get("course_id") == cid and t.get("status") == "pending"
        )

        # Get streak info
        streak = progress.get("streaks", {}).get(cid, {})

        # Count flashcard decks for this course
        deck_count = 0
        total_cards = 0
        due_cards = 0
        if _FLASHCARDS_DIR.is_dir():
            now = datetime.now().isoformat(timespec="seconds")
            for path in _FLASHCARDS_DIR.glob("*.json"):
                deck = _read_json(path, {})
                if deck.get("course_id") == cid:
                    deck_count += 1
                    cards = deck.get("cards") or []
                    total_cards += len(cards)
                    due_cards += sum(
                        1
                        for card in cards
                        if not card.get("due") or card.get("due") <= now
                    )

        exams.append(
            {
                "course_id": cid,
                "name": c.get("name"),
                "exam_date": exam,
                "days_until": days,
                "pending_todos": pending_todos,
                "current_streak": streak.get("current", 0),
                "flashcard_decks": deck_count,
                "total_cards": total_cards,
                "due_cards": due_cards,
                "project_id": c.get("project_id"),
            }
        )

    exams.sort(key=lambda x: x["exam_date"])
    return {"status": "ok", "exams": exams}


@router.get("/api/study/dashboard")
async def study_dashboard():
    """Aggregate courses, upcoming exams, course todos, deck counts, and progress."""
    courses = _read_json(_COURSES_PATH, [])
    todos = _load_todos()
    progress = _read_json(_PROGRESS_PATH, {"sessions": [], "streaks": {}})
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
    decks = decks_resp.get("decks", [])

    # Course progress aggregation
    sessions = progress.get("sessions", [])
    streaks = progress.get("streaks", {})
    course_progress = []
    for c in courses:
        cid = c.get("course_id")
        c_sessions = [s for s in sessions if s.get("course_id") == cid]
        c_decks = [d for d in decks if d.get("course_id") == cid]
        total_cards = sum(d.get("card_count", 0) for d in c_decks)
        due_cards = sum(d.get("due_cards", 0) for d in c_decks)
        quiz_sessions = [s for s in c_sessions if s.get("type") == "quiz"]
        avg_score = (
            sum(s.get("score", 0) for s in quiz_sessions) / len(quiz_sessions)
            if quiz_sessions
            else 0.0
        )
        streak = streaks.get(cid, {})
        last_studied = streak.get("last_active_date")

        course_progress.append(
            {
                "course_id": cid,
                "project_id": c.get("project_id"),
                "chat_count": len(c.get("chats") or []),
                "knowledge_files": len(c.get("linked_files") or []),
                "flashcard_decks": len(c_decks),
                "total_cards": total_cards,
                "due_cards": due_cards,
                "quiz_sessions": len(quiz_sessions),
                "avg_score": round(avg_score, 2),
                "current_streak": streak.get("current", 0),
                "longest_streak": streak.get("longest", 0),
                "last_studied": last_studied,
            }
        )

    # Global streak (best across all courses)
    all_streaks = list(streaks.values())
    global_streak = max((s.get("current", 0) for s in all_streaks), default=0)
    global_longest = max((s.get("longest", 0) for s in all_streaks), default=0)
    last_active = max((s.get("last_active_date", "") for s in all_streaks), default="")

    return {
        "status": "ok",
        "courses": courses,
        "upcoming_exams": upcoming_exams[:5],
        "course_todos": course_todos,
        "flashcard_decks": decks,
        "course_progress": course_progress,
        "study_streak": {
            "current": global_streak,
            "longest": global_longest,
            "last_active": last_active or None,
        },
    }
