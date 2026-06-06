# Changelog: Defense in Depth & Pipeline Optimizations

## [2026-06-06] - Security & Pipeline Enhancements

### Added
- Created `src/tools/notebook_worker.py` to isolate notebook `exec()` calls into a child process, protecting the main application memory.
- Added `prefetch_memory` WebSocket event to `src/api/ws/handler.py` to allow frontend to trigger vector memory search while the user is typing.
- Added `background_prefetch_memory` to `src/agent/nodes/memory.py` to handle the new prefetch event and populate `MemoryContextCache`.

### Changed
- Refactored `src/tools/notebook.py` to spawn the new worker process via `subprocess.Popen` instead of executing code in-process. Added `atexit` handlers to prevent zombie processes.
- Refactored `get_safe_workspace_path` in `src/tools/core_tools.py` to explicitly reject path traversal (`..`) and absolute home paths (`~`).
- Updated `docs/STATUS.md` and `docs/PROJECT_OVERVIEW.md` to formally document the migration from Tauri to Electron and confirm the local-only CI strategy.
