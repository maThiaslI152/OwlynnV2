# Browser Verification — May 25, 2026 Audit

> **Note**: This document describes an historical audit session. The current default medium model is `gemma-4-e4b-uncensored-hauhaucs-aggressive` (Q4_K_M). The Qwen 3.5 9B fp16 variant described in Session 1 is no longer used.

Two test sessions. Session 1 used Qwen 3.5 9B fp16 (crashed). Session 2 switched to Gemma 4 E4B Q4_K_M (stable).

---

## Session 1 (14:46–15:03 ICT): Qwen 3.5 9B fp16

Backend (uvicorn:8000) + frontend (Vite:5173). LM Studio had model load failures, Redis unavailable.

### BUG-2 — Orchestration Panel Empty
- **CONFIRMED FIXED** — Orchestration panel renders without error. Router dispatched correctly (`[router] Simple path - keyword match`).

### BUG-3 — Memory Panel "Loading..." Forever
- **CONFIRMED FIXED** — `/api/topics` (19ms), `/api/interests` (20ms) complete. "Loading..." resolves to empty state. AbortController 10s timeout in place.

### BUG-4 — Chat Auto-Title Defaults to "New Chat"
- **CONFIRMED FIXED** — Backend log: `title=hello` extracted from first meaningful word. The `try/except` in `router.py` fell back to text extraction on LLM failure.

### BUG-5 — Safe Mode Dropdown Errors in Browser
- **CONFIRMED FIXED** — Dropdown Normal → Read-only without errors. Operator note: "ⓘ Safe Mode set to safe_readonly". Tauri bridge detection + REST fallback working.

### BUG-6 — Mock Data in Tool Execution Panel
- **CONFIRMED FIXED** — Shows "No tool activity yet." Zero mock entries.

### BUG-8 — Audit & Verify Panel Doesn't Expand
- **CONFIRMED FIXED** — "+ Audit & Verify" expands to full sub-panel. `stopPropagation` + `overflow: visible` working.

### Crash: Qwen 3.5 9B fp16 Segfault at 5,280 tokens
- Root cause: Unified memory exhaustion (18 GB model weights + 1.9 GB Podman VM + KV cache > 24 GB M4 Air RAM).
- Fixes applied: Podman VM 1907 → 1024 MB, `_DEFAULT_CONTEXT_WINDOW` 100K → 16K in `graph.py`.
- Model was replaced with Gemma 4 E4B Q4_K_M (~2.5 GB).

---

## Session 2 (19:36 ICT): Gemma 4 E4B Q4_K_M

Model switched to [HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive](https://huggingface.co/HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive) Q4_K_M.

### Configuration Changes (4 files)

| File | Change |
|------|--------|
| `src/config/settings.py` | `large_model`: max_tokens 8192→4096, context_length 100K→16K, timeout 120s→60s. `memory`: max_facts 150→200, search_window 50→100. |
| `src/agent/llm.py` | Default model: `qwen/qwen3.5-9b` → `gemma-4-e4b-uncensored-hauhaucs-aggressive` |
| `src/agent/nodes/complex.py` | `_LARGE_CONTEXT_WINDOW` 100K→16K. Comments updated. |
| `src/agent/lm_studio_compat.py` | Comment updated (Qwen → generic). |

### Live Test Result

- **Model works**: Two consecutive 200 OK API calls, no segfault.
- **BUG-4 re-verified**: Title `"What is your name?"` registered correctly with Gemma.
- **BUG-1 blocked by frontend issue**: Backend processed response successfully, but assistant message didn't render in UI. User message appeared in DOM, but no assistant bubble. Not a model/prompt issue — WebSocket event rendering gap.

---

## Still Blocked

### BUG-1 — Persona System Prompt Leaks into Response
- **Status**: UNVERIFIED (response received by backend, not rendered in UI)
- Block: Assistant message doesn't appear in the DOM. WebSocket event for final `answer` may not be handled correctly by the React frontend.
- What's verified: Model loads and responds. `_clean_response` stripping logic, system delimiter markers, guard sentence all deployed.

### BUG-7 — Wrong Operator Note
- **Status**: UNTESTED
- Requires persisted chats (Redis) to test delete operations.

### Known Issues

| Issue | Impact |
|-------|--------|
| **Redis unavailable** | `AsyncRedisSaver` constructor arg mismatch (`url` vs expected param). MemorySaver fallback — no persistence across reloads. |
| **Assistant message not rendering** | Backend processes response (200 OK), WebSocket events sent, but DOM doesn't update. Needs frontend debugging. |

---

## Next Actions

1. **Fix assistant message rendering** — investigate WebSocket event → React state pipeline for the final `answer` event
2. **Re-test BUG-1** — once rendering fixed, send "What is your name?" and verify no system prompt markers in response
3. **Fix Redis connection** — `AsyncRedisSaver` constructor param
4. **Re-test BUG-7** — with Redis, create → delete a chat, verify operator note
