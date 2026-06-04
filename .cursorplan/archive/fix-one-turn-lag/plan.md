# Plan: Fix One-Turn Lag (Message Correlation IDs)

## 1. Goal
Eliminate the "One-Turn Lag" concurrency bug by introducing message correlation IDs into the WebSocket protocol.

## 2. Architecture
- **Backend (`src/api/server.py`)**: `GraphSession._execute` modified to accept `correlation_id` and attach to all yielded events. `_send_ws` ensures the ID is packed in the JSON payload.
- **Frontend (`frontend-v2/src/App.tsx`, `frontend-v2/src/types/protocol.ts`)**: Generates ID (`pendingCorrelationId`) on request. Ignores WS events with mismatched IDs.

## 3. Tasks
- **Task 1**: Verify Backend Integration. Run existing tests to ensure `correlation_id` injection is active.
- **Task 2**: Verify Frontend Tracking. Run `vitest` tests.
- **Task 3**: Clean up leftover `patch_server.py`, `patch_frontend.py`, `patch_types.py` files.
