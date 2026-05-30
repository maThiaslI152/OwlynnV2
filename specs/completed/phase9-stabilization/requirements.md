# Requirements: Phase 9 — Stabilization (Remaining Bug Fixes)

> **Purpose:** Investigate and fix all remaining bugs and architectural issues identified in Phase 8 browser audit (2026-05-25), file intake audit (2026-05-30), and lingering risks from project status.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | User | send a message and see the assistant's response rendered in the UI | I can use the chat feature reliably |
| US-2 | User | have chat history persist across page reloads | I don't lose my conversations |
| US-3 | User | upload DOCX files and have table content extracted | structured data in documents is searchable |
| US-4 | Developer | see proper error messages instead of silent failures | I can debug issues quickly |
| US-5 | User | have the UI stay consistent when switching workspaces | there are no stale or empty panels |

## Acceptance Criteria (EARS format)

| ID | Criterion |
|----|-----------|
| AC-1 | When the backend sends the final `answer` WebSocket event, the frontend shall render the assistant message in the chat DOM. |
| AC-2 | When a user reloads the page, previous chat history shall be restored (Redis persistence working). |
| AC-3 | When a DOCX file with tables is processed, table content shall be extracted and included in the output. |
| AC-4 | When an XLSX file with merged title cells is processed, the output shall not contain `Unnamed:` column headers or `NaN` rows. |
| AC-5 | When an API call fails (chat title, profile update, etc.), the error shall be surfaced to the user via operator note or console warning, not silently swallowed. |
| AC-6 | When a user switches workspaces, all UI panels shall reflect the new workspace state without stale data. |
| AC-7 | When the Safe Mode dropdown is used in a browser (non-Tauri) environment, it shall fall back to REST API without throwing `Cannot read properties of undefined (reading 'invoke')`. |
| AC-8 | When `fitz.open()` encounters a PDF error, the file handle shall be properly closed (no resource leak). |
| AC-9 | When the file watcher processes a non-default project, auto-indexing into Qdrant shall work (cache path match). |
| AC-10 | When the memory benchmark tests are run, all `TestMemoryInject` tests shall pass (fix stale `get_persona` mock path). |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Performance | All existing tests (backend + frontend) shall continue to pass after fixes. |
| NFR-2 | Stability | No regressions introduced in previously fixed bugs (BUG-1 through BUG-11). |

## Edge Cases and Error States

- What happens when WebSocket disconnects mid-response? Frontend should handle reconnection gracefully and show appropriate state.
- What happens when Redis is unavailable on startup? Backend should use MemorySaver fallback with a logged warning.
- What happens when a DOCX file has no tables? The paragraph-only extraction should still work as before.
- What happens when the user rapidly switches workspaces? No stale closure reads of `activeProjectId`.

## Out of Scope

- Tauri IPC leakage (SafeMode, ScreenAssist, window sizing) — browser is primary launch mode, Tauri on hold.
- Agent file selection ambiguity (LLM-driven file picking) — requires semantic improvements beyond bug fixing scope.
- Docling migration for unified PDF/DOCX extraction — tracked as medium-term recommendation, not a bug fix.
- Drag-and-drop file upload UI — feature addition, not stabilization.
- Live Talk / voice features — already removed.

## Dependencies

- Existing test suites: `tests/test_bugfix_persona_leak.py`, `tests/test_bugfix_chat_title.py`, frontend vitest suite
- Backend `src/api/server.py` — WebSocket event handling, Redis connection
- Frontend `App.tsx` — WebSocket event pipeline, workspace switching, operator notes
- Frontend `MemoryPanel.tsx` — loading state handling
- Frontend `OrchestrationPanel.tsx` — routing data rendering
- `src/api/file_processor.py` — PDF/DOCX/XLSX extraction

## References

- `docs/BUG-ANALYSIS.md` — Phase 8 browser audit (8 bugs found)
- `docs/BUG-TRACKER.md` — Bug tracker (BUG-1 through BUG-11, all fixed)
- `docs/STATUS.md` — Project status, lingering risks, architectural concerns
- `docs/debugging/browser-verification.md` — Live browser test results (assistant render blocked, Redis broken)
- `docs/audit-file-intake-2026-05-30.md` — File intake audit (auto-index, DOCX tables, XLSX merged cells)
- `docs/ARCHITECTURE_OVERVIEW.md` — System architecture

## Approval

- `requirements-review` AskQuestion: **APPROVED** (2026-05-31, manual override — user replied "APPROVE" via chat)
- Proceeding to design phase.
