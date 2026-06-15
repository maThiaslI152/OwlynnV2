"""Study personal assistant tools — courses, notes, flashcards, quizzes, mastery."""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from src.config.audit_log import get_thread_id
from src.config.settings import DATA_DIR

_COURSES_PATH = DATA_DIR / "courses.json"
_NOTES_DIR = DATA_DIR / "study_notes"
_FLASHCARDS_DIR = DATA_DIR / "flashcards"
_QUIZ_DIR = DATA_DIR / "quiz_sessions"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _session_key() -> str:
    tid = get_thread_id()
    return f"graph_{tid}" if tid else "default"


def sm2_next_interval(
    *,
    interval: float,
    ease: float,
    rating: str,
) -> tuple[float, float]:
    """SM-2 lite: return (new_interval_days, new_ease)."""
    r = rating.lower().strip()
    if r in ("again", "0"):
        return 0.0, max(1.3, ease - 0.2)
    if r in ("hard", "1"):
        return max(1.0, interval * 1.2), max(1.3, ease - 0.15)
    if r in ("easy", "3"):
        return max(1.0, interval * ease * 1.3), ease + 0.15
    # good / default
    if interval <= 0:
        return 1.0, ease
    return interval * ease, ease


def _filter_memories_by_tags(results: list, tags: list[str]) -> list:
    if not tags:
        return results
    tag_set = {t.lower() for t in tags}
    filtered = []
    for item in results:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata") or {}
        meta_tags = [str(t).lower() for t in (meta.get("tags") or [])]
        text = str(item.get("memory") or item.get("text") or "").lower()
        if tag_set.intersection(meta_tags) or any(t in text for t in tag_set):
            filtered.append(item)
    return filtered or results


@tool
def course_register(
    course_id: str,
    name: str,
    exam_date: str = "",
    linked_files: str = "",
) -> str:
    """
    Register or update a course for study tracking.

    Args:
        course_id: Short code (e.g. UID10667).
        name: Full course name.
        exam_date: Optional ISO date YYYY-MM-DD.
        linked_files: Comma-separated workspace PDF paths.
    """
    courses = _read_json(_COURSES_PATH, [])
    files = [f.strip() for f in linked_files.split(",") if f.strip()]
    entry = {
        "course_id": course_id.strip(),
        "name": name.strip(),
        "exam_date": exam_date.strip() or None,
        "linked_files": files,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    replaced = False
    for i, c in enumerate(courses):
        if c.get("course_id") == entry["course_id"]:
            courses[i] = {**c, **entry}
            replaced = True
            break
    if not replaced:
        courses.append(entry)
    _write_json(_COURSES_PATH, courses)
    return f"✅ Course registered: {entry['course_id']} — {entry['name']}"


@tool
def course_list() -> str:
    """List all registered courses with exam dates."""
    courses = _read_json(_COURSES_PATH, [])
    if not courses:
        return "No courses registered. Use course_register to add one."
    lines = ["📚 Courses:"]
    for c in courses:
        exam = c.get("exam_date") or "no exam date"
        files = len(c.get("linked_files") or [])
        lines.append(
            f"  • {c.get('course_id')}: {c.get('name')} (exam: {exam}, {files} files)"
        )
    return "\n".join(lines)


@tool
def course_get(course_id: str) -> str:
    """Get metadata for one course by course_id."""
    courses = _read_json(_COURSES_PATH, [])
    for c in courses:
        if c.get("course_id") == course_id.strip():
            return json.dumps(c, ensure_ascii=False, indent=2)
    return f"Course '{course_id}' not found."


@tool
def study_note_save(
    course_id: str,
    chapter: str,
    content: str,
    tags: str = "",
) -> str:
    """
    Save a structured study note.

    Args:
        course_id: Course code.
        chapter: Chapter or topic label.
        content: Note body (markdown ok).
        tags: Comma-separated tags.
    """
    _NOTES_DIR.mkdir(parents=True, exist_ok=True)
    note_id = uuid.uuid4().hex[:10]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    note = {
        "id": note_id,
        "course_id": course_id.strip(),
        "chapter": chapter.strip(),
        "content": content.strip(),
        "tags": tag_list,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    path = _NOTES_DIR / f"{note_id}.json"
    _write_json(path, note)
    return f"✅ Study note saved ({note_id}) for {course_id} / {chapter}"


@tool
def study_note_search(query: str, course_id: str = "") -> str:
    """Search study notes by keyword (optional course filter)."""
    if not _NOTES_DIR.is_dir():
        return "No study notes yet."
    q = query.lower().strip()
    hits: list[str] = []
    for path in sorted(_NOTES_DIR.glob("*.json")):
        note = _read_json(path, {})
        if course_id and note.get("course_id") != course_id.strip():
            continue
        blob = f"{note.get('chapter', '')} {note.get('content', '')} {' '.join(note.get('tags') or [])}".lower()
        if not q or q in blob:
            hits.append(
                f"  [{note.get('id')}] {note.get('course_id')} / {note.get('chapter')}: "
                f"{str(note.get('content', ''))[:120]}..."
            )
    if not hits:
        return "No matching study notes."
    return "Study notes:\n" + "\n".join(hits[:15])


@tool
def flashcard_deck_create(
    deck_name: str,
    cards_json: str,
    course_id: str = "",
) -> str:
    """
    Create a flashcard deck from JSON card list.

    Args:
        deck_name: Human-readable deck name.
        cards_json: JSON array of {"front": "...", "back": "..."} objects.
        course_id: Optional course association.
    """
    try:
        cards_raw = json.loads(cards_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid cards_json — {e}"
    if not isinstance(cards_raw, list) or not cards_raw:
        return "Error: cards_json must be a non-empty JSON array."

    _FLASHCARDS_DIR.mkdir(parents=True, exist_ok=True)
    deck_id = (
        re.sub(r"[^a-zA-Z0-9_-]+", "-", deck_name.strip().lower())[:40]
        or uuid.uuid4().hex[:8]
    )
    now = datetime.now().isoformat(timespec="seconds")
    cards = []
    for item in cards_raw:
        if not isinstance(item, dict):
            continue
        front = str(item.get("front", "")).strip()
        back = str(item.get("back", "")).strip()
        if not front or not back:
            continue
        cards.append(
            {
                "front": front,
                "back": back,
                "interval": 0.0,
                "ease": 2.5,
                "due": now,
            }
        )
    if not cards:
        return "Error: no valid cards in payload."
    deck = {
        "deck_id": deck_id,
        "name": deck_name.strip(),
        "course_id": course_id.strip() or None,
        "cards": cards,
        "created_at": now,
    }
    _write_json(_FLASHCARDS_DIR / f"{deck_id}.json", deck)
    return f"✅ Flashcard deck '{deck_name}' created ({len(cards)} cards, id={deck_id})"


@tool
def flashcard_review(deck_id: str = "", rating: str = "") -> str:
    """
    Present the next due flashcard or rate the previous card.

    Args:
        deck_id: Deck id (required on first call in a review).
        rating: After answering — again, hard, good, or easy. Omit to draw next card.
    """
    _FLASHCARDS_DIR.mkdir(parents=True, exist_ok=True)
    decks = list(_FLASHCARDS_DIR.glob("*.json"))
    if not decks:
        return "No flashcard decks. Use flashcard_deck_create first."

    deck_path = None
    if deck_id:
        candidate = _FLASHCARDS_DIR / f"{deck_id.strip()}.json"
        if candidate.is_file():
            deck_path = candidate
    if deck_path is None:
        deck_path = decks[0]

    deck = _read_json(deck_path, {})
    cards = deck.get("cards") or []
    if not cards:
        return f"Deck {deck_path.stem} is empty."

    now = datetime.now()
    if rating:
        # Rate last shown card (first due card before reorder)
        due_cards = sorted(cards, key=lambda c: c.get("due") or "")
        card = due_cards[0]
        interval, ease = sm2_next_interval(
            interval=float(card.get("interval") or 0),
            ease=float(card.get("ease") or 2.5),
            rating=rating,
        )
        card["interval"] = interval
        card["ease"] = ease
        card["due"] = (now + timedelta(days=max(interval, 0))).isoformat(
            timespec="seconds"
        )
        _write_json(deck_path, deck)
        return f"Rated '{rating}'. Next review in {interval:.1f} day(s). Call again without rating for next card."

    due = [
        c
        for c in cards
        if not c.get("due") or c.get("due") <= now.isoformat(timespec="seconds")
    ]
    pool = due if due else cards
    card = sorted(pool, key=lambda c: c.get("due") or "")[0]
    return (
        f"Deck: {deck.get('name')} ({deck_path.stem})\n"
        f"FRONT: {card.get('front')}\n"
        f"(Answer aloud, then call flashcard_review with deck_id='{deck_path.stem}' and rating=again|hard|good|easy)"
    )


@tool
def quiz_session_start(topic: str, questions_json: str) -> str:
    """
    Start a multi-question quiz session in the current chat thread.

    Args:
        topic: Quiz topic label.
        questions_json: JSON array of {"q": "...", "a": "..."} objects.
    """
    try:
        questions = json.loads(questions_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid questions_json — {e}"
    if not isinstance(questions, list) or not questions:
        return "Error: questions_json must be a non-empty array."

    _QUIZ_DIR.mkdir(parents=True, exist_ok=True)
    session = {
        "topic": topic.strip(),
        "questions": questions,
        "index": 0,
        "score": 0,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    path = _QUIZ_DIR / f"{_session_key()}.json"
    _write_json(path, session)
    first = questions[0]
    return f"Quiz started: {topic}\nQ1/{len(questions)}: {first.get('q', first)}"


@tool
def quiz_session_answer(answer: str) -> str:
    """
    Submit an answer for the current quiz question.

    Args:
        answer: User's answer text.
    """
    path = _QUIZ_DIR / f"{_session_key()}.json"
    session = _read_json(path, None)
    if not session:
        return "No active quiz. Use quiz_session_start first."

    questions = session.get("questions") or []
    idx = int(session.get("index") or 0)
    if idx >= len(questions):
        return f"Quiz complete. Score: {session.get('score', 0)}/{len(questions)}"

    q = questions[idx]
    expected = str(q.get("a", "")).strip().lower()
    given = answer.strip().lower()
    correct = expected and (expected in given or given in expected)
    if correct:
        session["score"] = int(session.get("score") or 0) + 1

    session["index"] = idx + 1
    _write_json(path, session)

    feedback = "✓ Correct" if correct else f"✗ Expected: {q.get('a', '')}"
    if session["index"] >= len(questions):
        return f"{feedback}\n\nQuiz finished — {session['score']}/{len(questions)} correct."
    next_q = questions[session["index"]]
    return f"{feedback}\n\nQ{session['index'] + 1}/{len(questions)}: {next_q.get('q', next_q)}"


@tool
def mastery_record(kind: str, topic: str, detail: str = "") -> str:
    """
    Explicitly save a study mastery or misconception atom to long-term memory.

    Args:
        kind: misconception or mastery.
        topic: Subject/topic label.
        detail: Optional extra context.
    """
    try:
        from src.memory.long_term import memory as mem0_memory
    except Exception:
        return "Error: Mem0 not available."

    if mem0_memory is None:
        return "Mem0 memory not initialized."

    from src.memory.educator import (
        STUDY_STRUGGLE_PREFIX,
        build_mastery_atom,
        build_misconception_atom,
    )
    from src.tools.workspace_context import _active_project_id

    k = kind.strip().lower()
    if k == "misconception":
        human = f"Your explanation of {topic} was wrong — {detail}".strip()
        atom = build_misconception_atom(human, "")
        tags = ["study", "misconception"]
    elif k == "mastery":
        human = f"I finally understand {topic} now. {detail}".strip()
        atom = build_mastery_atom(human)
        tags = ["study", "mastery"]
    else:
        return "Error: kind must be misconception or mastery."

    active_pid = _active_project_id.get()
    user_id = (
        f"project:{active_pid}" if active_pid and active_pid != "default" else "owner"
    )
    mem0_memory.add(
        atom,
        user_id=user_id,
        metadata={"type": "study_atom", "tags": tags, "scenario_id": "study"},
        infer=False,
    )
    return f"✅ Recorded study {k} for: {topic}"


@tool
def export_study_sheet(title: str, content: str, format: str = "pdf") -> str:
    """
    Export a study guide to the workspace as PDF or DOCX.

    Args:
        title: Document title.
        content: Study sheet body text.
        format: pdf or docx.
    """
    fmt = format.strip().lower()
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.strip())[:50] or "study-sheet"
    if fmt == "docx":
        from src.tools.doc_generator import create_docx

        return create_docx.invoke(
            {"filename": f"{safe}.docx", "content": content, "title": title}
        )
    from src.tools.doc_generator import create_pdf

    return create_pdf.invoke(
        {"filename": f"{safe}.pdf", "content": content, "title": title}
    )
