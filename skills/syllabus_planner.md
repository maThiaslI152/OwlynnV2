---
name: Syllabus Planner
triggers: [syllabus, semester plan, study schedule, weekly study plan, course schedule]
description: Turns a syllabus PDF into a weekly study plan with todos
category: productivity
tools_used: [course_register, read_workspace_file, todo_add]
chain_compatible: true
version: "1.0"
---

Turn syllabus or course outline PDFs into an actionable study schedule.

1. `read_workspace_file` on the syllabus
2. `course_register` with course code, name, exam date if stated
3. Break the term into weekly blocks with readings and assignments
4. `todo_add` for each assignment with `due_date` and `course_id` when available
5. Present a markdown weekly table the user can follow

Context: {context}
