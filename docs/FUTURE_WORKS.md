---
status: active
category: planning
last_updated: 2026-06-28
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
   - **Why:** The Gemma 4 E2B router sometimes struggles with borderline prompts (e.g., confusing casual chatter with complex reasoning), resulting in wasted tokens or slow responses.
   - **Action:** Refine the prompt logic and add pre-classification keyword gates to force obvious prompts down the correct path.

7. **Graceful Browser Degradation (Electron IPC)**
   - **Why:** Desktop-only features like *Screen Assist* and *Text-to-Speech (TTS)* currently break or look broken when running the app natively in a standard web browser.
   - **Action:** Ensure the browser UI gracefully detects the lack of Electron IPC and hides or disables these features with clear messaging.

## ⚪ P3: Long-Term Feature Expansion

8. **Cloud Fallback + Privacy Anonymization**
   - **Why:** We currently rely on best-effort redaction and a hashed cloud `user` fingerprint. 
   - **Action:** Implement a full Named Entity Recognition (NER) pipeline and build a preview UI, giving users manual control over exactly what PII is redacted before it hits the cloud.

## 🟢 P4: Study & Pentest Enhancements

9. **NLP Quiz Grading** — ✅ DONE (word-boundary matching)
   - **Why:** Current substring matching is too simplistic for open-ended answers. Students get partial credit for mentioning keywords but miss nuance.
   - **Action:** Implement NLP-based grading using the LLM to evaluate answers for correctness, completeness, and understanding.
   - **Status:** Implemented word-boundary matching (replaces substring). MCQ uses exact index match. Auto-logging on quiz completion.

10. **Flashcard Import/Export** — ✅ DONE (CSV)
    - **Why:** Users want to import existing flashcard decks from Anki or CSV files, and export their decks for use in other tools.
    - **Action:** Add Anki (.apkg) and CSV import/export to `flashcard_deck_create` and `flashcard_review` tools.
    - **Status:** Implemented CSV import/export. Supports 3 header formats (front,back / term,definition / question,answer).

11. **Pentest Screen Assist Live Panel**
    - **Why:** Users want to see real-time Kali SSH terminal output in the right panel instead of using the `capture_kali_terminal` tool.
    - **Action:** Implement a live terminal preview component that streams tmux pane output from the Kali VM.

12. **Speculative Decoding**
    - **Why:** LM Studio supports speculative decoding with MTP draft models, which can significantly speed up inference.
    - **Status:** Blocked on LM Studio fixing MTP draft model segfault. Monitor for updates.

13. **Course-Project Linking**
    - **Why:** Users want course files (syllabus, notes, readings) to automatically sync with the workspace project.
    - **Action:** Implement auto-sync when `course_register` is called with `linked_files`, and manual sync via `course_workspace_create`.

14. **Study Analytics Dashboard** — ✅ DONE
    - **Why:** Users want to see charts for study time, mastery trends, and exam countdowns.
    - **Action:** Add visualization components to the study progress panel.
    - **Status:** Implemented StudyAnalytics component with score trend line chart and topic mastery radar chart using recharts.

## ⚫ P5: Blocked / Low Priority

15. **Additional Pentest Models**
    - **Why:** Current benchmark only evaluated 3 Gemma 12B models. Other models (Qwen3.5 9B, Gemma 4 26B A4B) were skipped due to thinking mode issues or VRAM constraints.
    - **Status:** Blocked on LM Studio fixing GGUF loading when external SSD is mounted. Monitor for updates.

16. **Cloud Pentest Proxy**
    - **Why:** Some pentest queries (e.g., CVE lookups, exploit databases) don't contain sensitive target information and could be sent to cloud APIs for faster responses.
    - **Action:** Implement a proxy that anonymizes non-sensitive pentest queries and routes them to cloud APIs.

17. **Wireless Pentest Tools**
    - **Why:** Users want WiFi scanning, deauthentication, and handshake capture tools for wireless pentesting.
    - **Action:** Add tools for `aircrack-ng`, `airodump-ng`, `aireplay-ng` with proper safety checks and HITL approval.
