# Requirements: Fix One-Turn Lag (Message Correlation IDs)

> **Slug:** `fix-one-turn-lag`

## 1. Goal

Eliminate the "One-Turn Lag" concurrency bug by introducing message correlation IDs into the WebSocket protocol. This ensures that frontend UI state always correctly associates backend stream events with the exact prompt that triggered them, preventing delayed responses or concurrent message races from corrupting the chat interface.

## 2. Acceptance Criteria (AC)

- **AC-1:** Every user message payload sent over WebSocket MUST include a unique `correlation_id`.
- **AC-2:** The `GraphSession` backend MUST capture the `correlation_id` when executing a run, attach it to the `event_buffer`, and stream it back to the client in ALL resulting ServerEvents (tool calls, stream chunks, status updates).
- **AC-3:** The frontend MUST maintain a `pendingCorrelationId` state that tracks the active request.
- **AC-4:** The frontend MUST gracefully ignore or handle any incoming `ServerEvent` that contains a `correlation_id` distinct from the active `pendingCorrelationId`.
- **AC-5:** HITL (Human-in-the-Loop) events (approval, feedback, skipped) MUST also inject their own `correlation_id` to prevent async mismatches when interacting with popups.
- **AC-6:** The patch files left by previous AI sessions (`patch_server.py`, `patch_frontend.py`, `patch_types.py`) MUST be deleted from the repository root to ensure a clean codebase.

## 3. Scope & Constraints

- **Scope:** Broad/Optimized. We must ensure ALL paths (User messages, HITL interactions) are covered by the correlation ID tracking, not just standard text messages.
- **Constraints:** We must not break the existing LangGraph streaming event structure. The `correlation_id` must be appended as an envelope field inside the WebSocket transmission layer (`_send_ws`), keeping the core agent logic unaware of network transport details.

---
_Status: Pending Review_

## Approval

- `requirements-review` AskQuestion: approved (2026-06-04)
