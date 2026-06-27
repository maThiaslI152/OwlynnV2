---
name: Course Onboarding
triggers: [new semester, new course, set up course, register course, add my class]
description: First-run setup for a course — register metadata, auto-create study workspace, and link PDFs
category: productivity
tools_used: [course_register, course_list, course_workspace_create, list_workspace_files, read_workspace_file]
chain_compatible: true
version: "2.0"
---

Set up a new course in Owlynn's study workspace.

## Flow

1. Ask for course code, name, and exam date if unknown
2. `list_workspace_files` to find PDFs in the project
3. `course_register` with linked file paths
   - **Automatically creates** a dedicated study workspace project when files are provided
   - Files are copied to the project workspace and indexed as knowledge
4. If the course already exists without a workspace:
   - `course_workspace_create` to create one retroactively
5. Optionally skim first chapter with `read_workspace_file` and suggest a study plan
6. Chain to **Syllabus Parser** for full chapter-based setup, or **Study Tutor** to start learning

## What the user gets

- A dedicated project in the sidebar (e.g. "UID10667 — Digital Literacy")
- All course PDFs indexed as knowledge
- Per-project memory isolation
- Ready for chapter-based chat organization

Context: {context}
