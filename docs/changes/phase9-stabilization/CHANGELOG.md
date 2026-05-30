# Changelog: phase9-stabilization

> **Purpose:** Per-task entries for Phase 9 stabilization. Appended after each task completes in Agent mode.

| Task | Date | Summary |
|------|------|---------|
| — | 2026-05-31 | Scaffold — SDD init with bug inventory from Phase 8 audit + file intake audit |
| Task 1 | 2026-05-31 | Fix assistant message not rendering (AC-1). Backend: added catch-all `on_chain_end` for unmatched nodes with AIMessage content. Frontend: fixed race condition by using `finalContent` directly instead of re-reading store for streamed content. |
| Task 2 | 2026-05-31 | DOCX table extraction (AC-3). Added `doc.tables` iteration in `_process_word()` fallback with pipe-delimited row format. |
| Task 3 | 2026-05-31 | XLSX merged cells cleanup (AC-4). Added second-pass scan to rename remaining `Unnamed:` columns using first valid value from data rows. |
| Task 4 | 2026-05-31 | Silent error handling (AC-5). Added `console.warn` to 8 frontend catch blocks and `logger.warning` to 6 backend `except:pass` blocks across App.tsx, wsClient.ts, MemoryPanel.tsx, server.py, memory.py. |
| Task 5 | 2026-05-31 | Workspace switch stale UI (AC-6). Removed `activeProjectId` from `handleDeleteProject` dependency array — callback now uses ref only. |
| Task 6 | 2026-05-31 | `fitz.open()` resource leak (AC-8). Added `try/finally` with `doc.close()` in `extract_pdf_text()`. |
| Task 7 | 2026-05-31 | Auto-index cache path (AC-9). Swapped search order in `notify_file_processed()` to check `root_processed` first (fast path). |
| Task 8 | 2026-05-31 | Memory benchmark mock path (AC-10). Fixed stale `get_persona` -> `get_persona_by_id` mock paths in test_memory_benchmark.py AND test_complex_benchmark.py. |

## Related

- `docs/STATUS.md` — project status
- `docs/BUG-TRACKER.md` — bug tracker
