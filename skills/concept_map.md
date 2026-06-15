---
name: Concept Map
triggers: [concept map, mind map, how topics connect, topic hierarchy, map the chapter]
description: Text hierarchy showing how chapter concepts relate
category: general
tools_used: [read_workspace_file, notebook_run, create_pdf]
chain_compatible: true
version: "1.0"
---

Build a hierarchical concept map from course material.

1. `read_workspace_file` on the source
2. Output an indented tree or mermaid-friendly outline: main theme → subtopics → key terms
3. Optional `create_pdf` one-pager for exam review

Context: {context}
