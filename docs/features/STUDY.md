# Study System

Owlynn's study system provides course tracking, flashcards with spaced repetition, quizzes, study notes, and progress analytics.

## Tools (16)

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
| `study_note_search` | `query, course_id?` | Search notes by keyword (brute-force substring match). |

### Flashcards

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `flashcard_deck_create` | `deck_name, cards_json, course_id?` | Create deck from JSON `[{"front": "...", "back": "..."}]`. SM-2 init. |
| `flashcard_review` | `deck_id?, rating?` | Two-phase: draw next due card, then rate (again/hard/good/easy). |
| `flashcard_suggest` | `course_id, chapter, count?` | Generate flashcard content from course files. Returns JSON pairs. |

### Quizzes

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `quiz_session_start` | `topic, questions_json` | Start quiz session. Questions: `[{"q": "...", "a": "..."}]`. |
| `quiz_session_answer` | `answer` | Submit answer. Substring grading. Advances to next question. |

### Progress & Memory

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `study_session_log` | `course_id, session_type, topic?, duration_minutes?, cards_reviewed?, score?` | Log session for streak tracking. Writes to `data/study_progress.json`. |
| `study_weak_areas` | `course_id?` | Detect weak topics from misconception history in Mem0. |
| `mastery_record` | `kind, topic, detail?` | Save mastery/misconception atom to Mem0 long-term memory. |
| `export_study_sheet` | `title, content, format?` | Export study guide as PDF or DOCX. |

## SM-2 Spaced Repetition

Initial ease: **2.5**, minimum: **1.3**

| Rating | Interval | Ease Change |
|--------|----------|-------------|
| Again | reset to 0 | -0.2 |
| Hard | interval × 1.2 | -0.15 |
| Good | interval × ease | — |
| Easy | interval × ease × 1.3 | +0.15 |

## Data Files

| File | Schema |
|------|--------|
| `data/courses.json` | `[{course_id, name, exam_date, linked_files, project_id, updated_at}]` |
| `data/study_notes/{id}.json` | `{id, course_id, chapter, content, tags, created_at}` |
| `data/flashcards/{deck_id}.json` | `{deck_id, name, course_id, cards: [{front, back, interval, ease, due}], created_at}` |
| `data/quiz_sessions/{key}.json` | `{topic, questions, index, score, started_at}` |
| `data/study_progress.json` | `{sessions: [...], streaks: {course_id: {current, longest, last_active_date}}}` |

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

| Endpoint | Purpose |
|----------|---------|
| `GET /api/courses` | List all courses |
| `GET /api/flashcards` | List all flashcard decks with due counts |
| `GET /api/study/dashboard` | Aggregate: courses, exams, todos, decks, progress, streaks |
| `GET /api/study/exam-countdown` | Upcoming exams with study progress |

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
