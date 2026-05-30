# Design: Phase 9 — Stabilization

> **Purpose:** Fix strategies for all 10 remaining bugs identified in Phase 8 browser audit, file intake audit, and memory benchmark failures.

## Architecture Overview

Nine bug fixes across the frontend (React/Zustand), backend (FastAPI/Python), and file processing pipeline. All fixes are self-contained, backwards-compatible, and target specific code paths. No new dependencies required.

## System Diagram

```mermaid
flowchart TD
  subgraph Frontend
    WS[WebSocket Handler] --> ASM[assistant.message event]
    ASM --> STORE[Zustand Store]
    STORE --> RENDER[Chat DOM]
    SW[Workspace Switch] --> STALE[Stale Closure Bug]
    SM[SafeMode Panel] --> TB[tauriBridge.ts]
  end
  subgraph Backend
    OCE[on_chain_end] --> AM{node in simple/complex_llm?}
    AM -->|yes| EMIT[Emit assistant.message]
    AM -->|no| SILENT[Silent Drop]
    REDIS[AsyncRedisSaver] --> PERSIST[Chat Persistence]
    CT[Chat Title Gen] --> CATCH[except: pass]
  end
  subgraph File Processing
    FP[file_processor.py] --> DOCX[DOCX: paragraphs only, no tables]
    FP --> XLSX[XLSX: Unnamed: headers from merged cells]
    FP --> PDF[PDF: server.py fitz.open() no close]
    AI[Auto-Index] --> CACHE[Cache path always searches wrong dir first]
  end
  subgraph Tests
    BM[Benchmark Tests] --> MOCK[get_persona mock path stale]
  end
```

## Component / Module Breakdown

| Component | Fix Scope | Files |
|-----------|-----------|-------|
| **Frontend WS Handler** | Fix race condition in `assistant.message` event processing | `frontend-v2/src/App.tsx` |
| **Frontend Error Handling** | Add `console.warn` to 7 empty catch blocks | `frontend-v2/src/App.tsx`, `frontend-v2/src/lib/wsClient.ts`, `frontend-v2/src/components/MemoryPanel.tsx` |
| **Frontend Workspace Switch** | Fix `handleDeleteProject` ref vs state race | `frontend-v2/src/App.tsx` |
| **Backend Silent Errors** | Log 9 `except: pass` blocks at `logger.warning` | `src/api/server.py`, `src/agent/nodes/memory.py` |
| **Backend PDF Close** | Add `doc.close()` in server.py fitz path | `src/api/server.py` |
| **Backend Auto-Index** | Skip guaranteed-miss cache dir check | `src/api/server.py` |
| **File Processor DOCX** | Add table iteration to `_process_word()` | `src/api/file_processor.py` |
| **File Processor XLSX** | Fix merged cell header cleanup | `src/api/file_processor.py` |
| **Memory Benchmark** | Fix `get_persona` → `get_persona_by_id` mock path | `tests/benchmarks/test_memory_benchmark.py` |

## Fix Strategies by AC

### AC-1: Assistant Message Rendering

**Root cause:** `on_chain_end` handler in `server.py` only emits `assistant.message` when `node in ["simple", "complex_llm"]`. Root-level events (no `node` metadata) fall through silently. Also, frontend handler has a race between `msgs` capture and `currentContent` re-read.

**Fix:**
1. **Backend** (`server.py`): Add a catch-all in `on_chain_end` — if no node-specific handler matched AND the event contains an output (AIMessage with content), emit `assistant.message` with the content. This ensures no response is silently dropped.
2. **Frontend** (`App.tsx`): Refactor `assistant.message` handler to use a single store read. Replace the dual-read pattern (`getState().messages` at line 268, then `getState().messages` again at line 271) with a unified approach: read messages once, compute final content, apply.

### AC-2: Redis Persistence

**Status:** Already fixed. `AsyncRedisSaver(redis_url=REDIS_URL)` at `graph.py:198` uses the correct kwarg for the installed `langgraph-checkpoint-redis` version. No code change needed.

**Verification:** Check the constructor signature matches at runtime, confirm the chat persists across reloads. Mark as verified.

### AC-3: DOCX Table Extraction

**Root cause:** `_process_word()` fallback (lines 273-282) iterates `doc.paragraphs` only. `doc.tables` is never processed.

**Fix:** Add table iteration after paragraph extraction:
```python
for table in doc.tables:
    text += "\n--- Table ---\n"
    for row in table.rows:
        row_text = " | ".join(cell.text.strip() for cell in row.cells)
        text += row_text + "\n"
```

### AC-4: XLSX Merged Cells

**Root cause:** `_process_table()` cleanup at lines 234-247 only promotes first data row once. Multi-row merged headers leave `Unnamed: N` columns.

**Fix:** After the current promotion logic, add a second pass: rename any remaining `Unnamed:` columns by scanning ALL rows for the first non-`Unnamed:` non-NaN value in each column. If no column header found, fall back to `Column_{N}`.

### AC-5: Silent Error Handling

**Root cause:** 7 frontend empty `catch {}` and 9 backend `except: pass` blocks swallow errors.

**Fix:** Add `console.warn` with context to every frontend catch block. Upgrade backend `except: pass` to `logger.warning` with exception info. Prioritize:
- Frontend: chat title (570), edit project (618), profile/history (207, 245)
- Backend: chat title generation (749), persona update (309), auto-index (1096), Mem0 search (memory.py 174, 193, 224)

### AC-6: Stale Workspace Switch UI

**Root cause:** `handleDeleteProject` uses `activeProjectIdRef.current` but the callback's dependency array includes `activeProjectId` (not the ref). If user switches projects during delete API call, the ref may point to the new project.

**Fix:** Remove `activeProjectId` from the dependency array. Only keep `clearSession` and `loadProjects`. The ref-based access ensures the latest value is always read without recreating the callback.

### AC-7: SafeMode Browser Fallback

**Status:** Already fixed. Dynamic import in `tauriBridge.ts` (line 18) and optimistic update + REST fallback in `SafeModePanel.tsx` (lines 30-44) are correctly in place.

**Verification:** Confirm no `Cannot read properties of undefined (reading 'invoke')` error in browser mode. Mark as verified.

### AC-8: `fitz.open()` Resource Leak

**Root cause:** `server.py` line 1948 opens `fitz.open(stream=raw_bytes, filetype="pdf")` without calling `doc.close()`.

**Fix:** Add `doc.close()` or wrap in try/finally at the server.py call site. The `file_processor.py` path is already correct with try/finally.

### AC-9: Auto-Index Cache Path Mismatch

**Root cause:** `notify_file_processed()` always checks `project_workspace/.processed/` first (guaranteed miss for non-default projects). Also, `_process_table()` writes `.md` instead of `.txt`.

**Fix:**
1. In `notify_file_processed()`: Check `root_processed` first (fast path). Only fall back to `project_workspace/.processed/` for non-default projects.
2. In `_process_table()`: Change output extension from `.md` to `.txt` for consistency, OR update all search sites to search both `.txt` and `.md`.

### AC-10: Memory Benchmark Stale Mock

**Root cause:** Tests patch `src.agent.nodes.memory.get_persona` but the function was renamed/moved to `get_persona_by_id` in `src.memory.persona_manager`. The mock silently does nothing.

**Fix:** Update mock path to `src.agent.nodes.memory.get_persona_by_id` in both test functions (lines 55 and 99).

## Trade-offs and Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Fix catch blocks with `console.warn` not full error UI | Minimal change, preserves existing UX | Full toast/operator note system — too invasive for stabilization |
| Skip `.md` extension standardization | Changing extension could break existing cached files; search already handles both | Normalizing to `.txt` only would require migration or re-processing |
| Keep `get_persona` mock in benchmark tests | The mock function is intentional — test measures memory inject with controlled persona | Removing mock entirely would make tests slower and non-deterministic |

## Error Handling Strategy

- All fixes preserve existing error recovery behavior (catch doesn't re-raise)
- Silent catches are upgraded to `console.warn` (frontend) or `logger.warning` (backend)
- Backend logging uses existing `logger` instances; no new logging infrastructure needed
- No user-facing error UI changes — operator note pattern already exists for important failures

## Security Considerations

- No auth/authz changes — fixes are internal error handling and file processing
- DOCX/XLSX extraction changes only affect already-trusted files (from workspace watcher)
- No new network or IPC surface area

## Open Questions

- None — all 10 ACs have been investigated at the source code level

## References

- `requirements.md` — 10 acceptance criteria
- `plan_ref: .cursorplan/active/phase9-stabilization/plan.md`

## Approval

- `design-review` AskQuestion: **APPROVED** (2026-05-31)
- Proceeding to tasks phase.
