# Changelog: Fix One-Turn Lag (Message Correlation IDs)

## Task 1: Verify Backend Integration
- Confirmed that `src/api/server.py` accurately accepts `correlation_id` in `GraphSession._execute` and embeds it in all outbound WebSocket JSON payloads via `_send_ws()`. Verified via integration tests.

## Task 2: Verify Frontend Tracking
- Confirmed that `frontend-v2/src/App.tsx` and `protocol.ts` track `pendingCorrelationId`. Mismatched incoming websocket events are effectively ignored to prevent UI lag. Vitest suite passes without issue.

## Task 3: Clean up Patch Scripts
- Deleted residual `patch_server.py`, `patch_frontend.py`, `patch_types.py` files that contained the implementation script for these changes.
