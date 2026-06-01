---
status: active
category: reference
last_updated: 2026-05-31
owner: human
---

# Tools Reference

> **Purpose:** Reference for all agent tools organized by toolbox category. Tools are dynamically bound per turn based on router classification.

## Overview

Tools are organized into 5 toolbox categories. The Router selects which categories are needed per turn, and only the relevant tools are bound to the LLM — saving ~2000 tokens of schema overhead.

## Entry Points

```text
src/agent/tool_sets.py            # ToolboxRegistry, resolve_tools()
src/tools/                        # Tool implementations (@tool decorators)
src/agent/nodes/complex.py         # Tool binding in complex_llm_node()
src/agent/nodes/security_proxy.py  # SENSITIVE_TOOLS set
src/api/server.py                  # Tool discovery (GET /api/tools)
```

## Architecture

### Tool Selection Flow

1. Router classifies the user request into one or more toolbox categories
2. `resolve_tools(toolbox_names, web_search_enabled)` returns the union of tools from selected categories + always-included tools
3. `complex_llm_node` binds only the resolved tools to the LLM
4. If the Router is uncertain, it selects `"all"` to fall back to the full tool set

## API

### Always Included

| Tool | Description |
|------|-------------|
| `ask_user` | Ask a clarifying question. Supports 1-3 choice buttons + free text. Always bound regardless of toolbox selection |

### Toolbox: `web_search`

| Tool | Description |
|------|-------------|
| `web_search` | Search via SearXNG/DDG/Bing. Supports `focus_query` for reranking |
| `fetch_webpage` | Fetch URL content. Embedding-ranked excerpts with `focus_query` |

### Toolbox: `file_ops`

| Tool | Description |
|------|-------------|
| `read_workspace_file` | Read file content. Uses Docling for PDF/DOCX (layout-aware markdown, table extraction) with `.processed/` cache. Fuzzy filename matching |
| `write_workspace_file` | Create or overwrite a file |
| `edit_workspace_file` | Search-and-replace in a file. Exact pattern match required |
| `list_workspace_files` | List directory contents with file sizes |
| `delete_workspace_file` | Delete a file |

### Toolbox: `data_viz`

| Tool | Description |
|------|-------------|
| `create_docx` | Word document with headings, bullets, numbered lists |
| `create_xlsx` | Excel spreadsheet from CSV-like text. First row = headers |
| `create_pptx` | PowerPoint with slides separated by `---` |
| `create_pdf` | PDF from text content via PyMuPDF |
| `notebook_run` | Stateful Python REPL. Variables persist between calls |
| `notebook_reset` | Clear all notebook variables |

### Toolbox: `productivity`

| Tool | Description |
|------|-------------|
| `todo_add` | Add task with priority (low/medium/high) |
| `todo_list` | List tasks. Filter by status (all/pending/done) |
| `todo_complete` | Mark a task as done |
| `list_skills` | List available skill templates from `skills/` directory |
| `invoke_skill` | Load and return a skill's prompt template |

### Toolbox: `memory`

| Tool | Description |
|------|-------------|
| `recall_memories` | Search short-term (JSON) memory — keyword overlap on recent 50 entries |
| `recall_all_memories` | Deep semantic search of Mem0/Qdrant vector store (long-term memory). Optional `project_id` for scoping |
| `forget_memory` | Delete specific memories by their ID (hash). Use `recall_all_memories` first to find IDs |
| `search_workspace_docs` | Semantic search over workspace documentation indexed in Qdrant. Queries project-specific knowledge base and returns relevant document excerpts |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Dynamic toolbox selection | Reduces token overhead by ~2000/turn | Router must correctly classify toolbox needs |
| Security proxy gates destructive tools | Safety for file write/edit/delete, notebook execution | HITL latency for approved sensitive calls |
| Always-include `ask_user` | HITL escape hatch on every turn | Minor token overhead |

## Testing

Security policy — sensitive tools require approval via `security_proxy`:

| Tool | Risk |
|------|------|
| `write_workspace_file` | File system modification |
| `edit_workspace_file` | File system modification |
| `delete_workspace_file` | Destructive file removal |
| `notebook_run` | Arbitrary code execution |

All other tools auto-approve. Dangerous shell patterns (`rm -rf`, `sudo`, etc.) are blocked.

## Configuration

### Adding a New Tool

1. Create `@tool` function in `src/tools/`
2. Import in `src/agent/tool_sets.py`
3. Add to the appropriate `TOOLBOX_REGISTRY` category (or create a new category)
4. Tool automatically included when that toolbox is selected by the Router
5. Update guidance text in `src/agent/nodes/complex.py`
6. If sensitive, add to `SENSITIVE_TOOLS` in `src/agent/nodes/security_proxy.py`

## Related

- [`docs/API_REFERENCE.md`](API_REFERENCE.md) — REST endpoint reference
- [`docs/ARCHITECTURE_OVERVIEW.md`](ARCHITECTURE_OVERVIEW.md) — system architecture

## Last updated

2026-05-31 — `docs-standards-timeline` added search_workspace_docs to memory toolbox
