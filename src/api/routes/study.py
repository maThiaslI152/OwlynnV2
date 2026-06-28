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


@router.get("/api/study/analytics")
async def study_analytics():
    """Study analytics: score trends, topic mastery, study time by course."""
    progress = _read_json(_PROGRESS_PATH, {"sessions": [], "streaks": {}})
    sessions = progress.get("sessions") or []
    streaks = progress.get("streaks") or {}

    # Score trend by course (last 30 sessions)
    score_by_course: dict[str, list[dict]] = {}
    for s in sessions[-30:]:
        cid = s.get("course_id", "unknown")
        if s.get("score") is not None:
            score_by_course.setdefault(cid, []).append(
                {
                    "date": s.get("started_at", "")[:10],
                    "score": round(s.get("score", 0) * 100),
                }
            )

    # Topic mastery from Mem0 (if available)
    topics: list[dict] = []
    try:
        from src.memory.educator import detect_weak_topics
        from src.memory.long_term import memory

        if memory:
            weak = detect_weak_topics(memory, "owner")
            for w in weak[:10]:
                topics.append(
                    {
                        "topic": w.get("topic", "Unknown"),
                        "mastery": round((1 - w.get("weakness", 0.5)) * 100),
                        "struggles": w.get("struggles", 0),
                    }
                )
    except Exception:
        pass

    # Study time by course
    time_by_course: dict[str, int] = {}
    for s in sessions:
        cid = s.get("course_id", "unknown")
        time_by_course[cid] = time_by_course.get(cid, 0) + s.get("duration_minutes", 0)

    # Sessions by type
    sessions_by_type: dict[str, int] = {}
    for s in sessions:
        stype = s.get("type", "unknown")
        sessions_by_type[stype] = sessions_by_type.get(stype, 0) + 1

    return {
        "status": "ok",
        "score_trend": score_by_course,
        "topic_mastery": topics,
        "study_time": {
            "total_minutes": sum(time_by_course.values()),
            "by_course": time_by_course,
        },
        "sessions_by_type": sessions_by_type,
        "total_sessions": len(sessions),
    }


_NOTES_DIR = DATA_DIR / "study_notes"


@router.get("/api/study/notes")
async def list_notes(q: str = "", course_id: str = ""):
    """List/search study notes."""
    if not _NOTES_DIR.is_dir():
        return {"status": "ok", "notes": []}

    notes = []
    q_lower = q.lower().strip()
    q_words = set(q_lower.split()) if q_lower else set()

    for path in sorted(_NOTES_DIR.glob("*.json")):
        note = _read_json(path, {})
        if course_id and note.get("course_id") != course_id.strip():
            continue

        if q_lower:
            blob = f"{note.get('chapter', '')} {note.get('content', '')} {' '.join(note.get('tags') or [])}".lower()
            if q_lower not in blob:
                # Fuzzy match
                blob_words = set(blob.split())
                matched = len(q_words.intersection(blob_words))
                if matched / len(q_words) < 0.3 if q_words else True:
                    continue

        notes.append(
            {
                "id": note.get("id"),
                "course_id": note.get("course_id"),
                "chapter": note.get("chapter"),
                "content": note.get("content", "")[:500],
                "tags": note.get("tags") or [],
                "created_at": note.get("created_at"),
            }
        )

    return {"status": "ok", "notes": notes[:20]}


@router.get("/api/flashcards/{deck_id}")
async def get_deck(deck_id: str):
    """Get a specific flashcard deck with all cards."""
    if not _FLASHCARDS_DIR.is_dir():
        return {"status": "error", "message": "No flashcard decks found."}
    deck_path = _FLASHCARDS_DIR / f"{deck_id.strip()}.json"
    if not deck_path.is_file():
        return {"status": "error", "message": f"Deck '{deck_id}' not found."}
    deck = _read_json(deck_path, {})
    return {"status": "ok", "deck": deck}


@router.put("/api/flashcards/{deck_id}")
async def update_deck(deck_id: str, body: dict):
    """Update a flashcard deck (add/edit/remove cards)."""
    if not _FLASHCARDS_DIR.is_dir():
        return {"status": "error", "message": "No flashcard decks found."}
    deck_path = _FLASHCARDS_DIR / f"{deck_id.strip()}.json"
    if not deck_path.is_file():
        return {"status": "error", "message": f"Deck '{deck_id}' not found."}

    deck = _read_json(deck_path, {})
    cards = deck.get("cards") or []
    action = body.get("action")

    if action == "update_card":
        card_id = body.get("card_id")
        for card in cards:
            if card.get("card_id") == card_id:
                if "front" in body:
                    card["front"] = body["front"]
                if "back" in body:
                    card["back"] = body["back"]
                break
        else:
            return {"status": "error", "message": f"Card '{card_id}' not found."}
    elif action == "delete_card":
        card_id = body.get("card_id")
        cards = [c for c in cards if c.get("card_id") != card_id]
        deck["cards"] = cards
    elif action == "add_card":
        import uuid
        from datetime import datetime

        cards.append(
            {
                "card_id": uuid.uuid4().hex[:12],
                "front": body.get("front", ""),
                "back": body.get("back", ""),
                "interval": 0.0,
                "ease": 2.5,
                "due": datetime.now().isoformat(timespec="seconds"),
            }
        )
        deck["cards"] = cards
    else:
        return {"status": "error", "message": f"Unknown action: {action}"}

    _write_json(deck_path, deck)
    return {"status": "ok", "deck": deck}


def _write_json(path: Path, data) -> None:
    """Write JSON to file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)
