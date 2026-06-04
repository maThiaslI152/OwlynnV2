# Design: Fix One-Turn Lag (Message Correlation IDs)

> **Slug:** `fix-one-turn-lag`

## 1. Architecture

We will implement an envelope-level correlation ID pattern over our WebSockets. The backend LangGraph flow itself will NOT be aware of these IDs (to keep our agent framework decoupled from networking). Instead, the WebSocket translation layers will manage it.

## 2. Component Changes

### Backend (`src/api/server.py`)

1. **`GraphSession._execute`**:
   - Update signature to accept `correlation_id`.
   - Store events as a tuple: `(event, correlation_id)`.
   - Propagate to `self.event_buffer` and the listener queues.
2. **`websocket_endpoint` / `forward_events`**:
   - Extract `correlation_id` from the queue item.
   - Inject `"correlation_id": correlation_id` into the JSON payload before `await websocket.send_json(payload)`.
   - Pass `payload.get("correlation_id")` to `session.start_run(...)` when receiving messages.

### Frontend (`frontend-v2/src/App.tsx`, `frontend-v2/src/types/protocol.ts`)

1. **Types**: Add `correlation_id?: string` to all relevant event interfaces (e.g., `UserMessageEvent`, `SecurityApprovalClientEvent`, `AskUserResponseClientEvent`).
2. **Store (`useAppStore`)**: Add `pendingCorrelationId: string | null`.
3. **Dispatching**:
   - On `handleSend()`, set `pendingCorrelationId = message.id` and send it.
   - On HITL actions (`handleHitlApprove`, `handleHitlDecline`, `handleHitlSelectChoice`, `handleHitlSkip`), generate a new `crypto.randomUUID()`, set it as pending, and send it.
4. **Receiving (`wsClient.onEvent`)**:
   - If `event.correlation_id` exists and doesn't match `pendingCorrelationId`, drop the event early (prevents UI overlap/lag bugs).
   - If `event.type === 'status' && event.content === 'idle'`, clear `pendingCorrelationId`.

## 3. Risks & Edge Cases

- **Silent Drops**: If the server resolves an old request after we've started a new one, its results will be totally invisible. This is intentional to prevent "lag" overlap, but makes debugging harder. We will add a `console.debug("Ignoring mismatched correlation id")` to make it traceable.

---
## Approval

- `design-review` AskQuestion: approved (2026-06-04)
