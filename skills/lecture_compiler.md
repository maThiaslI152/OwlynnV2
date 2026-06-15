---
name: Lecture Compiler
triggers: [combine notes, merge chapters, compile notes, unified study guide]
description: Merges multiple chapter PDFs into one structured study document
category: general
tools_used: [read_workspace_file, study_note_save, create_docx]
chain_compatible: true
version: "1.0"
---

Combine multiple lecture/chapter files into one coherent study artifact.

1. Read each file with `read_workspace_file`
2. Synthesize by topic (not file-by-file dump)
3. `study_note_save` with course/chapter tags
4. Optional `create_docx` export when the user wants a downloadable guide

Context: {context}
