# Bug Analysis: Workspace Creation & Chat Display Issues

**Date:** 2026-05-23
**Session:** Debug session 03f428

---

## Symptoms Reported

1. **"Failed to create workspace"** — Error shown when attempting to create a new workspace/project
2. **"Chats did not appear on General Workspace but the conversation working fine"** — Chats are not visible in the sidebar for the "General Workspace" (default project), even though the WebSocket conversation proceeds normally

---

## Architecture Overview

```
┌─────────────────────┐     HTTP/WebSocket     ┌──────────────────────┐
│   Vite React App     │ ◄────────────────── ► │  FastAPI Backend      │
│   (port 5173)        │                       │  (port 8000)          │
│                      │   Vite proxy:          │                       │
│  App.tsx             │   /api → :8000         │  server.py            │
│  ├─ handleCreateProject()                     │  ├─ POST /api/projects│
│  ├─ handleSend()      │                       │  ├─ GET  /api/projects│
│  ├─ loadProjects()    │                       │  ├─ POST /api/projects│
│  └─ projectThreadsRef │                       │  │   /{id}/chats      │
│                      │                       │  └─ WS  /ws/chat/{id} │
└─────────────────────┘                       └──────┬───────────────┘
                                                      │
                                                     ▼
                                          ┌──────────────────────┐
                                          │  project_manager      │
                                          │  (project.py)         │
                                          │                       │
                                          │  ── data/projects.json│
                                          │    {                  │
                                          │     "default": {      │
                                          │       id: "default",  │
                                          │       name: "General  │
                                          │         Workspace",   │
                                          │       chats: [...]    │
                                          │     },                │
                                          │     "<uuid>": {...}   │
                                          │    }                  │
                                          └──────────────────────┘
```

---

## Bug 1: "Failed to create workspace"

### Code Location

**Frontend:** `frontend-v2/src/App.tsx` lines 463-485

```typescript
const handleCreateProject = useCallback(async (projectName: string) => {
    const trimmedName = projectName.trim()
    if (!trimmedName) return
    try {
      const response = await fetch('/api/projects', {       // ← Step 1: POST
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmedName }),
      })
      if (!response.ok) throw new Error('create failed')    // ← Step 2: check
      const created = (await response.json()) as ProjectCreateResponse
      const newThreadId = makeThreadId()
      projectThreadsRef.current = { ...projectThreadsRef.current, [created.id]: newThreadId }
      clearSession()
      setActiveProjectId(created.id)                         // ← Step 3: React state set
      setCurrentThreadId(newThreadId)
      setActiveChatId(newThreadId)
      setOperatorNote('Switched to new workspace.')
      await loadProjects()                                   // ← Step 4: refresh
    } catch {
      setOperatorNote('Failed to create workspace.')         // ← Step 5: silent catch-all
    }
  }, [clearSession, loadProjects])
```

**Backend:** `src/api/server.py` lines 561-565 → `src/memory/project.py` lines 114-129

### Hypothesis A1 — Network/fetch error (HIGH PROBABILITY)

**Mechanism:** The `catch` block in `handleCreateProject` swallows ALL errors. When running in Tauri dev mode on macOS, the Tauri application's WebView may have different network capabilities than a browser:

- Tauri uses a custom WebView (WKWebView on macOS) which may block localhost requests differently
- The API runs at `http://127.0.0.1:8000` but Tauri may route localhost differently
- In Tauri context, `isTauriRuntime = true`, but the `fetch('/api/projects')` path is RELATIVE — it relies on Vite's proxy to forward to port 8000. But Tauri may serve from a different origin that doesn't proxy `/api/*`.

**Evidence:** The terminal log from `909937.txt` shows the frontend WAS able to connect via Vite proxy (HMR working), but also shows ECONNREFUSED errors for `/api/projects` when the backend was down. In Tauri production/dev, the frontend may not be served by Vite's dev server but directly by Tauri's WebView, so Vite proxy is bypassed.

**How to verify:**
```javascript
// In handleCreateProject, add logging before the try/catch:
console.log('[create] isTauriRuntime:', isTauriRuntime, 'apiBase:', apiBase)
// And use apiUrl() instead of relative paths:
const url = apiUrl('/api/projects')
```

### Hypothesis A2 — Backend UUID collision or `get_project_workspace` crash (LOW PROBABILITY)

**Mechanism:** `project_manager.create_project()` calls `get_project_workspace(pid)` at line 128 of `project.py`. This creates the workspace directory via `Path.mkdir()`. On macOS, if there are filesystem permission issues or the path is invalid, this could fail with an OSError, propagating back to the FastAPI endpoint as a 500 error, which triggers `!response.ok`.

**How to verify:** Check backend logs for any exceptions during project creation. Also check that `WORKSPACE_DIR/projects/<id>/` is being created successfully.

### Hypothesis A3 — `loadProjects()` throws after successful creation (MEDIUM PROBABILITY)

**Mechanism:** Even if the POST succeeds, `loadProjects()` is called afterward. If `loadProjects()` fails (e.g., the GET `/api/projects` returns an error), the catch-all handler shows "Failed to create workspace." — even though the project WAS created successfully on the backend.

**Evidence:** The data file `data/projects.json` already contains 4 projects (default, tws, TestCreate, ViteProxyTest), so creation works sometimes. The `TestCreate` and `ViteProxyTest` projects have empty `chats` arrays, suggesting they were created via the UI but never used.

**How to verify:** Check `data/projects.json` after a "Failed to create workspace" error — if the project exists in the JSON, the error is in `loadProjects()`.

### Hypothesis A4 — React stale closure race in `loadProjects` (MEDIUM PROBABILITY)

**Mechanism:** `loadProjects` is a `useCallback` with dependencies `[activeProjectId, currentThreadId]`. When `handleCreateProject` runs:

1. `setActiveProjectId(created.id)` — React state update (batched, not immediate)
2. `await loadProjects()` — calls the current closure of `loadProjects`, which still captures OLD `activeProjectId`

Since `loadProjects` checks whether `activeProjectId` exists in loaded projects:
```typescript
const activeExists = mapped.some((project) => project.id === activeProjectId)
```
If `activeProjectId` is still `"default"` (stale), it enters the `else` branch and auto-switches to the latest chat of the "default" project — potentially overriding the state updates that `handleCreateProject` just made. While this wouldn't throw, it causes confusing state. Combined with potential fetch errors, it degrades the experience.

**How to verify:** Add console.log to `loadProjects` to see what `activeProjectId` is at call time.

### Hypothesis A5 — `generate_chat_title_router_llm` crash in WebSocket (VERY LOW PROBABILITY)

The chat title generation is wrapped in `try/except` at server.py line 1588-1591, so it shouldn't crash. But worth noting.

---

## Bug 2: "Chats did not appear on General Workspace"

### Data Evidence

The `data/projects.json` file shows:
```json
"default": {
    "id": "default",
    "name": "General Workspace",
    "chats": [{
        "id": "thread-2658ab49-571a-45bf-a90e-cf93c6e8bc77",
        "name": "New Chat",
        "created_at": 1779553952.387603
    }],
}
```

So the chat IS registered on the backend. The problem is on the **frontend**.

### Code Location

**Chat registration (backend):** `src/api/server.py` lines 1584-1599
```python
# On first user message in a thread, register the chat in the project
if thread_id not in sessions or not sessions[thread_id].event_buffer:
    chat_id = thread_id
    ...
    project_manager.add_chat_to_project(project_id, {
        "id": chat_id,
        "name": title or "New Chat",
        "created_at": time_module.time(),
    })
```

**Frontend listing:** `loadProjects()` in `frontend-v2/src/App.tsx` lines 72-125

### Hypothesis B1 — Race condition: frontend `loadProjects()` before backend registers chat (HIGH PROBABILITY)

**Mechanism:** In `handleSend()` (line 330-346):
```typescript
wsClientRef.current?.send({
    type: 'user.message',
    ...
    project_id: activeProjectId,
})
void loadProjects()   // ← called IMMEDIATELY after WS send
```

The backend processes the WebSocket message **asynchronously**. The chat is registered during message processing (line 1584-1599). When `loadProjects()` is called right after `wsClientRef.current?.send()`, the WebSocket message hasn't reached the backend yet or hasn't been processed, so the chat isn't registered yet. The `GET /api/projects` returns before the chat is added.

**Timing:**
```
Frontend                          Backend
  │                                 │
  ├─ WS.send(message) ────────────► │ (async receive)
  ├─ fetch('/api/projects') ──────► │ GET /api/projects
  │   ◄── returns without chat ─── │ (chat not registered yet)
  │                                 │ ← process WS message
  │                                 │ ← register chat in projects.json
```

**However:** The `assistant.message` event handler (line 221) also calls `loadProjectsRef.current()`, so the second call should pick up the chat. But this depends on timing too.

### Hypothesis B2 — Thread ID mismatch between frontend and backend (HIGH PROBABILITY)

**Mechanism:**
- Initial `currentThreadId` is `'default'` (from `useState('default')` on line 63)
- Initial `activeChatId` is `'default'` (same line)
- When the app first loads, WebSocket connects to `ws://.../ws/chat/default`
- The backend uses `thread_id = "default"` for LangGraph state
- When `handleSend` is called, the message goes to the `"default"` WebSocket
- **BUT**: `handleNewChat()` (line 396) creates a NEW `thread-<uuid>` and only updates local state — it does NOT trigger chat registration on the backend

The backend's `add_chat_to_project` registers the chat with `chat_id = thread_id`. But the frontend uses `currentThreadId` which initially is `"default"`. So:

1. User opens app → WebSocket connects to `/ws/chat/default`
2. User types first message → backend registers chat with `id = "default"` in projects.json
3. User creates a "New Chat" → frontend creates `thread-xxx`, reconnects WebSocket to `/ws/chat/thread-xxx`
4. Backend registers a NEW chat with `id = "thread-xxx"` 
5. But `loadProjects()` determines chat display based on `activeChatId` matching

This could cause the **chat list not reflecting the actual conversation**.

### Hypothesis B3 — `loadProjects()` auto-switch logic resets chat state (MEDIUM PROBABILITY)

**Mechanism:** In `loadProjects()` lines 106-117:
```typescript
const activeProject = mapped.find((p) => p.id === activeProjectId)
if (activeProject && activeProject.chats.length > 0) {
    const currentExists = currentThreadId && activeProject.chats.some((c) => c.id === currentThreadId)
    if (!currentExists) {
        projectThreadsRef.current[activeProjectId] = currentThreadId  // keeps old value
    } else {
        const sorted = [...activeProject.chats].sort(...)
        const latestChatId = sorted[0].id
        projectThreadsRef.current[activeProjectId] = latestChatId
        setCurrentThreadId(latestChatId)     // auto-switches!
        setActiveChatId(latestChatId)        // auto-switches!
    }
}
```

When `currentThreadId` starts as `"default"` and the registered chat id is `"thread-xxx"`:
- `currentExists` = false (no chat with id `"default"`)
- The `!currentExists` branch executes, keeping the stale `currentThreadId`
- But the backend's thread_id is the WebSocket path, which IS `"default"` on initial connection

This logic is fragile — it auto-switches the active chat based on the latest chat, which can disorient the user and cause the chat list to appear out of sync.

### Hypothesis B4 — `activeChatId` misalignment with WebSocket thread (MEDIUM PROBABILITY)

**Mechanism:** The WebSocket connects to `/ws/chat/{currentThreadId}`, but `activeChatId` may not match `currentThreadId` after `loadProjects()` auto-switches. This means:
- Messages are sent on one thread but displayed as if on another
- Chats in the sidebar reflect project registration but don't align with active conversation

---

## Summary of Interactions

Both bugs may stem from the same root cause: **improper state management across WebSocket reconnections and React stale closures**.

```
Problem cascade:
  1. State initialized with magic string "default" as thread ID
  2. loadProjects() depends on activeProjectId/currentThreadId via useCallback closure
  3. handleCreateProject() calls loadProjects() with potentially stale activeProjectId
  4. WebSocket sends project_id but thread_id comes from URL path, not payload
  5. Chat registration is asynchronous and races with loadProjects()
  6. loadProjects() auto-switches active chat, fighting with manual user navigation
```

---

## Recommended Fixes (Priority Order)

### Fix 1: Instrument error handling to determine actual cause
Add detailed error logging to `handleCreateProject` instead of the silent catch-all.

### Fix 2: Fix the stale closure in `loadProjects`
- Use refs for `activeProjectId` and `currentThreadId` inside `loadProjects`, or
- Remove these from the `useCallback` dependency array and read them from refs

### Fix 3: Fix the race in chat registration
- Add the chat to the project BEFORE responding to the WebSocket, not during processing, or
- Move the `loadProjects()` call in `handleSend` to the `assistant.message` event handler (it's already there at line 221, possibly redundant)

### Fix 4: Eliminate "default" as thread ID
- Initialize `currentThreadId` with a proper UUID instead of the magic string "default"
- This avoids collision with project IDs and makes thread IDs truly unique

### Fix 5: Send `chat_id` explicitly in WebSocket messages
- Currently, thread_id is embedded in the WS URL path. Instead, send it in the message payload for clarity and consistency.

### Fix 6: Separate project/chat navigation from auto-switch logic
- `loadProjects()` should only update the project/chat LIST, not auto-navigate
- Navigation should be a separate, explicit user action
