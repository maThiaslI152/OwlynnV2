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
_PROGRESS_PATH = DATA_DIR / "study_progress.json"


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


def _normalize_answer(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for answer comparison."""
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def _word_boundary_match(expected: str, given: str) -> bool:
    """Check if expected answer appears as whole words in given answer."""
    exp = _normalize_answer(expected)
    giv = _normalize_answer(given)
    if not exp:
        return False
    # Exact match after normalization
    if exp == giv:
        return True
    # All expected words present in given
    exp_words = set(exp.split())
    giv_words = set(giv.split())
    return exp_words.issubset(giv_words)


def _auto_log_session(
    course_id: str,
    session_type: str,
    topic: str = "",
    duration_minutes: int = 0,
    cards_reviewed: int = 0,
    score: float = 0.0,
) -> None:
    """Auto-log a study session to progress tracking."""
    _PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    progress = _read_json(_PROGRESS_PATH, {"sessions": [], "streaks": {}})
    now = datetime.now()
    today = now.date().isoformat()

    # Add session
    progress.setdefault("sessions", []).append(
        {
            "course_id": course_id,
            "type": session_type,
            "topic": topic,
            "started_at": now.isoformat(timespec="seconds"),
            "duration_minutes": duration_minutes,
            "cards_reviewed": cards_reviewed,
            "score": score,
        }
    )

    # Update streak
    streaks = progress.setdefault("streaks", {})
    streak = streaks.setdefault(
        course_id, {"current": 0, "longest": 0, "last_active_date": None}
    )
    last = streak.get("last_active_date")
    if last == today:
        pass  # Already active today
    elif last == (now - timedelta(days=1)).date().isoformat():
        streak["current"] = streak.get("current", 0) + 1
    else:
        streak["current"] = 1
    streak["longest"] = max(streak.get("longest", 0), streak["current"])
    streak["last_active_date"] = today

    _write_json(_PROGRESS_PATH, progress)


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


def _auto_create_study_project(
    course_id: str, name: str, files: list[str]
) -> str | None:
    """Create a study workspace project for a course and index linked files."""
    try:
        import asyncio
        import shutil

        from src.memory.project import project_manager
        from src.config.settings import get_project_workspace

        project_name = f"{course_id} — {name}"
        instructions = (
            f"You are a study tutor for {name} ({course_id}). "
            f"Use the knowledge files as source material. "
            f"When the user asks about this course, reference the indexed documents."
        )
        project = project_manager.create_project(project_name, instructions)
        project_id = project["id"]

        workspace = get_project_workspace(project_id)
        for fname in files:
            src = Path(get_project_workspace("default")) / fname
            if src.is_file():
                dst = Path(workspace) / fname
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                # Index as knowledge in Qdrant (non-blocking best-effort)
                try:
                    content = dst.read_text(encoding="utf-8", errors="replace")[:32000]
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(
                            project_manager.add_knowledge(project_id, fname, content)
                        )
                    else:
                        loop.run_until_complete(
                            project_manager.add_knowledge(project_id, fname, content)
                        )
                except Exception:
                    pass  # Non-critical — files are still in workspace
        return project_id
    except Exception:
        return None


@tool
def course_register(
    course_id: str,
    name: str,
    exam_date: str = "",
    linked_files: str = "",
) -> str:
    """
    Register or update a course for study tracking.

    When linked_files are provided, automatically creates a dedicated study
    workspace project and indexes the files as knowledge.

    Args:
        course_id: Short code (e.g. UID10667).
        name: Full course name.
        exam_date: Optional ISO date YYYY-MM-DD.
        linked_files: Comma-separated workspace PDF paths.
    """
    courses = _read_json(_COURSES_PATH, [])
    files = [f.strip() for f in linked_files.split(",") if f.strip()]
    cid = course_id.strip()

    # Preserve existing project_id if course already exists
    existing_project_id = None
    for c in courses:
        if c.get("course_id") == cid:
            existing_project_id = c.get("project_id")
            break

    project_id = existing_project_id

    # Auto-create study workspace when linked files are provided and no project exists
    if files and not project_id:
        project_id = _auto_create_study_project(cid, name.strip(), files)

    entry = {
        "course_id": cid,
        "name": name.strip(),
        "exam_date": exam_date.strip() or None,
        "linked_files": files,
        "project_id": project_id,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    replaced = False
    for i, c in enumerate(courses):
        if c.get("course_id") == cid:
            courses[i] = {**c, **entry}
            replaced = True
            break
    if not replaced:
        courses.append(entry)
    _write_json(_COURSES_PATH, courses)

    msg = f"✅ Course registered: {cid} — {name}"
    if project_id:
        msg += f"\n📁 Study workspace created (project: {project_id})"
    return msg


@tool
def course_list() -> str:
    """List all registered courses with exam dates and workspace status."""
    courses = _read_json(_COURSES_PATH, [])
    if not courses:
        return "No courses registered. Use course_register to add one."
    lines = ["📚 Courses:"]
    for c in courses:
        exam = c.get("exam_date") or "no exam date"
        files = len(c.get("linked_files") or [])
        ws = "📁" if c.get("project_id") else "—"
        lines.append(
            f"  {ws} {c.get('course_id')}: {c.get('name')} (exam: {exam}, {files} files)"
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
def course_workspace_create(course_id: str, linked_files: str = "") -> str:
    """
    Create a study workspace project for an existing course.

    Args:
        course_id: Course code to create workspace for.
        linked_files: Comma-separated workspace PDF paths to index.
    """
    courses = _read_json(_COURSES_PATH, [])
    target = None
    for c in courses:
        if c.get("course_id") == course_id.strip():
            target = c
            break
    if not target:
        return (
            f"Course '{course_id}' not found. Register it first with course_register."
        )

    if target.get("project_id"):
        return f"Course '{course_id}' already has a workspace (project: {target['project_id']})."

    files = [f.strip() for f in linked_files.split(",") if f.strip()] or target.get(
        "linked_files", []
    )
    if not files:
        return "No files to index. Provide linked_files or register the course with files first."

    project_id = _auto_create_study_project(target["course_id"], target["name"], files)
    if not project_id:
        return "Failed to create study workspace."

    # Update course entry with project_id and files
    for i, c in enumerate(courses):
        if c.get("course_id") == course_id.strip():
            courses[i]["project_id"] = project_id
            courses[i]["linked_files"] = files
            courses[i]["updated_at"] = datetime.now().isoformat(timespec="seconds")
            break
    _write_json(_COURSES_PATH, courses)
    return f"✅ Study workspace created for {course_id} (project: {project_id}, {len(files)} files indexed)"


@tool
def course_chat_create(course_id: str, chat_name: str) -> str:
    """
    Create a named chat in a course's study workspace project.

    Args:
        course_id: Course code.
        chat_name: Name for the new chat (e.g. "Chapter 1 — Intro").
    """
    courses = _read_json(_COURSES_PATH, [])
    target = None
    for c in courses:
        if c.get("course_id") == course_id.strip():
            target = c
            break
    if not target:
        return f"Course '{course_id}' not found."
    if not target.get("project_id"):
        return f"Course '{course_id}' has no study workspace. Use course_workspace_create first."

    try:
        import uuid

        from src.memory.project import project_manager

        chat_id = f"thread-{uuid.uuid4()}"
        project_manager.add_chat_to_project(
            target["project_id"],
            {"id": chat_id, "name": chat_name.strip(), "created_at": time.time()},
        )
        return f"✅ Chat '{chat_name}' created in {course_id} workspace (id: {chat_id})"
    except Exception as e:
        return f"Failed to create chat: {e}"


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
    """
    Search study notes by keyword or semantic similarity.

    Args:
        query: Search query.
        course_id: Optional course filter.
    """
    if not _NOTES_DIR.is_dir():
        return "No study notes yet."
    q = query.lower().strip()
    q_words = set(q.split())
    hits: list[tuple[float, str]] = []
    for path in sorted(_NOTES_DIR.glob("*.json")):
        note = _read_json(path, {})
        if course_id and note.get("course_id") != course_id.strip():
            continue
        blob = f"{note.get('chapter', '')} {note.get('content', '')} {' '.join(note.get('tags') or [])}".lower()

        if not q:
            score = 1.0
        elif q in blob:
            # Exact substring match — high score
            score = 1.0
        else:
            # Fuzzy: count matching words
            blob_words = set(blob.split())
            matched = len(q_words.intersection(blob_words))
            score = matched / len(q_words) if q_words else 0.0

        if score > 0.3:
            hits.append(
                (
                    score,
                    f"  [{note.get('id')}] {note.get('course_id')} / {note.get('chapter')}: "
                    f"{str(note.get('content', ''))[:120]}...",
                )
            )

    if not hits:
        return "No matching study notes."

    # Sort by score descending
    hits.sort(key=lambda x: x[0], reverse=True)
    return "Study notes:\n" + "\n".join(h[1] for h in hits[:15])


@tool
def study_note_delete(note_id: str) -> str:
    """
    Delete a study note by ID.

    Args:
        note_id: Note ID to delete.
    """
    if not _NOTES_DIR.is_dir():
        return "No study notes yet."
    path = _NOTES_DIR / f"{note_id.strip()}.json"
    if not path.is_file():
        return f"Error: note '{note_id}' not found."
    path.unlink()
    return f"✅ Study note '{note_id}' deleted."


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
                "card_id": uuid.uuid4().hex[:12],
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
def flashcard_import(deck_name: str, file_path: str, course_id: str = "") -> str:
    """
    Import flashcards from a CSV file.

    Supported CSV formats (auto-detected by header):
    - front,back
    - term,definition
    - question,answer

    Args:
        deck_name: Human-readable deck name.
        file_path: Path to CSV file.
        course_id: Optional course association.
    """
    import csv

    path = Path(file_path)
    if not path.is_file():
        return f"Error: file not found — {file_path}"

    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Auto-detect column names
            headers = reader.fieldnames or []
            front_col = None
            back_col = None
            for h in headers:
                h_lower = h.strip().lower()
                if h_lower in ("front", "term", "question"):
                    front_col = h
                elif h_lower in ("back", "definition", "answer"):
                    back_col = h
            if not front_col or not back_col:
                return f"Error: could not detect columns. Expected headers like 'front,back' or 'term,definition'. Found: {headers}"

            cards_json = []
            for row in reader:
                front = str(row.get(front_col, "")).strip()
                back = str(row.get(back_col, "")).strip()
                if front and back:
                    cards_json.append({"front": front, "back": back})

    except Exception as e:
        return f"Error reading CSV: {e}"

    if not cards_json:
        return "Error: no valid cards found in CSV."

    return flashcard_deck_create(
        deck_name=deck_name,
        cards_json=json.dumps(cards_json, ensure_ascii=False),
        course_id=course_id,
    )


@tool
def flashcard_export(deck_id: str, format: str = "csv") -> str:
    """
    Export a flashcard deck to CSV format.

    Args:
        deck_id: Deck id to export.
        format: Export format (currently only 'csv' supported).
    """
    import csv
    import io

    _FLASHCARDS_DIR.mkdir(parents=True, exist_ok=True)
    deck_path = _FLASHCARDS_DIR / f"{deck_id.strip()}.json"
    if not deck_path.is_file():
        return f"Error: deck '{deck_id}' not found."

    deck = _read_json(deck_path, {})
    cards = deck.get("cards") or []
    if not cards:
        return f"Error: deck '{deck_id}' is empty."

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["front", "back"])
    writer.writeheader()
    for card in cards:
        writer.writerow({"front": card.get("front", ""), "back": card.get("back", "")})

    csv_content = output.getvalue()

    # Save to exports directory
    export_dir = DATA_DIR / "flashcard_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"{deck_id}.csv"
    export_path.write_text(csv_content, encoding="utf-8")

    return f"✅ Exported {len(cards)} cards to {export_path}"


@tool
def flashcard_review(deck_id: str = "", rating: str = "", card_id: str = "") -> str:
    """
    Present the next due flashcard or rate the previous card.

    Args:
        deck_id: Deck id (required on first call in a review).
        rating: After answering — again, hard, good, or easy. Omit to draw next card.
        card_id: Card id to rate (required when rating, prevents race condition).
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
        # Rate specific card by card_id (prevents race condition)
        if card_id:
            card = next((c for c in cards if c.get("card_id") == card_id), None)
            if not card:
                return f"Error: card_id '{card_id}' not found in deck."
        else:
            # Fallback: first due card (legacy behavior)
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
        # Auto-log flashcard review session
        _auto_log_session(
            course_id=deck.get("course_id", ""),
            session_type="flashcard_review",
            topic=deck.get("name", ""),
            cards_reviewed=1,
        )
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
        f"Card ID: {card.get('card_id', 'unknown')}\n"
        f"FRONT: {card.get('front')}\n"
        f"(Answer aloud, then call flashcard_review with deck_id='{deck_path.stem}', card_id='{card.get('card_id', '')}' and rating=again|hard|good|easy)"
    )


@tool
def quiz_session_start(topic: str, questions_json: str, course_id: str = "") -> str:
    """
    Start a multi-question quiz session in the current chat thread.

    Args:
        topic: Quiz topic label.
        questions_json: JSON array of question objects.
            Free-text: {"q": "...", "a": "..."}
            MCQ: {"q": "...", "options": ["A", "B", "C"], "correctIndex": 0, "explanation": "..."}
        course_id: Optional course association for context-aware grading.
    """
    try:
        questions = json.loads(questions_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid questions_json — {e}"
    if not isinstance(questions, list) or not questions:
        return "Error: questions_json must be a non-empty array."

    # Normalize questions — add type field
    for q in questions:
        if "options" in q and "correctIndex" in q:
            q["type"] = "mcq"
        else:
            q["type"] = "free_text"

    _QUIZ_DIR.mkdir(parents=True, exist_ok=True)
    session = {
        "topic": topic.strip(),
        "course_id": course_id.strip(),
        "questions": questions,
        "index": 0,
        "score": 0,
        "answers": [],  # Track per-question answers
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    path = _QUIZ_DIR / f"{_session_key()}.json"
    _write_json(path, session)
    first = questions[0]
    q_text = first.get("q", first)
    if first.get("type") == "mcq":
        options = "\n".join(
            f"  {chr(65 + i)}. {opt}" for i, opt in enumerate(first.get("options", []))
        )
        return f"Quiz started: {topic}\nQ1/{len(questions)}: {q_text}\n{options}"
    return f"Quiz started: {topic}\nQ1/{len(questions)}: {q_text}"


@tool
def quiz_session_answer(answer: str) -> str:
    """
    Submit an answer for the current quiz question.

    Args:
        answer: User's answer text (for free-text) or letter/number (for MCQ).
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
    q_type = q.get("type", "free_text")
    given = answer.strip()

    # Grade based on question type
    if q_type == "mcq":
        # MCQ: exact match on correctIndex
        try:
            # Accept letter (A, B, C) or number (0, 1, 2)
            if given.isalpha():
                selected = ord(given.upper()) - 65
            else:
                selected = int(given)
            correct = selected == q.get("correctIndex")
        except (ValueError, IndexError):
            correct = False
        feedback = "✓ Correct" if correct else "✗ Incorrect"
        if not correct and q.get("explanation"):
            feedback += f" — {q['explanation']}"
    else:
        # Free-text: word-boundary matching (fast, no LLM call)
        expected = str(q.get("a", "")).strip()
        correct = _word_boundary_match(expected, given)
        feedback = "✓ Correct" if correct else f"✗ Expected: {q.get('a', '')}"

    if correct:
        session["score"] = int(session.get("score") or 0) + 1

    # Track answer
    session.setdefault("answers", []).append(
        {
            "question_idx": idx,
            "given": given,
            "correct": correct,
        }
    )

    session["index"] = idx + 1
    _write_json(path, session)

    if session["index"] >= len(questions):
        # Auto-log quiz session on completion
        score_pct = session["score"] / len(questions) if len(questions) > 0 else 0
        _auto_log_session(
            course_id=session.get("course_id", session.get("topic", "")),
            session_type="quiz",
            topic=session.get("topic", ""),
            score=score_pct,
        )
        return f"{feedback}\n\nQuiz finished — {session['score']}/{len(questions)} correct."
    next_q = questions[session["index"]]
    q_text = next_q.get("q", next_q)
    if next_q.get("type") == "mcq":
        options = "\n".join(
            f"  {chr(65 + i)}. {opt}" for i, opt in enumerate(next_q.get("options", []))
        )
        return f"{feedback}\n\nQ{session['index'] + 1}/{len(questions)}: {q_text}\n{options}"
    return f"{feedback}\n\nQ{session['index'] + 1}/{len(questions)}: {q_text}"


@tool
def quiz_session_results() -> str:
    """
    Get results of the current or most recent quiz session.

    Returns per-question breakdown with scores.
    """
    path = _QUIZ_DIR / f"{_session_key()}.json"
    session = _read_json(path, None)
    if not session:
        return "No quiz session found."

    questions = session.get("questions") or []
    answers = session.get("answers") or []
    score = session.get("score", 0)
    total = len(questions)

    lines = [f"Quiz: {session.get('topic', 'Unknown')}"]
    lines.append(
        f"Score: {score}/{total} ({score / total * 100:.0f}%)"
        if total > 0
        else "Score: 0/0"
    )
    lines.append("")

    for i, q in enumerate(questions):
        a = next((x for x in answers if x.get("question_idx") == i), None)
        status = "✓" if a and a.get("correct") else "✗" if a else "—"
        lines.append(f"  {status} Q{i + 1}: {q.get('q', '?')[:80]}")
        if a and not a.get("correct"):
            lines.append(f"      Given: {a.get('given', '?')}")
            if q.get("type") == "mcq":
                lines.append(
                    f"      Correct: {q.get('options', [])[q.get('correctIndex', 0)]}"
                )
            else:
                lines.append(f"      Expected: {q.get('a', '?')}")

    return "\n".join(lines)


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


# ── Study Progress & Streak Tracking ─────────────────────────────────


def _load_progress() -> dict:
    return _read_json(_PROGRESS_PATH, {"sessions": [], "streaks": {}})


def _save_progress(data: dict) -> None:
    _write_json(_PROGRESS_PATH, data)


@tool
def study_session_log(
    course_id: str,
    session_type: str,
    topic: str = "",
    duration_minutes: int = 0,
    cards_reviewed: int = 0,
    score: float = 0.0,
) -> str:
    """
    Log a study session for streak tracking and progress analytics.

    Args:
        course_id: Course code.
        session_type: flashcard_review, quiz, study, or exam_prep.
        topic: Topic or chapter studied.
        duration_minutes: How long the session lasted.
        cards_reviewed: Number of flashcards reviewed (if applicable).
        score: Score as decimal 0.0-1.0 (if applicable).
    """
    progress = _load_progress()
    now = datetime.now()
    today = now.date().isoformat()

    session_entry = {
        "course_id": course_id.strip(),
        "type": session_type.strip(),
        "topic": topic.strip(),
        "started_at": now.isoformat(timespec="seconds"),
        "duration_minutes": duration_minutes,
        "cards_reviewed": cards_reviewed,
        "score": score,
    }
    progress.setdefault("sessions", []).append(session_entry)

    # Update streak
    streaks = progress.setdefault("streaks", {})
    streak = streaks.get(course_id.strip(), {})
    last_active = streak.get("last_active_date", "")
    current = streak.get("current", 0)
    longest = streak.get("longest", 0)

    if last_active == today:
        pass  # Same day, no change
    elif last_active == (now.date() - timedelta(days=1)).isoformat():
        current += 1
    else:
        current = 1

    longest = max(longest, current)
    streaks[course_id.strip()] = {
        "current": current,
        "longest": longest,
        "last_active_date": today,
    }
    _save_progress(progress)
    return (
        f"✅ Study session logged for {course_id} ({session_type}). "
        f"🔥 Streak: {current} day(s)."
    )


@tool
def study_weak_areas(course_id: str = "") -> str:
    """
    Identify weak topics based on misconception history from long-term memory.

    Args:
        course_id: Optional course filter.
    """
    try:
        from src.memory.long_term import memory as mem0_memory
    except Exception:
        return "Error: Mem0 not available."
    if mem0_memory is None:
        return "Mem0 memory not initialized."

    from src.memory.educator import STUDY_STRUGGLE_PREFIX, is_study_memory_item
    from src.tools.workspace_context import _active_project_id

    active_pid = _active_project_id.get()
    user_id = (
        f"project:{active_pid}" if active_pid and active_pid != "default" else "owner"
    )

    try:
        results_dict = mem0_memory.search(
            f"{STUDY_STRUGGLE_PREFIX} misconception struggle",
            filters={"user_id": user_id},
            limit=20,
        )
        items = (
            results_dict.get("results", [])
            if isinstance(results_dict, dict)
            else results_dict
        )
    except Exception:
        return "Could not search study memories."

    struggles = [i for i in (items or []) if is_study_memory_item(i)]
    if not struggles:
        return "No weak areas detected yet. Keep studying!"

    # Count by topic
    topic_counts: dict[str, int] = {}
    for item in struggles:
        text = str(item.get("memory") or item.get("text") or "")
        # Extract topic from [STUDY_STRUGGLE] prefix
        match = __import__("re").search(
            r"\[STUDY_STRUGGLE\]\s*([^:]+):", text, __import__("re").I
        )
        topic = match.group(1).strip() if match else "Unknown"
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    lines = ["📊 Weak Areas (by misconception count):"]
    for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  ⚠️ {topic}: {count} misconception(s)")
    return "\n".join(lines)


@tool
def flashcard_suggest(course_id: str, chapter: str, count: int = 10) -> str:
    """
    Suggest flashcard content from a course chapter.
    Returns JSON front/back pairs ready for flashcard_deck_create.

    Args:
        course_id: Course code to find linked files.
        chapter: Chapter or topic name to extract cards from.
        count: Number of flashcards to suggest (default 10).
    """
    courses = _read_json(_COURSES_PATH, [])
    target = None
    for c in courses:
        if c.get("course_id") == course_id.strip():
            target = c
            break
    if not target:
        return f"Course '{course_id}' not found."

    files = target.get("linked_files", [])
    if not files:
        return f"No linked files for {course_id}. Register the course with files first."

    # Try to find a matching file for the chapter
    chapter_lower = chapter.strip().lower()
    matched_file = None
    for f in files:
        if chapter_lower in f.lower():
            matched_file = f
            break
    if not matched_file:
        matched_file = files[0]  # Default to first file

    # Read file content from the course's project workspace
    try:
        from src.config.settings import get_project_workspace

        course_pid = target.get("project_id") or "default"
        workspace = get_project_workspace(course_pid)
        filepath = Path(workspace) / matched_file
        if not filepath.is_file():
            return f"File not found: {matched_file} in workspace {workspace}"
        content = filepath.read_text(encoding="utf-8", errors="replace")[:16000]
    except Exception as e:
        return f"Failed to read {matched_file}: {e}"

    # Return the content and instructions for the agent to generate flashcards
    return (
        f"Source: {matched_file} (chapter: {chapter})\n"
        f"Content preview:\n{content[:8000]}\n\n"
        f"Generate {count} flashcards from this content as a JSON array of "
        f'{{"front": "...", "back": "..."}} objects, then call flashcard_deck_create '
        f'with deck_name="{chapter}" and course_id="{course_id}".'
    )
