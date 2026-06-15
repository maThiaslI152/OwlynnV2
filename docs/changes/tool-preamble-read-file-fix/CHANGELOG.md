---
status: active
category: changelog
audience: agent
last_updated: 2026-06-15
owner: ai-agent
---

# Changelog: Tool Preamble Streaming & `read_workspace_file` False Error

> **Purpose:** Record fixes for PDF study prompts where the UI showed a false `read_workspace_file` ERROR card, duplicate “Reading workspace file…” text, and streamed LLM preamble before the real answer.

**Trigger:** User attaches `chapter 1 Digital Literacy.pdf` and asks Owlynn to help study it.

## Symptom summary (what the user saw)

1. Tool card `read_workspace_file` marked **ERROR** at **0.0s** even though the file was read successfully on retry.
2. **Duplicate** “Reading workspace file…” lines in chat (stream bubble + tool card).
3. Final answer sometimes appeared only after the false error; preamble text polluted the stream.

## Root causes

### BUG-TOOL-1 — False ERROR on successful PDF read

| | |
|---|---|
| **Severity** | High |
| **Symptom** | `tool_execution` status `error` immediately after `read_workspace_file` returns long PDF text. |
| **Root cause** | `_tool_status_from_content()` matched the substring `"error:"` anywhere in tool output. Academic PDFs often contain phrases like “trial and error”. |
| **Fix** | Status is `error` only when output **starts with** `Error:` / `error:` (or known failure prefixes like `execution error`, `traceback`). |
| **Files** | `src/api/ws/handler.py` — `_tool_status_from_content()` |
| **Tests** | `tests/test_ws_tool_ui_helpers.py` |

### BUG-TOOL-2 — LLM passes `[Attached: filename]` as tool arg

| | |
|---|---|
| **Severity** | Medium |
| **Symptom** | First `read_workspace_file` call fails path resolution; model copies chat attachment wrapper into `filename`. |
| **Root cause** | `get_safe_workspace_path()` did not strip `[Attached: …]` or `Attached:` prefixes. |
| **Fix** | `_normalize_workspace_filename()` in `get_safe_workspace_path()`; `_workspace_paths_from_text()` also extracts `[Attached: …]` for prefetch hints. |
| **Files** | `src/tools/core_tools.py`, `src/agent/nodes/complex.py` |
| **Tests** | `tests/test_tools_core.py` |

### BUG-TOOL-3 — Wrong `.processed/` cache directory

| | |
|---|---|
| **Severity** | Medium |
| **Symptom** | Cache miss on project workspaces; slower reads or inconsistent text vs upload pipeline. |
| **Root cause** | `read_workspace_file` looked under `BASE_WORKSPACE_DIR/.processed` instead of `tool_workspace_root()/.processed`. |
| **Fix** | Cache path uses active project workspace root. |
| **Files** | `src/tools/core_tools.py` |
| **Tests** | `tests/test_tools_core.py` |

### BUG-UI-1 — Tool preamble streamed as assistant text

| | |
|---|---|
| **Severity** | Medium |
| **Symptom** | “Reading workspace file…” appears as streaming assistant message before tool card and before the real answer. |
| **Root cause** | Complex node emits short tool-only placeholders (`_TOOL_ONLY_PLACEHOLDERS` in `formatter.py`) as `AIMessage` content; handler forwarded them as `chunk` / `assistant.message`. |
| **Fix** | Backend suppresses preamble chunks while tools are pending/running and skips `assistant.message` for preamble-only tool turns. Frontend filters matching text via `isToolPreambleText()` and removes stale stream bubbles when a tool enters `running`. |
| **Files** | `src/api/ws/handler.py`, `frontend-v2/src/lib/toolPreamble.ts`, `frontend-v2/src/App.tsx` |
| **Tests** | `tests/test_ws_tool_ui_helpers.py`, `frontend-v2/src/lib/toolPreamble.test.ts` |

## Expected UX after fix

```text
User message (+ PDF attachment)
  → tool_execution running  read_workspace_file
  → tool_execution success  read_workspace_file
  → chunk / assistant.message  (study guide prose only)
```

No standalone “Reading workspace file…” bubble. Tool card status reflects real failures only (`Error: File '…' not found.` at line start).

## Verification

```bash
# Backend helpers
python3 -m pytest tests/test_ws_tool_ui_helpers.py tests/test_tools_core.py -q

# Frontend preamble helper
cd frontend-v2 && npm test -- src/lib/toolPreamble.test.ts

# Full gate
./scripts/ci.sh --quick
```

Manual: attach a PDF, ask to study it — one tool card (success), no duplicate preamble, answer streams after tool completes.

## Related docs

- [`docs/CHAT_PROTOCOL.md`](../../CHAT_PROTOCOL.md) — `chunk` suppression rules, `tool_execution` status derivation
- [`docs/TOOLS.md`](../../TOOLS.md) — `read_workspace_file` filename normalization
- [`docs/debugging/tools.md`](../../debugging/tools.md) — false ERROR diagnostic row
