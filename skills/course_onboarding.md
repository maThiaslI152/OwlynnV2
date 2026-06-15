---
name: Course Onboarding
triggers: [new semester, new course, set up course, register course, add my class]
description: First-run setup for a course — register metadata and link workspace PDFs
category: productivity
tools_used: [course_register, course_list, list_workspace_files, read_workspace_file]
chain_compatible: true
version: "1.0"
---

Set up a new course in Owlynn's study workspace.

1. Ask for course code, name, and exam date if unknown
2. `list_workspace_files` to find PDFs in the project
3. `course_register` with linked file paths
4. Optionally skim first chapter with `read_workspace_file` and suggest a study plan (chain to Study Tutor)

Context: {context}
