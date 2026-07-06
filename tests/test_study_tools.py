"""Tests for study personal assistant tools."""

import json

from src.tools.study_tools import (
    _filter_memories_by_tags,
    sm2_next_interval,
    course_register,
    flashcard_deck_create,
    quiz_session_start,
    quiz_session_answer,
)


def test_sm2_again_resets_interval():
    interval, ease = sm2_next_interval(interval=3.0, ease=2.5, rating="again")
    assert interval == 0.0
    assert ease < 2.5


def test_sm2_good_increases_interval():
    interval, ease = sm2_next_interval(interval=1.0, ease=2.5, rating="good")
    assert interval >= 2.0


def test_filter_memories_by_tags():
    results = [
        {
            "memory": "study misconception",
            "metadata": {"tags": ["study", "misconception"]},
        },
        {"memory": "unrelated weather", "metadata": {"tags": []}},
    ]
    filtered = _filter_memories_by_tags(results, ["misconception"])
    assert len(filtered) == 1


async def test_course_register_and_list(tmp_path, monkeypatch):
    courses_path = tmp_path / "courses.json"
    monkeypatch.setattr("src.tools.study_tools._COURSES_PATH", courses_path)
    out = await course_register.ainvoke(
        {
            "course_id": "UID10667",
            "name": "Digital Literacy",
            "exam_date": "2026-12-01",
            "linked_files": "chapter1.pdf",
        }
    )
    assert "UID10667" in out
    data = json.loads(courses_path.read_text())
    assert data[0]["course_id"] == "UID10667"


def test_flashcard_deck_create(tmp_path, monkeypatch):
    deck_dir = tmp_path / "flashcards"
    monkeypatch.setattr("src.tools.study_tools._FLASHCARDS_DIR", deck_dir)
    cards = json.dumps(
        [
            {"front": "Data", "back": "Raw facts"},
            {"front": "Info", "back": "Processed data"},
        ]
    )
    out = flashcard_deck_create.invoke(
        {"deck_name": "Ch1", "cards_json": cards, "course_id": "UID10667"}
    )
    assert "created" in out.lower()
    assert list(deck_dir.glob("*.json"))


def test_quiz_session_flow(tmp_path, monkeypatch):
    quiz_dir = tmp_path / "quiz"
    monkeypatch.setattr("src.tools.study_tools._QUIZ_DIR", quiz_dir)
    monkeypatch.setattr("src.tools.study_tools._session_key", lambda: "test-thread")

    qs = json.dumps(
        [
            {"q": "What is data?", "a": "raw facts"},
            {"q": "What is info?", "a": "processed"},
        ]
    )
    start = quiz_session_start.invoke({"topic": "Ch1", "questions_json": qs})
    assert "Q1" in start
    ans1 = quiz_session_answer.invoke({"answer": "raw facts"})
    assert "Q2" in ans1 or "Correct" in ans1
    ans2 = quiz_session_answer.invoke({"answer": "processed data"})
    assert "finished" in ans2.lower() or "2/2" in ans2
