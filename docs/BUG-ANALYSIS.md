# Bug Analysis: Browser Audit — OwlynnV2 Full Feature Test

**Date:** 2026-05-25  
**Session:** Browser-based interactive audit of all frontend features  
**Environment:** Backend on port 8000, Frontend on port 5173 (Vite), LM Studio on 1234, Qdrant/Redis via Podman  
**Browser:** Cursor built-in browser

---

## Audit Method

Every user-facing feature was tested interactively through the built-in browser. The backend (`src/api/server.py` line 1-1830) and agent state (`src/agent/state.py`) were reviewed for context. Tests were conducted in "Normal" safe mode with "Auto-approve" execution policy.

---

## Feature Test Matrix

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | WebSocket Connection | PASS | Shows "connected" in inspector header |
| 2 | Workspace Create | PASS | Creates new workspace, switches to it, shows operator note |
| 3 | Workspace Rename | PASS | Inline rename input appears, updates active name |
| 4 | Workspace Delete | PASS* | Deletes successfully but shows wrong operator note (BUG-7) |
| 5 | Workspace Switch | PASS | Falls back to default workspace on delete |
| 6 | Chat Create (+ New) | PASS | Creates new thread, resets conversation |
| 7 | Chat Rename | PASS | Edit/delete buttons appear on chat items |
| 8 | Chat Delete | PASS | Shows confirm dialog, removes from list |
| 9 | Message Send | PASS | Clears input, disables send button |
| 10 | Message Receive | PASS* | Receives response but content is wrong (BUG-1) |
| 11 | Streaming Indicator | PASS | "Thinking..." animation during response |
| 12 | Suggestion Buttons | PASS | Shown in empty state, disabled when disconnected |
| 13 | Composer Enable/Disable | PASS | Disabled when not connected |
| 14 | Operator Note | PASS | Shows contextual messages (new workspace, errors, audit status) |
| 15 | Full/Compact Toggle | PASS | Both modes render correctly |
| 16 | Inspector Overlay | PASS | Opens in compact mode with all panels |
| 17 | Orchestration Panel | FAIL | Empty after message processing (BUG-2) |
| 18 | Memory Panel | FAIL | Shows "Loading..." indefinitely (BUG-3) |
| 19 | Safe Mode Dropdown | FAIL | Depends on Tauri IPC, errors in browser (BUG-5) |
| 20 | Execution Policy Dropdown | UNTESTED | Requires backend interaction |
| 21 | Screen Assist | UNTESTED | Requires Tauri IPC bridge |
| 22 | Tool Execution Filters | PASS | All/Risky/Error buttons clickable |
| 23 | Tool Execution Export | PASS | Shows appropriate message when no data |
| 24 | Tool Exec Audit & Verify | FAIL | Panel doesn't expand (BUG-8) |
| 25 | Action Proposals | PASS | Shows "No pending proposals" correctly |
| 26 | Project Knowledge | PASS | Shows empty state with hint text |
| 27 | Chat Auto-Title | FAIL | Defaults to "New Chat" (BUG-4) |
| 28 | Security Approval | UNTESTED | No security-sensitive tool calls triggered |

---

## Bugs Found

### BUG-1 (CRITICAL): Persona/System Prompt Leaks into First Response

**Symptom:** When sending "Hello, what is 2+2?", the assistant responded with a persona description instead of answering the question:

> "Owlynn (you) is a helpful assistant specializing in programming languages like Python and JavaScript. They provide short, direct answers for common questions such as: How to install dependencies. Best practices for error handling..."

The system prompt/persona text is leaking into the output as if it were the assistant's response.

**Location:** Likely in `src/agent/nodes/simple.py` or `src/agent/nodes/complex.py` — the initial system message may be getting included in the `messages` list incorrectly.

**Severity:** Critical — corrupts the first interaction with every new conversation.

---

### BUG-2 (HIGH): Orchestration Panel Remains Empty After Message Processing

**Symptom:** After the agent processes a message, the Orchestration panel in the inspector shows nothing. The initial "No routing information yet" message disappears, but no routing data (model, route, confidence, source) appears.

**Expected:** Panel should show the model used (e.g., "gemma-4-e2b-heretic-uncensored-mlx"), route ("simple"/"complex-default"), confidence gauge, and source.

**Location:** 
- Backend: `src/api/server.py` line 1388-1404 — `router_info` WebSocket event emission in `on_chain_end` for node `"router"`
- Frontend: `OrchestrationPanel.tsx` — reads `routerMetadata` from store

**Hypothesis:** Either the `router_info` event is not being emitted (router node may not have set `router_metadata` in state), or the frontend store isn't receiving/processing the event correctly.

---

### BUG-3 (HIGH): Memory Panel Shows "Loading..." Indefinitely

**Symptom:** The Memory & Context panel shows "Loading..." and never resolves to show tracked topics, interests, or memory context.

**Expected:** Panel should show tracked topics (from `GET /api/topics`), interests (from `GET /api/interests`), and provide access to Mem0 search and memory context display.

**Location:** Frontend `MemoryPanel.tsx` — the data fetching for topics/interests may be:
1. Failing silently (API returns error)
2. Hanging (no timeout on fetch)
3. Not being triggered at all

---

### BUG-4 (MEDIUM): Chat Auto-Title Defaults to "New Chat"

**Symptom:** When a new chat is created via the first message, the chat title should be auto-generated from the message content (e.g., "Math question" or "2+2 calculation"). Instead, it defaults to "New Chat".

**Location:** `src/api/server.py` lines 1600-1614 — `generate_chat_title_router_llm(user_input[:1000], file_names=file_names)` is wrapped in try/except. On failure, `title` is set to `""`, resulting in "New Chat".

**Hypothesis:** The router LLM for title generation is either:
- Not loaded/available
- Returning an error that's silently caught
- The `generate_chat_title_router_llm` function is failing

---

### BUG-5 (MEDIUM): Safe Mode Dropdown Requires Tauri IPC, No Browser Fallback

**Symptom:** Changing the safe mode from the dropdown produces error: `"Safe Mode error: Cannot read properties of undefined (reading 'invoke')"`. The dropdown visually resets to "Normal" after selection.

**Location:** `SafeModePanel.tsx` — calls `tauriBridge.set_safe_mode()` which invokes `window.__TAURI__` IPC. In browser-only mode, `window.__TAURI__` is undefined.

**Fix:** The SafeModePanel should either:
1. Fall back to a REST API call (`POST /api/advanced-settings`) for mode changes
2. Disable the dropdown in non-Tauri environments with a tooltip explaining it's Tauri-only
3. Use the unified settings endpoint consistently instead of Tauri bridge

---

### BUG-6 (LOW): Tool Execution Panel Shows Mock/Preview Data Permanently

**Symptom:** Even when no tools have been executed in the current session, the Tool Execution panel shows:
- "workspace_search · pending"
- "browser_snapshot · queued"

These appear to be mock/demo entries from the empty state preview.

**Location:** `ToolExecutionPanel.tsx` — the empty state preview renders these as mock entries.

**Fix:** Remove mock entries or conditionally render them only when `toolExecutionHistory.length === 0 && !latestToolExecution`. They should not persist after real tool activity begins.

---

### BUG-7 (LOW): Workspace Delete Shows Wrong Operator Note

**Symptom:** After deleting a workspace (non-default), the operator note reads: `"Chat thread-<uuid> deleted."` instead of something like `"Workspace <name> deleted."` or `"Project deleted."`.

**Location:** `App.tsx` `handleDeleteProject()` — the operator note text references "Chat thread" when it should reference the project/workspace.

---

### BUG-8 (LOW): Audit & Verify Sub-Panel Doesn't Expand

**Symptom:** Clicking the "+ Audit & Verify" button in the Tool Execution panel focuses the button but does not expand the sub-panel containing "Copy verify script", "Signing key", "Signing secret", "Verify bundle", and "Export report" controls.

**Location:** `ToolExecutionPanel.tsx` — the expand/collapse toggle for the audit section may not be wired correctly, or the expanded state is not being set.

---

## Architecture Observations

### Strengths
1. **Clean three-panel layout** with responsive compact/full mode toggle
2. **Real-time WebSocket communication** handles streaming, interrupts, and tool execution events
3. **Comprehensive inspector panels** for debugging (orchestration, memory, tool execution, action proposals)
4. **Audit trail export** with SHA-256 hash chaining and HMAC signing support
5. **Workspace/project isolation** with per-project knowledge bases and chat organization

### Concerns
1. **Tauri dependency leakage** — SafeMode, ScreenAssist, TTS, and window sizing all require Tauri IPC and have no browser-only fallbacks
2. **Silent error handling** — Many try/catch blocks in the frontend swallow errors without logging (e.g., chat title generation, profile updates)
3. **Stale closure patterns** — `useCallback` with complex dependency chains (documented in prior session)
4. **Loading states without timeouts** — Memory panel and orchestration panel have no timeout/error fallback
5. **Mock data in production panels** — Tool Execution panel always shows mock entries regardless of actual tool activity

---

## Recommended Priority Actions

1. **Fix BUG-1 (Persona Leak)** — Critical, affects every new conversation
2. **Fix BUG-2 (Orchestration Panel)** — Core observability feature, needed for debugging
3. **Fix BUG-3 (Memory Loading)** — Core feature, needed for personalization
4. **Fix BUG-5 (Tauri Fallback)** — Blocks Safe Mode in browser deployments
5. **Fix BUG-4 (Chat Titling)** — Quality of life, auto-generated titles improve navigation
6. **Fix BUG-6 (Mock Data)** — Remove demo entries for clean production UI
7. **Fix BUG-7 (Operator Note)** — Correct the delete message text
8. **Fix BUG-8 (Audit Expand)** — Enable the audit verification features
