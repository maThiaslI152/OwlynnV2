---
status: active
category: reference
last_updated: 2026-07-09
owner: ai-agent
audience: agent
---

# Study System

Owlynn's study system provides course tracking, flashcards with spaced repetition, quizzes, study notes, and progress analytics.

## Tools (20)

All tools defined in `src/tools/study_tools.py`.

### Course Management

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `course_register` | `course_id, name, exam_date?, linked_files?` | Register/update course. Auto-creates workspace project when `linked_files` provided. |
| `course_workspace_create` | `course_id, linked_files?` | Create study workspace for existing course (on-demand). |
| `course_chat_create` | `course_id, chat_name` | Create named chat in course project (e.g., "Chapter 1 — Intro"). |
| `course_list` | — | List all registered courses with exam dates and workspace status. |
| `course_get` | `course_id` | Get full course metadata JSON. |

### Study Notes

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `study_note_save` | `course_id, chapter, content, tags?` | Save structured study note. Stored as `data/study_notes/{id}.json`. |
| `study_note_search` | `query, course_id?` | Search notes by keyword with fuzzy matching (word overlap). |
| `study_note_delete` | `note_id` | Delete a study note by ID. |

### Flashcards

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `flashcard_deck_create` | `deck_name, cards_json, course_id?` | Create deck from JSON `[{"front": "...", "back": "..."}]`. SM-2 init. |
| `flashcard_review` | `deck_id?, rating?, card_id?` | Two-phase: draw next due card, then rate (again/hard/good/easy). Uses `card_id` to prevent race condition. |
| `flashcard_suggest` | `course_id, chapter, count?` | Generate flashcard content from course files. Returns JSON pairs. |
| `flashcard_import` | `deck_name, file_path, course_id?` | Import flashcards from CSV (supports `front,back` / `term,definition` / `question,answer` headers). |
| `flashcard_export` | `deck_id, format?` | Export deck to CSV format. Saves to `data/flashcard_exports/`. |

### Quizzes

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `quiz_session_start` | `topic, questions_json, course_id?` | Start quiz session. Supports MCQ (`options` + `correctIndex`) and free-text (`a`). |
| `quiz_session_answer` | `answer` | Submit answer. MCQ: exact index match. Free-text: word-boundary matching. |
| `quiz_session_results` | — | Get per-question breakdown with scores. |

### Progress & Memory

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `study_session_log` | `course_id, session_type, topic?, duration_minutes?, cards_reviewed?, score?` | Log session for streak tracking. Writes to `data/study_progress.json`. |
| `study_weak_areas` | `course_id?` | Detect weak topics from misconception history in Mem0. |
| `mastery_record` | `kind, topic, detail?` | Save mastery/misconception atom to Mem0 long-term memory. |
| `export_study_sheet` | `title, content, format?` | Export study guide as PDF or DOCX. |

## Quiz System

### Question Types

**MCQ (Multiple Choice):**
```json
{
  "q": "What does DNS stand for?",
  "options": ["Domain Name System", "Data Network Service", "Digital Node Standard"],
  "correctIndex": 0,
  "explanation": "DNS translates domain names to IP addresses."
}
```

**Free-text:**
```json
{
  "q": "What is the purpose of a firewall?",
  "a": "A firewall monitors and controls network traffic based on security rules."
}
```

### Grading

- **MCQ:** Exact match on `correctIndex` (accepts letter A/B/C or number 0/1/2)
- **Free-text:** Word-boundary matching (normalizes punctuation, checks all expected words present)

### Auto-logging

Quiz sessions are automatically logged to `data/study_progress.json` when completed.

## SM-2 Spaced Repetition

Initial ease: **2.5**, minimum: **1.3**

| Rating | Interval | Ease Change |
|--------|----------|-------------|
| Again | reset to 0 | -0.2 |
| Hard | interval × 1.2 | -0.15 |
| Good | interval × ease | — |
| Easy | interval × ease × 1.3 | +0.15 |

### Card ID Tracking

Each flashcard has a unique `card_id` (12-char hex). When rating, pass `card_id` to prevent rating the wrong card (race condition fix).

## Data Files

| File | Schema |
|------|--------|
| `data/courses.json` | `[{course_id, name, exam_date, linked_files, project_id, updated_at}]` |
| `data/study_notes/{id}.json` | `{id, course_id, chapter, content, tags, created_at}` |
| `data/flashcards/{deck_id}.json` | `{deck_id, name, course_id, cards: [{card_id, front, back, interval, ease, due}], created_at}` |
| `data/quiz_sessions/{key}.json` | `{topic, course_id, questions, index, score, answers, started_at}` |
| `data/study_progress.json` | `{sessions: [...], streaks: {course_id: {current, longest, last_active_date}}}` |
| `data/flashcard_exports/{deck_id}.csv` | CSV export of flashcard decks |

## Skills (6)

| Skill | File | Triggers |
|-------|------|----------|
| Syllabus Parser | `skills/syllabus_parser.md` | parse syllabus, extract chapters |
| Course Onboarding | `skills/course_onboarding.md` | new course, register course |
| Study Tutor | `skills/study_tutor.md` | study, quiz me, help me learn |
| Exam Prep | `skills/exam_prep.md` | mock exam, practice test |
| Flashcard Builder | `skills/flashcard_builder.md` | flashcards, spaced repetition |
| Weak Area Coach | `skills/weak_area_coach.md` | weak areas, review mistakes |

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/courses` | GET | List all courses |
| `/api/flashcards` | GET | List all flashcard decks with due counts |
| `/api/flashcards/{deck_id}` | GET | Get specific deck with all cards |
| `/api/flashcards/{deck_id}` | PUT | Update deck (add/edit/remove cards) |
| `/api/study/dashboard` | GET | Aggregate: courses, exams, todos, decks, progress, streaks |
| `/api/study/exam-countdown` | GET | Upcoming exams with study progress |
| `/api/study/analytics` | GET | Score trends, topic mastery, session types |
| `/api/study/notes` | GET | List/search study notes |

## Frontend Components

| Component | File | Purpose |
|-----------|------|---------|
| `StudyPanel` | `frontend-v2/src/components/StudyPanel.tsx` | Main study panel (courses, exams, todos, decks) |
| `StudyProgressPanel` | `frontend-v2/src/components/StudyProgressPanel.tsx` | Streak, per-course progress, exams |
| `StudyAnalytics` | `frontend-v2/src/components/StudyAnalytics.tsx` | Score trend chart, topic mastery radar |
| `StudyNotesSearch` | `frontend-v2/src/components/StudyNotesSearch.tsx` | Searchable notes in sidebar |
| `DeckBrowserModal` | `frontend-v2/src/components/DeckBrowserModal.tsx` | Modal deck editor (view/edit/delete cards) |

## Memory Integration

The study system integrates with Mem0 long-term memory:

- **Misconception detection:** Patterns like "was wrong", "incorrect" → `[STUDY_STRUGGLE]` atom
- **Mastery detection:** Patterns like "I finally understand" → `[STUDY_MASTERY]` atom
- **Struggle recall:** "what did I struggle with?" → searches Mem0 for study atoms
- **Explicit recording:** `mastery_record` tool bypasses auto-detection

## Course ↔ Project Linking

When `course_register` is called with `linked_files`:

1. Creates a dedicated project (e.g., "UID10667 — Digital Literacy")
2. Copies linked files to project workspace
3. Indexes files as knowledge in Qdrant
4. Sets project instructions to study tutor prompt
5. Stores `project_id` in course metadata

This gives each course:
- Isolated workspace directory
- Per-project memory isolation (`project:<id>` in Mem0)
- Knowledge files indexed for semantic search
- Dedicated chat list for subject organization

## Session Cleanup

Stale quiz sessions (older than 30 days) can be archived:

```bash
python scripts/cleanup_study_sessions.py --dry-run  # Preview
python scripts/cleanup_study_sessions.py             # Execute
```

Archives to `data/quiz_archive/`.
