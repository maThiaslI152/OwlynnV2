# Plan: phase9-stabilization

## Linked specs
- specs/active/phase9-stabilization/requirements.md
- specs/active/phase9-stabilization/design.md
- specs/active/phase9-stabilization/tasks.md

## Summary
Investigate and fix 10 remaining bugs: assistant message rendering, DOCX table extraction, XLSX merged cells, silent error handling, workspace switch stale UI, fitz resource leak, auto-index cache path, memory benchmark mock path, plus verify 2 already-fixed items (Redis, SafeMode).

## Scope (in / out)
**In scope:**
- Task 1: Fix assistant message not rendering (backend catch-all + frontend race condition)
- Task 2: Add DOCX table extraction to file_processor.py
- Task 3: Fix XLSX merged cell header cleanup
- Task 4: Add console.warn/logging to 16 silent catch blocks
- Task 5: Fix handleDeleteProject stale closure dependency
- Task 6: Add fitz doc.close() in server.py
- Task 7: Reverse auto-index cache search order
- Task 8: Fix memory benchmark mock path (get_persona → get_persona_by_id)
- Task 9: Verify AC-2 (Redis) and AC-7 (SafeMode) already fixed
- Task 10: Full test suite + verification report

**Out of scope:**
- Tauri IPC full decoupling
- Docling migration
- Drag-and-drop file upload UI
- Agent file selection disambiguation
- Live Talk / voice features

## Architecture decisions
- All fixes are minimal, backwards-compatible diffs
- Error handling: additive logging only, no behavior change
- Files changed: 8 source files, 1 test file
- No new dependencies

## Task sequence (high level)
1. Fix assistant message rendering (AC-1)
2. Add DOCX table extraction (AC-3)
3. Fix XLSX merged cells (AC-4)
4. Fix silent error handling (AC-5)
5. Fix workspace switch stale UI (AC-6)
6. Fix fitz resource leak (AC-8)
7. Fix auto-index cache path (AC-9)
8. Fix memory benchmark mock path (AC-10)
9. Verify already-fixed items (AC-2, AC-7)
10. Full test suite + verification report

## Risks and open questions
- Task 1 (assistant render) is the highest risk — involves frontend state timing
- Tasks 2-3 (DOCX/XLSX) could affect file processing tests if edge cases in table formats
- Task 4 (error handling) is lowest risk — purely additive logging
- None of the tasks require new dependencies

## Approval history
- requirements-review: APPROVED (2026-05-31)
- design-review: APPROVED (2026-05-31)
- tasks-review: pending
