---
status: archived
category: audit
last_updated: 2026-06-10
owner: human
audience: archive
---

# Bug Analysis: Browser Audit — OwlynnV2 Full Feature Test

> **Purpose:** Historical record of the 2026-05-25 browser audit findings. **Agents:** use [`docs/BUG-TRACKER.md`](BUG-TRACKER.md) for fix details and [`docs/STATUS.md`](STATUS.md) for current open work.

> **Resolution:** All BUG-1 through BUG-8 from this audit are **FIXED** (verified 2026-05-30). See [`docs/BUG-TRACKER.md`](BUG-TRACKER.md). File-intake bugs BUG-9 through BUG-11 are documented in STATUS.md and BUG-TRACKER.md.

**Date:** 2026-05-25  
**Session:** Browser-based interactive audit of all frontend features  
**Environment:** Backend on port 8000, Frontend on port 5173 (Vite), LM Studio on 1234, Qdrant/Redis via Podman  
**Browser:** Cursor built-in browser

---

## Audit Method

Every user-facing feature was tested interactively through the built-in browser. The backend (`src/api/server.py`) and agent state (`src/agent/state.py`) were reviewed for context. Tests were conducted in "Normal" safe mode with "Auto-approve" execution policy.

---

## Feature Test Matrix

| # | Feature | Status (at audit) | Resolution | Notes |
|---|---------|-------------------|------------|-------|
| 1 | WebSocket Connection | PASS | — | Shows "connected" in inspector header |
| 2 | Workspace Create | PASS | — | Creates new workspace, switches to it, shows operator note |
| 3 | Workspace Rename | PASS | — | Inline rename input appears, updates active name |
| 4 | Workspace Delete | PASS* | FIXED (BUG-7) | Wrong operator note at audit time |
| 5 | Workspace Switch | PASS | — | Falls back to default workspace on delete |
| 6 | Chat Create (+ New) | PASS | — | Creates new thread, resets conversation |
| 7 | Chat Rename | PASS | — | Edit/delete buttons appear on chat items |
| 8 | Chat Delete | PASS | — | Shows confirm dialog, removes from list |
| 9 | Message Send | PASS | — | Clears input, disables send button |
| 10 | Message Receive | PASS* | FIXED (BUG-1) | Wrong content at audit time (persona leak) |
| 11 | Streaming Indicator | PASS | — | "Thinking..." animation during response |
| 12 | Suggestion Buttons | PASS | — | Shown in empty state, disabled when disconnected |
| 13 | Composer Enable/Disable | PASS | — | Disabled when not connected |
| 14 | Operator Note | PASS | — | Shows contextual messages |
| 15 | Full/Compact Toggle | PASS | — | Both modes render correctly |
| 16 | Inspector Overlay | PASS | — | Opens in compact mode with all panels |
| 17 | Orchestration Panel | FAIL | FIXED (BUG-2) | Empty after message processing at audit time |
| 18 | Memory Panel | FAIL | FIXED (BUG-3) | "Loading..." indefinitely at audit time |
| 19 | Safe Mode Dropdown | FAIL | FIXED (BUG-5) | Desktop IPC error in browser at audit time |
| 20 | Execution Policy Dropdown | UNTESTED | — | Requires backend interaction |
| 21 | Screen Assist | UNTESTED | — | Requires Electron IPC bridge |
| 22 | Tool Execution Filters | PASS | — | All/Risky/Error buttons clickable |
| 23 | Tool Execution Export | PASS | — | Shows appropriate message when no data |
| 24 | Tool Exec Audit & Verify | FAIL | FIXED (BUG-8) | Panel didn't expand at audit time |
| 25 | Action Proposals | PASS | — | Shows "No pending proposals" correctly |
| 26 | Project Knowledge | PASS | — | Shows empty state with hint text |
| 27 | Chat Auto-Title | FAIL | FIXED (BUG-4) | Defaulted to "New Chat" at audit time |
| 28 | Security Approval | UNTESTED | — | No security-sensitive tool calls triggered |

---

## Bugs Found (historical symptoms)

Symptoms below are preserved for context. Fixes are in [`docs/BUG-TRACKER.md`](BUG-TRACKER.md).

### BUG-1 (CRITICAL): Persona/System Prompt Leaks into First Response — FIXED

**Symptom (2026-05-25):** First message echoed persona text instead of answering (e.g. "Hello, what is 2+2?" → identity description).

**Location:** `src/agent/nodes/simple.py`, `src/agent/nodes/complex.py`

---

### BUG-2 (HIGH): Orchestration Panel Remains Empty — FIXED

**Symptom (2026-05-25):** No routing data after message processing.

**Location:** `src/api/ws/handler.py`, `frontend-v2/src/components/OrchestrationPanel.tsx`

---

### BUG-3 (HIGH): Memory Panel Shows "Loading..." Indefinitely — FIXED

**Symptom (2026-05-25):** Panel never resolved topics/interests.

**Location:** `frontend-v2/src/components/MemoryPanel.tsx`

---

### BUG-4 (MEDIUM): Chat Auto-Title Defaults to "New Chat" — FIXED

**Symptom (2026-05-25):** Title not auto-generated from first message.

**Location:** `src/agent/nodes/router.py` (`generate_chat_title_router_llm`)

---

### BUG-5 (MEDIUM): Safe Mode Dropdown Requires Desktop IPC — FIXED

**Symptom (2026-05-25):** `"Cannot read properties of undefined (reading 'invoke')"` in browser.

**Location:** `frontend-v2/src/lib/electronBridge.ts`, `frontend-v2/src/components/SafeModePanel.tsx`

---

### BUG-6 (LOW): Tool Execution Panel Shows Mock/Preview Data — FIXED

**Symptom (2026-05-25):** Stale mock entries visible with no tool activity.

**Location:** `frontend-v2/src/App.tsx`, `frontend-v2/src/components/ToolExecutionPanel.tsx`

---

### BUG-7 (LOW): Workspace Delete Shows Wrong Operator Note — FIXED

**Symptom (2026-05-25):** Note said "Chat thread deleted" instead of workspace deleted.

**Location:** `frontend-v2/src/App.tsx` `handleDeleteProject()`

---

### BUG-8 (LOW): Audit & Verify Sub-Panel Doesn't Expand — FIXED

**Symptom (2026-05-25):** "+ Audit & Verify" button did not expand sub-panel.

**Location:** `frontend-v2/src/components/ToolExecutionPanel.tsx`

---

## Architecture Observations (at audit time)

### Strengths
1. Clean three-panel layout with responsive compact/full mode toggle
2. Real-time WebSocket communication
3. Comprehensive inspector panels
4. Audit trail export with SHA-256 hash chaining
5. Workspace/project isolation

### Concerns (mitigated where noted)
1. **Desktop IPC dependency** — BUG-5 fixed REST fallback for Safe Mode; Screen Assist still Electron-only
2. **Silent error handling** — partially addressed in BUG-3/BUG-4 (still a general concern; see STATUS.md)
3. **Loading states without timeouts** — mitigated by BUG-3 (error + retry UI)
4. **Mock data in tool panel** — mitigated by BUG-6

---

## Related

- [`docs/BUG-TRACKER.md`](BUG-TRACKER.md) — root cause, fixes, verification (BUG-1..11)
- [`docs/STATUS.md`](STATUS.md) — current risks and remaining tasks (R3, R5, R7, R9)
- [`docs/audit-file-intake-2026-05-30.md`](audit-file-intake-2026-05-30.md) — source audit for BUG-9..11

## Last updated

2026-06-10 — marked historical; added resolution column; all BUG-1..8 fixed per BUG-TRACKER
