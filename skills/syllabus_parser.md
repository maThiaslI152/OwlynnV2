---
name: Syllabus Parser
triggers: [parse syllabus, analyze syllabus, set up from syllabus, extract chapters, course structure]
description: Parses a syllabus PDF to extract chapter/topic structure, creates a study workspace with per-topic chats
category: productivity
tools_used: [read_workspace_file, course_register, course_chat_create, course_workspace_create, todo_add, flashcard_deck_create, flashcard_suggest]
chain_compatible: true
version: "1.0"
---

Parse a syllabus or course material PDF to extract its structure and set up a complete study workspace.

## Flow

1. Ask the user which PDF is the syllabus (or use the one they attached)
2. `read_workspace_file` on the syllabus PDF
3. Extract the structure using reasoning:
   - Course code and name
   - Exam date (if stated)
   - Chapter/topic list with descriptions
   - Key terms per chapter
4. `course_register` with course code, name, exam date, and linked PDFs
   - This auto-creates a study workspace project when linked_files are provided
5. For each chapter/topic:
   - `course_chat_create` to create a dedicated chat in the study workspace
   - Suggest a study schedule with `todo_add` (due_date, course_id)
6. If the user wants flashcards:
   - `flashcard_suggest` for each chapter to generate cards
   - `flashcard_deck_create` with the generated cards
7. Present a summary table:

| Chapter | Topic | Chat Created | Todo Added |
|---------|-------|--------------|------------|
| 1 | ... | ✅ | ✅ |
| 2 | ... | ✅ | ✅ |

## Example

User: "Parse this syllabus PDF and set up my study workspace"

1. Read the PDF → extract course UID10667, name "Digital Literacy", exam Dec 1
2. `course_register("UID10667", "Digital Literacy", "2026-12-01", "ch1.pdf,ch2.pdf,ch3.pdf")`
3. `course_chat_create("UID10667", "Chapter 1 — Digital Standards")`
4. `course_chat_create("UID10667", "Chapter 2 — Computer Basics")`
5. `course_chat_create("UID10667", "Chapter 3 — Internet & Security")`
6. `todo_add("Study Chapter 1", due_date="2026-09-15", course_id="UID10667")`
7. Present summary

Context: {context}
