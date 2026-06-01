---
status: active
category: debugging
last_updated: 2026-05-31
owner: human
---

# Debugging: Frontend

> **Purpose:** Debugging guide for frontend UI and component issues.


**Quick Reference:** React 19 + TypeScript (Vite 8). Zustand 5 state management. WebSocket streaming via `frontend-v2/src/lib/wsClient.ts`. Key files: `frontend-v2/src/state/useAppStore.ts`, `frontend-v2/src/lib/wsClient.ts`, `frontend-v2/src/App.tsx`, `frontend-v2/src/components/*.tsx`.

## Common Failure Modes

| Symptom | Likely Cause | Diagnostic | Fix |
|---------|-------------|-----------|-----|
| Blank screen / white page | Build error or runtime JS exception | Check browser DevTools Console + Network tab | Fix build errors (`npm run build`), check for JS exceptions |
| `npm run build` fails | TypeScript errors or missing deps | `npx tsc --noEmit` | Fix TS errors, `npm install` |
| `vitest` fails | Test regression or missing polyfills | `npx vitest run` output | Fix failing tests; check `vitest.config.ts` for polyfills |
| WebSocket reconnection loop | Backend down or wsClient retry logic | Browser DevTools → Network → WS tab | Fix backend (see [backend-api.md](backend-api.md)), check wsClient retry config |
| Messages not appearing | WS event type mismatch or state not updating | Check WS messages in DevTools, check store setters | Verify event types match `protocol.ts` |
| Orchestration panel empty (BUG-2) | `router_info` event not emitted or not processed | See dedicated section below | See dedicated section below |
| Memory panel "Loading..." (BUG-3) | REST fetch hangs or errors | See [memory.md](memory.md) frontend section | See [memory.md](memory.md) |
| Safe Mode dropdown errors (BUG-5) | Tauri IPC unavailable in browser | Browser Console shows `Cannot read properties of undefined (reading 'invoke')` | See [tauri-desktop.md](tauri-desktop.md) |
| Stale UI after workspace switch | Store not resetting on project change | Check `useAppStore` project-switch logic | Force store reset on project switch |
| Component re-render storms | Missing useCallback/useMemo or stale closure | React DevTools Profiler | Add memoization, fix dependency arrays |
| Zustand state desync | Multiple store updates racing | React DevTools → inspect store state | Audit action dispatch order, use middleware |

## Diagnostic Commands

### Build & Lint

```bash
# TypeScript check
cd frontend-v2 && npx tsc --noEmit

# Production build
cd frontend-v2 && npm run build

# Run all tests
cd frontend-v2 && npx vitest run

# Run specific test file
cd frontend-v2 && npx vitest run src/__tests__/wsClient.test.ts

# Lint (if configured)
cd frontend-v2 && npm run lint 2>/dev/null || echo "No lint script configured"
```

### Browser DevTools Checks

1. **Console**: Check for JS errors, unhandled promise rejections, Tauri IPC `undefined` errors.
2. **Network → WS tab**: Select the WebSocket connection, inspect sent/received frames.
   - Expected: First frame from client is a JSON chat message. Server responds with `status`, `chunk`, `router_info`, `model_info`, `message` events.
   - If no frames appear: WebSocket not connecting. See [backend-api.md](backend-api.md) Procedure 2.
3. **Application → Local Storage / Session Storage**: Check for persisted state.
4. **React DevTools**: Inspect component tree, check Zustand store values.

### Zustand Store Snapshot

```javascript
// Paste in browser console while app is running
// Expose store for debugging (if not already exposed)
// Check useAppStore.ts for __ZUSTAND_DEVTOOLS__ or window.__store__

// Alternative: check via React DevTools → Components → select AppShell → hooks → useStore
```

### WebSocket Frame History

In browser DevTools → Network → WS tab:
- Green arrows (↑) = client → server
- Red arrows (↓) = server → client

Expected message sequence for a normal chat:
```
↑ {"message":"Hello","files":[],...}
↓ {"type":"status","content":"reasoning"}
↓ {"type":"router_info","metadata":{...}}
↓ {"type":"chunk","content":"He","metadata":{...}}
↓ {"type":"chunk","content":"llo","metadata":{...}}
...more chunks...
↓ {"type":"model_info","model":"small",...}
↓ {"type":"status","content":"idle"}
↓ {"type":"message","message":{...}}
```

## Bug-Specific Debugging

### BUG-2: Orchestration Panel Empty After Message

**Location:** `frontend-v2/src/components/OrchestrationPanel.tsx` reads `routerMetadata` from store. Backend emits `router_info` event in `src/api/server.py` via `forward_events()` → `on_chain_end` for `router` node.

**Debug steps:**

1. Check if `router_info` event is emitted:
   - Open browser DevTools → Network → WS tab
   - Send a message
   - Look for a frame with `"type":"router_info"` from server → client
   - If absent: backend issue. Check `src/api/server.py` `forward_events()` function, verify `router_metadata` is set in `AgentState`.

2. Check if frontend receives the event:
   - In `App.tsx`, the WS `message` handler should dispatch to store based on `event.type`
   - Verify `case 'router_info':` is handled and calls the store setter

3. Check store state:
   - React DevTools → inspect Zustand store
   - Look for `routerMetadata` field
   - If `null` or `undefined`: the setter is not being called or called with wrong data

4. Check panel render logic:
   - `OrchestrationPanel.tsx` should conditionally render based on `routerMetadata`
   - If `routerMetadata` is populated but panel shows empty: rendering condition is wrong

### BUG-6: Tool Execution Mock Data

**Location:** `frontend-v2/src/components/ToolExecutionPanel.tsx`

**Debug steps:**

1. Check if mock entries are in the component source (hardcoded JSX) or in initial store state.
2. The panel should only show mock entries when `toolExecutionHistory.length === 0`.
3. If mock data persists after real tool activity, the history array is not being populated.

### BUG-8: Audit & Verify Sub-Panel Won't Expand

**Location:** `frontend-v2/src/components/ToolExecutionPanel.tsx`

**Debug steps:**

1. Check the expand/collapse state variable. Is the click handler toggling it?
2. Check if state is controlled by a React `useState` that's local to the component.
3. Verify the click handler is bound to the correct element (button vs wrapper div).
4. Check CSS: the expanded content may be rendering but hidden by `display: none` or `max-height: 0`.

## Step-by-Step Procedures

### Procedure 1: Blank Screen / Build Failure

1. Check the build output:
   ```bash
   cd frontend-v2 && npm run build 2>&1 | tail -30
   ```
   Expected: `✓ built in X.XXs` with no errors.

2. If TypeScript errors: fix them based on the error messages. Check:
   - Missing imports
   - Type mismatches in `protocol.ts` vs actual WS event payloads
   - Stale type definitions

3. If `node_modules` issues:
   ```bash
   rm -rf frontend-v2/node_modules frontend-v2/package-lock.json
   cd frontend-v2 && npm install
   ```

4. Check Vite config:
   ```bash
   cat frontend-v2/vite.config.ts
   ```
   Ensure proxy/dev server settings are correct.

### Procedure 2: WebSocket Reconnection Loop

1. Check browser DevTools → Console for repeated connection attempts.
2. Verify backend is running: `curl http://127.0.0.1:8000/docs`
3. Check `wsClient.ts` for retry logic:
   - Default reconnect delay?
   - Max retries?
   - Exponential backoff configuration?
4. If backend is up but reconnecting, check for auth/CORS issues (see [backend-api.md](backend-api.md)).
5. To break the loop temporarily: close the browser tab and restart both backend and frontend.

### Procedure 3: Frontend Tests Failing

1. Run all tests:
   ```bash
   cd frontend-v2 && npx vitest run 2>&1
   ```

2. For failing tests, check:
   - **Missing browser API polyfills**: `vitest.config.ts` setup file must polyfill `crypto.subtle`, `URL.createObjectURL`, `navigator.clipboard` for jsdom.
   - **Component test props**: Components that accept `bridge` prop need it in tests (Tauri globals unavailable in jsdom).
   - **WebSocket mocks**: Tests that import `wsClient` may need mocking.

3. Run a single failing test file:
   ```bash
   cd frontend-v2 && npx vitest run src/__tests__/<failing-file>.test.ts
   ```

4. If tests pass locally but fail in CI:
   ```bash
   ./scripts/ci.sh --quick
   ```

## Known Fixes

- **WebSocket transport regression tests**: Added in Phase 1 — tests cover malformed JSON, lifecycle callbacks, send-gating, disconnect cleanup. See [STATUS.md](../STATUS.md).
- **Component testability**: Components refactored to accept optional `bridge` prop for testing without Tauri globals.
- **Browser API polyfills**: `vitest.config.ts` setup file provides `crypto.subtle`, `URL.createObjectURL`, `navigator.clipboard`.
- **Stale closure patterns**: Known concern from browser audit — `useCallback` with complex dependency chains. See [BUG-ANALYSIS.md](../BUG-ANALYSIS.md) section "Concerns".
- **Silent error handling**: Known concern — multiple try/catch blocks swallow errors in chat title generation, profile updates. See [BUG-ANALYSIS.md](../BUG-ANALYSIS.md).

## Related

- [`docs/debugging/README.md`](README.md) — debugging index

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
