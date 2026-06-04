# Verification Report: Fix One-Turn Lag (Message Correlation IDs)

> **Slug:** `fix-one-turn-lag`
> **Date:** 2026-06-04

## Verification Results

| AC ID | Verification Step | Status | Evidence |
|-------|-------------------|--------|----------|
| AC-1, AC-3, AC-4, AC-5 | `npm run test` in `frontend-v2` | Passed | Vitest suite successfully passed. The frontend code maintains `pendingCorrelationId` via Zustand and correctly ignores events with mismatched correlation IDs. |
| AC-2 | `.venv/bin/pytest tests/test_websocket_event_contract.py` | Passed | Backend `GraphSession` properly propagates correlation IDs to WebSocket payloads via the `_send_ws` decorator. |
| AC-6 | Manual check | Passed | Residual `.py` patch scripts deleted. |

## Impact Summary

- **Reliability:** The UI will no longer randomly mix up old delayed AI stream events with the active prompt stream, effectively mitigating the "One-Turn Lag" concurrency UI defect.
- **Traceability:** Mismatched messages are dropped from rendering but explicitly logged (`console.debug`) on the frontend to allow debugging without disrupting UX.
- **Regressions:** None observed.

## Sign-off

Ready to archive to `specs/completed/`.
