---
status: active
category: planning
last_updated: 2026-06-26
owner: ai-agent
audience: human
---

# docs/FUTURE_WORKS.md — Prioritized Roadmap & Future Works

> **Purpose:** Detailed breakdown of remaining architectural concerns and future priorities following the completion of Phase 8 bug fixes.

While the major known bugs are squashed, the project's `STATUS.md` outlines several remaining architectural concerns. Here they are ordered strictly by priority:

## 🔴 P0: Critical Verification & Reliability

1. **Fix F5.1 WS Event Loss (Frontend Idle State Bug)** — ✅ Mostly Fixed
   - **Why:** The frontend's `pendingCorrelationId` is never cleared when `status: idle` WS event is lost. This causes `.composer-stop` to stay visible, making `is_graph_busy` return True forever.
   - **Status:** Fixed via chunk-text fallback (eval script reconstructs response from streaming chunks), frontend 120s timeout, `clearStreamingState()` on `window.__owlynnEval`, and `assistant.message` always-sent fallback in handler.py. F5.1 scores 90/100.
   - **Remaining:** Playwright browser WS connection still drops during long responses (~40s). Full fix requires frontend WS reconnection or backend polling.
   - **Files:** `frontend-v2/src/App.tsx:313`, `src/api/ws/handler.py:546`, `scripts/run_local_frontier_eval.py`

2. **Verify Frontier Eval Suite (Task `R10`)** 
   - **Why:** We need empirical proof that the system hits ≥97% (ideally 100%) after our recent patches.
   - **Current:** 93.7% (1780/1900) after F6.1 fix. Gap: +63 points needed.
   - **Action:** Fix remaining test gaps: F2.1 (90), F5.1 (90), F7.1/F7.2 (85), M1.2 (75), M2.1 (85), FF3.1 (85).

3. **Fix Silent Error Handling** 
   - **Why:** `try/catch` blocks in the frontend and API routes currently swallow errors (e.g., during profile updates). This makes regressions nearly impossible to diagnose.
   - **Action:** Audit empty catch blocks and surface errors to the user via visible toast notifications.

## 🟡 P1: Core User Experience (UX) & State Consistency

3. **Workspace Switching State (Stale UI)**
   - **Why:** Rapidly switching between chats or workspaces before previous backend tasks complete can cause data to visually bleed across contexts.
   - **Action:** Implement strict cleanup routines on component unmount and enforce generation locks per-workspace.

4. **CRUD Invariants**
   - **Why:** Heavy, repeated Create/Read/Update/Delete operations on memory and chat threads can destabilize the store.
   - **Action:** Add stress-tests for repeated DB interactions and harden the local/remote state sync.

5. **Frontend/Backend WS Payload Drift**
   - **Why:** The backend WebSocket payloads occasionally drift from what the React frontend expects, breaking core chat features silently.
   - **Action:** Enforce strict shared typing (via a centralized schema) between the Python backend and TypeScript frontend.

## 🔵 P2: Model Routing & Feature Polish

6. **Router Selection Drift**
   - **Why:** The Qwen3-VL-4B router sometimes struggles with borderline prompts (e.g., confusing casual chatter with complex reasoning), resulting in wasted tokens or slow responses.
   - **Action:** Refine the prompt logic and add pre-classification keyword gates to force obvious prompts down the correct path.

7. **Graceful Browser Degradation (Electron IPC)**
   - **Why:** Desktop-only features like *Screen Assist* and *Text-to-Speech (TTS)* currently break or look broken when running the app natively in a standard web browser.
   - **Action:** Ensure the browser UI gracefully detects the lack of Electron IPC and hides or disables these features with clear messaging.

## ⚪ P3: Long-Term Feature Expansion

8. **Cloud Fallback + Privacy Anonymization**
   - **Why:** We currently rely on best-effort redaction and a hashed cloud `user` fingerprint. 
   - **Action:** Implement a full Named Entity Recognition (NER) pipeline and build a preview UI, giving users manual control over exactly what PII is redacted before it hits the cloud.
