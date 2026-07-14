## 2026-07-14 — Frontier Evaluation & WebSocket Stability Fixes

### What
- Fixed a bug where Semantic Cache hits incorrectly emitted `{"type": "stream"}` and `{"type": "message"}` over the WebSocket. Changed them to standard `chunk` and `assistant.message` events in `src/api/ws/handler.py`.
- Implemented robust timeout cleanup for stale streaming states in `frontend-v2/src/App.tsx`, forcibly clearing `.streaming-cursor` and `.tool-activity-running` elements when correlation IDs go stale (e.g. backend crashes or disconnects).
- Increased backend Uvicorn startup timeout in `scripts/run_local_frontier_eval.py` from 15s to 60s to accommodate slower MCP server connection initializations.
- Added a 5-second `ws_idle` fallback timeout inside `wait_for_turn_complete` in `scripts/run_local_frontier_eval.py` to prevent infinite DOM polling loops when an `assistant.message` fails to arrive (e.g., during a graph execution error).

### Why
These fixes address severe evaluation harness and UI desynchronization issues:
- Cached responses were completely invisible to the frontend and eval script because of event type mismatches, resulting in infinite waits and 0/100 grades on cache hits.
- If the backend restarted or failed to complete a response cleanly, the frontend UI would remain stuck in a "generating" state infinitely, completely locking up the `wait_for_turn_complete` DOM evaluation.
- The evaluation suite (`scripts/run_local_frontier_eval.py`) is now resilient to backend startup races and silent graph failures, ensuring that benchmark scores (currently restored to 91.32%) accurately reflect LLM capability rather than infrastructure flakiness.

### Files
- `src/api/ws/handler.py`
- `frontend-v2/src/App.tsx`
- `scripts/run_local_frontier_eval.py`
