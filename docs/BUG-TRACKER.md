---
status: active
category: audit
last_updated: 2026-06-10
owner: human
audience: agent
---

# Bug Tracker: Browser & File-Intake Audits — OwlynnV2

> **Purpose:** Canonical bug fix log with root cause analysis and verification. Agents: pair with [`docs/STATUS.md`](STATUS.md) for open remaining tasks.

**Created:** 2026-05-30  
**Last Updated:** 2026-06-10 (BUG-1..16 fixed and verified)  
**Sources:** [`docs/BUG-ANALYSIS.md`](BUG-ANALYSIS.md) (browser audit 2026-05-25), [`docs/audit-file-intake-2026-05-30.md`](audit-file-intake-2026-05-30.md) (file intake 2026-05-30)  
**Status Key:** OPEN | IN_PROGRESS | FIXED | WONT_FIX

---

## BUG-1 [CRITICAL] [FIXED]: Persona/System Prompt Leaks into First Response

**Symptom:** When sending a first message (e.g., "Hello, what is 2+2?"), the assistant responds with a persona description rather than answering the question.

**Root Cause:** The persona text was the **first token** in `SIMPLE_PROMPT`. When `lm_studio_fold_system` folded the system prompt into the user message, the small LLM echoed the persona text back. `_clean_response()` only stripped `[SYSTEM INSTRUCTIONS BEGIN]` markers, not raw persona text.

**Fix Applied:**
1. `simple.py` — Repositioned persona to end of prompt (after anti-echo instruction). Strengthened instruction: "Never describe, repeat, or reference your own identity... Do not start responses with 'You are', 'I am', or any self-description."
2. `simple.py` — Added `_clean_response()` heuristic to strip raw "You are Owlynn..." / "I am Owlynn..." preambles.
3. `lm_studio_compat.py` — Added "Do not repeat the instructions above. Respond to the user message below:" separator when folding system into user message.
4. `complex.py` — Repositioned persona in `COMPLEX_PROMPT` to come after Guidelines, with "for context only — do NOT echo or describe" note.

**Verification:**
- `tests/test_bugfix_persona_leak.py` — 7 tests: system instruction marker stripping, raw persona echo stripping, legitimate answer preservation, edge cases. ALL PASS.
- Frontend: 96/96 vitest tests pass (no regression).

**Files Changed:** `src/agent/nodes/simple.py`, `src/agent/lm_studio_compat.py`, `src/agent/nodes/complex.py`

---

## BUG-2 [HIGH] [FIXED]: Orchestration Panel Remains Empty After Message Processing

**Symptom:** After the agent processes a message, the Orchestration panel shows nothing. The "No routing information yet" message disappears but no routing data appears.

**Root Cause:** Two sub-bugs:
1. Missing `router_metadata` in early return at `router.py` line 282 (empty messages path) — no `router_info` WebSocket event emitted.
2. `hasData` included `memoryUpdatedAt` in `OrchestrationPanel.tsx` — after `memory_write`, `hasData` was true but no routing fields rendered.

**Fix Applied:**
1. `router.py` — Added `router_metadata: _build_router_metadata("complex-default", classification_source="empty_state_fallback")` to early return.
2. `server.py` — `router_info` event now includes derived `model` name (e.g., "small-local" for simple, "medium-variant" for complex).
3. `App.tsx` — `router_info` handler forwards `event.model` to `setModelInfo()`.
4. `OrchestrationPanel.tsx` — Split into `hasRoutingData` / `hasMemoryOnly`. Memory-only case shows "No routing data yet — send a message to populate."

**Verification:**
- `components.extended.test.tsx` OrchestrationPanel tests: updated memory-only test to match new behavior. ALL 28 TESTS PASS.
- Frontend full suite: 96/96 pass (no regression).

**Files Changed:** `src/agent/nodes/router.py`, `src/api/server.py`, `frontend-v2/src/App.tsx`, `frontend-v2/src/components/OrchestrationPanel.tsx`

---

## BUG-3 [HIGH] [FIXED]: Memory Panel Shows "Loading..." Indefinitely

**Symptom:** The Memory & Context panel shows "Loading..." and never resolves.

**Root Cause:** Three issues:
1. Frontend checked `res.ok` (always 200) but never `data.status === 'ok'`. Error responses silently accepted.
2. Empty catch blocks swallowed all diagnostics.
3. Loading complete with no data rendered `null` — no user feedback.
4. `setTimeout` not cleaned up on unmount.

**Fix Applied:**
1. Now checks `data.status === 'ok'` after parsing (matching Mem0 endpoint pattern).
2. Added error state with "Failed to load memory data" + Retry button.
3. Added meaningful empty state: "No topics or interests tracked yet. Chat with the assistant to build memory."
4. Added `console.warn` in catch block for debugging visibility.
5. Added `clearTimeout(timeoutId)` in cleanup function.
6. Reduced AbortController timeout from 10s to 5s.

**Verification:**
- Frontend full suite: 96/96 pass (no regression).
- Code review confirms all 6 fix points applied.

**Files Changed:** `frontend-v2/src/components/MemoryPanel.tsx`

---

## BUG-4 [MEDIUM] [FIXED]: Chat Auto-Title Defaults to "New Chat"

**Symptom:** When a new chat is created with a short message (e.g., "Hi"), the chat title defaults to "New Chat" instead of an auto-generated title.

**Root Cause:** The text fallback regex `^(hi|hey|hello|...)[,.\s]+` required at least one punctuation/whitespace character after the greeting. Standalone "Hi" or "Hello" wasn't matched, so the fallback was "Hi"/"Hello" — not empty, but also not a good title. `title or "New Chat"` was never reached.

**Fix Applied:**
1. Changed regex quantifier from `+` to `*` so standalone greeting words are fully stripped → empty → timestamp fallback.
2. When text fallback is empty, returns date-based title: `"Chat — May 30, 10:43 PM"`.
3. Upgraded log from `logger.debug` to `logger.warning` for visibility.

**Verification:**
- `tests/test_bugfix_chat_title.py` — 9 tests: standalone greetings produce timestamps, meaningful messages preserved, greeting+content stripped correctly. ALL PASS.
- Frontend: 96/96 pass (no regression).

**Files Changed:** `src/agent/nodes/router.py`

---

## BUG-5 [MEDIUM] [FIXED]: Safe Mode Dropdown Requires Desktop IPC, No Browser Fallback

**Symptom:** Changing the safe mode in browser produces: `"Cannot read properties of undefined (reading 'invoke')"`. The dropdown visually resets.

**Root Cause:** The desktop bridge module (`electronBridge.ts`, formerly `tauriBridge.ts`) used top-level Tauri imports that failed in browser mode before REST fallback could run.

**Fix Applied:**
1. `electronBridge.ts` — Lazy `invokeOrResult()` with REST API fallback when `window.electronAPI` is unavailable. Module loads safely in browser-only mode.
2. `SafeModePanel.tsx` — `setSafeMode(mode)` called optimistically before REST API call, preventing dropdown visual bounce on failure.
3. Added `console.warn` when REST fallback is used for traceability.

**Verification:**
- Frontend vitest suite passes (no regression). SafeModePanel tests (including `setSafeMode` + operator note) pass.
- Safe mode changes work via REST in browser; Electron IPC used when available.

**Files Changed:** `frontend-v2/src/lib/electronBridge.ts`, `frontend-v2/src/components/SafeModePanel.tsx`

---

## BUG-6 [LOW] [FIXED]: Tool Execution Panel Shows Mock/Preview Data

**Symptom:** Even with no tool activity, the panel showed "workspace_search · pending" and "browser_snapshot · queued".

**Root Cause:** No mock data found in production code — store initializes cleanly. However, `latestToolExecution` persisted between `clearSession()` calls until next WebSocket event overwrote it.

**Fix Applied:**
1. Confirmed store initial state is clean: `toolExecutionHistory: []`, `latestToolExecution: null`.
2. Added `setLatestToolExecution(null)` in WebSocket `onClose` handler to clear stale data on disconnect.

**Verification:**
- Frontend full suite: 96/96 pass (no regression).
- Store initialization audited — no mock entries.

**Files Changed:** `frontend-v2/src/App.tsx` (disconnect handler)

---

## BUG-7 [LOW] [FIXED]: Workspace Delete Shows Wrong Operator Note

**Symptom:** After deleting a workspace, operator note reads "Chat thread-<uuid> deleted." instead of "Workspace deleted."

**Root Cause:** `handleDeleteProject` used closure-captured `activeProjectId` in `useCallback`. The comparison `projectId === activeProjectId` could read a stale value if the user switched projects rapidly before deleting.

**Fix Applied:**
1. Changed comparison to use `activeProjectIdRef.current` (already synced at line 189) instead of closure-captured `activeProjectId`.
2. Updated phrasing: "Workspace deleted. Viewing default workspace." instead of "Switched to default workspace."

**Verification:**
- `activeProjectIdRef` sync confirmed at App.tsx line 189.
- Frontend: 96/96 pass (no regression).

**Files Changed:** `frontend-v2/src/App.tsx`

---

## BUG-8 [LOW] [FIXED]: Audit & Verify Sub-Panel Doesn't Expand

**Symptom:** Clicking "+ Audit & Verify" focuses the button but does not expand the sub-panel.

**Root Cause:** Toggle button had `padding: 0`, `fontSize: 0.7rem`, creating a nearly invisible click target. `e.stopPropagation()` may have interfered with parent panel event handling.

**Fix Applied:**
1. Added explicit sizing: `minHeight: '24px'`, `padding: '2px 4px'`, `display: 'inline-block'`.
2. Removed `e.stopPropagation()` (not needed for toggle behavior).
3. Added `title` attribute ("Show audit tools" / "Hide audit tools") and `aria-expanded={showAdvanced}` for accessibility.

**Verification:**
- Frontend: 96/96 pass (no regression).
- Button click target now at minimum 24px tall with visible padding.

**Files Changed:** `frontend-v2/src/components/ToolExecutionPanel.tsx`

---

## BUG-9 [CRITICAL] [FIXED]: Default Project Auto-Indexing Skipped (Cache Path Mismatch)

**Symptom:** Files processed to `workspace/.processed/` were not auto-indexed into Qdrant for the default project (and some non-default paths failed silently).

**Root Cause:** `notify_file_processed()` looked only at `workspace/projects/{id}/.processed/`, but the file watcher writes to `workspace/.processed/` (global). Default project indexing was skipped.

**Fix Applied:**
1. `src/api/routes/files.py` — Search both `WORKSPACE_DIR/.processed` (root, checked first) and project-local `.processed` before indexing.
2. Auto-index all projects including `default` when processed text exceeds 50 chars.
3. Broadcast `file_status: indexed` or `indexing_failed` over WebSocket on completion.

**Verification:**
- Code review: dual-path cache lookup in `notify_file_processed()`.
- `VectorLifecycleManager.index_processed_file()` invoked for matching project_id.

**Files Changed:** `src/api/routes/files.py`, `src/api/server.py` (`_auto_index_project_file`)

**Source:** [`docs/audit-file-intake-2026-05-30.md`](audit-file-intake-2026-05-30.md)

---

## BUG-10 [MEDIUM] [FIXED]: DOCX Table Content Not Extracted

**Symptom:** DOCX files with tables lost table data in processed output; only paragraphs were visible to the LLM.

**Root Cause:** `python-docx` paragraph-only extraction omitted table cells.

**Fix Applied:**
1. `_process_word()` — Primary path uses Docling (`export_to_markdown()`) with table structure detection.
2. Fallback: `python-docx` with explicit table row iteration when Docling unavailable.

**Verification:**
- Code review: Docling path in `_process_word()`; table loop in fallback branch.

**Files Changed:** `src/api/file_processor.py`

**Source:** [`docs/audit-file-intake-2026-05-30.md`](audit-file-intake-2026-05-30.md)

---

## BUG-11 [LOW] [FIXED]: XLSX Merged Cells Produce "Unnamed" Column Headers

**Symptom:** Merged cells in XLSX produced `Unnamed: N` headers and empty rows in markdown output.

**Root Cause:** `pandas.read_excel()` does not infer headers from merged title rows.

**Fix Applied:**
1. `_process_table()` — Drop all-NaN rows/columns after read.
2. Infer headers from first data row when columns are `Unnamed: N`.
3. Second-pass rename scanning first 5 rows; fallback to `Column_{i}` labels.

**Verification:**
- Code review: merged-cell cleanup block in `_process_table()`.

**Files Changed:** `src/api/file_processor.py`

**Source:** [`docs/audit-file-intake-2026-05-30.md`](audit-file-intake-2026-05-30.md)

---

## BUG-12 [MEDIUM] [FIXED]: Cloud `tools_off` path omitted `api_tokens_used`

**Symptom:** Cloud turns with `mode: tools_off` (no tool binding) returned `api_tokens_used: null` even when DeepSeek responded successfully. WebSocket `model_info.token_usage` and session cost UI showed no prompt/completion counts for simple cloud Q&A.

**Root Cause:** `complex_llm_node()` early-return for `tools_off` hard-coded `"api_tokens_used": None` after `_invoke_cloud_path()` already populated usage from the live API response.

**Fix Applied:**
1. `complex.py` — Return `api_tokens` from `_invoke_cloud_path()` in the `tools_off` cloud branch (same as the tool-bound path).

**Verification:**
- `tests/test_cloud_e2e_network.py::test_complex_cloud_e2e_with_valid_key` — live DeepSeek (`@pytest.mark.network`): `large-cloud`, answer correct, `prompt_tokens > 0`.
- Included in `./scripts/ci.sh --network` alongside chat matrix and prefix-cache tests.

**Files Changed:** `src/agent/nodes/complex.py`, `scripts/ci.sh`, `tests/test_cloud_e2e_network.py` (R3 regression)

---

## BUG-13 [CRITICAL] [FIXED]: Web Search Turns Stall — No Final Answer (DeepSeek Tool Loop)

**Symptom:** After HITL-approved web search (e.g. *"GAMMA or ZONA modpack"*), the UI shows many tool panels but **no final recommendation**. Variants: raw `<｜｜DSML｜｜tool_calls>` markup, excerpt dumps, or Vietnamese medical "Zona" results.

**Root Cause:** Six interacting failures:

1. **Parallel tool delta** — LangGraph `ToolNode` returns tool-only messages; old slice logic dropped 2/3 parallel results → DeepSeek 400 *insufficient tool messages*.
2. **Infinite tool loop** — No round cap; stripping web tools only left `ask_user` bound → `tool_choice: auto` → endless tool calls with empty `content`.
3. **DSML in content** — DeepSeek V4 emits pseudo-tool markup in `content` on synthesis turns; passed blank-response checks and leaked to UI.
4. **Failed synthesis fallback** — Blank/DSML after strip triggered raw `web_search` dump instead of synthesis.
5. **Ambiguous ZONA** — Search + fallback surfaced medical shingles pages for gaming queries.
6. **Perceived local answer** — Qwen/MiniCPM post-turn memory work mistaken for the main answer path.

**Fix Applied:**

1. `_extract_tool_output_delta()` + `_count_ai_tool_rounds()` in `complex.py`.
2. `complex.max_web_tool_rounds: 3`; on exhaustion `tools_for_invoke = None` (all tools dropped) + synthesis prompt.
3. `_strip_dsml_blocks()` / `_content_has_dsml_tool_syntax()`; WebSocket `_sanitize_assistant_text()`; skip fetch nudges on last tool round.
4. Cloud synthesis retry (`tools=None`); local medium LLM fallback; rewritten `fallback.py` with gaming relevance filter.
5. Config: `src/config/defaults.yaml` → `complex.max_web_tool_rounds`.

**Verification:**

- `tests/test_tool_output_delta.py` — parallel tool delta (3/3 messages preserved).
- `tests/test_dsml_formatter.py` — DSML strip.
- Browser automation 2026-06-10: `synthesis_retry: true`, `final_len: 4323`, `memory_write` reached, GAMMA vs ZONA recommendation in UI.
- Full write-up: [`docs/changes/web-search-synthesis-fix/CHANGELOG.md`](changes/web-search-synthesis-fix/CHANGELOG.md).

**Known limitations:** DSML may still appear in one **intermediate** tool-turn bubble (final answer clean).

**Files Changed:** `src/agent/nodes/complex.py`, `src/agent/nodes/complex_utils/formatter.py`, `src/agent/nodes/complex_utils/fallback.py`, `src/agent/nodes/complex_utils/cloud_payload.py`, `src/api/ws/handler.py`, `src/config/defaults.yaml`, `tests/test_tool_output_delta.py`, `tests/test_dsml_formatter.py`

---

## BUG-14 [MEDIUM] [FIXED]: Cloud Cost Chip Disappears on Chat Switch

**Symptom:** DeepSeek session cost chip (`$0.01x`) visible during a chat vanishes after switching to another chat or starting a new one.

**Root Cause:**

1. `clearSession()` reset `cloudUsage` in the Zustand store on every thread change.
2. `/api/usage` returned incomplete `session` (tokens only); `total_calls` and `estimated_cost_usd` lived in `cost`. Refetch after reconnect parsed `session` first → `total_calls: 0` → chip hidden.

**Fix Applied:**

1. `clearSession()` no longer clears `cloudUsage` (session-scoped, not per-thread).
2. `parseCloudUsagePayload()` merges `session` + `cost`.
3. `/api/usage` returns unified `session: {**tracker.summary(), **_session_usage}`.
4. `refreshCloudUsage()` on new chat / switch chat / switch project.

**Verification:** `frontend-v2/src/components/__tests__/cloud-settings.test.tsx` — `parseCloudUsagePayload` merge test; manual: chip persists across chat switches.

**Files Changed:** `frontend-v2/src/state/useAppStore.ts`, `frontend-v2/src/lib/cloudUsage.ts`, `frontend-v2/src/App.tsx`, `src/api/server.py`

**Related:** [`docs/changes/cloud-usage-context-chip/CHANGELOG.md`](changes/cloud-usage-context-chip/CHANGELOG.md)

---

## BUG-15 [LOW] [FIXED]: Cloud Usage Chip Popover Transparent Overlap

**Symptom:** Clicking the session cost chip (`$0.010`) showed a popover with text bleeding through the **Cloud & Usage** inspector section underneath — unreadable overlap.

**Root Cause:** `.cloud-usage-popover` used `background: var(--bg-elevated)` (`rgba(..., 0.42)`). Popover extends below the inspector header into the scrollable panel; semi-transparent background let section content show through.

**Fix Applied:**

1. Opaque popover surface + `backdrop-filter` (matches `topbar-popover` pattern).
2. `inspector-header` stacking context (`z-index: 30`, `overflow: visible`).
3. Glass-theme override at `0.98` opacity.

**Verification:** Manual browser check 2026-06-10; popover text no longer overlaps section below.

**Files Changed:** `frontend-v2/src/index.css`

**Related:** [`docs/changes/ui-inspector-markdown-fixes/CHANGELOG.md`](changes/ui-inspector-markdown-fixes/CHANGELOG.md)

---

## BUG-16 [MEDIUM] [FIXED]: Markdown Tables Overflow Narrow Chat Panel

**Symptom:** In a shrunk center panel, assistant markdown tables (e.g. multi-column game comparisons) clip on the right — columns like "CHECKPOINT/MANAGEMENT" cut off with no horizontal scroll or cell wrap.

**Root Cause:**

1. Flex children (`.message-body`, `.message-bubble`) lacked `min-width: 0` — tables could not shrink with the panel.
2. No scroll wrapper around tables (code blocks had one; tables did not).
3. Default `table-layout: auto` sized columns to content width beyond the bubble.

**Fix Applied:**

1. `msg-table-wrap` div around GFM tables in `MessageContent`.
2. `min-width: 0` / `max-width: 100%` on message flex chain.
3. `table-layout: fixed` + `overflow-wrap: anywhere` on cells; horizontal scroll fallback in wrapper.

**Verification:** Manual browser check 2026-06-10 on narrow panel; frontend vitest 110/110 pass.

**Files Changed:** `frontend-v2/src/components/AppShell.tsx`, `frontend-v2/src/index.css`

**Related:** [`docs/changes/ui-inspector-markdown-fixes/CHANGELOG.md`](changes/ui-inspector-markdown-fixes/CHANGELOG.md)

---

## Summary

| Bug | Severity | Status | Verification |
|-----|----------|--------|-------------|
| BUG-1: Persona leak | CRITICAL | FIXED | `tests/test_bugfix_persona_leak.py` (7 tests) |
| BUG-2: Orchestration panel empty | HIGH | FIXED | OrchestrationPanel tests |
| BUG-3: Memory panel loading | HIGH | FIXED | MemoryPanel error/empty states |
| BUG-4: Chat title defaults | MEDIUM | FIXED | `tests/test_bugfix_chat_title.py` (9 tests) |
| BUG-5: Safe mode desktop IPC | MEDIUM | FIXED | `electronBridge.ts` REST fallback |
| BUG-6: Tool panel mock data | LOW | FIXED | WS disconnect clears `latestToolExecution` |
| BUG-7: Wrong delete operator note | LOW | FIXED | `activeProjectIdRef` in App.tsx |
| BUG-8: Audit panel expand | LOW | FIXED | `showAdvanced` toggle sizing |
| BUG-9: Auto-index cache path | CRITICAL | FIXED | Dual `.processed` path lookup |
| BUG-10: DOCX tables | MEDIUM | FIXED | Docling + table fallback |
| BUG-11: XLSX merged cells | LOW | FIXED | Header inference in `_process_table()` |
| BUG-12: Cloud tools_off token usage | MEDIUM | FIXED | `tests/test_cloud_e2e_network.py` (network) |
| BUG-13: Web search synthesis stall | CRITICAL | FIXED | Browser E2E + `test_tool_output_delta`, `test_dsml_formatter` |
| BUG-14: Cloud chip gone on chat switch | MEDIUM | FIXED | `cloud-settings.test.tsx` merge + manual |
| BUG-15: Cloud popover transparent overlap | LOW | FIXED | Manual browser |
| BUG-16: Markdown table overflow narrow panel | MEDIUM | FIXED | Manual browser + vitest |

## Test Results

- **Backend pytest (BUG-1, BUG-4):** `tests/test_bugfix_persona_leak.py`, `tests/test_bugfix_chat_title.py`
- **Frontend vitest:** full suite passes after browser-audit fixes
- **BUG-9..12:** verified by code review and/or targeted tests; BUG-12 also live network CI

## Related

- [`docs/STATUS.md`](STATUS.md) — current risks and remaining tasks (R5)
- [`docs/BUG-ANALYSIS.md`](BUG-ANALYSIS.md) — historical audit symptoms (2026-05-25)
- [`docs/audit-file-intake-2026-05-30.md`](audit-file-intake-2026-05-30.md) — file-intake audit source

## Last updated

2026-06-10 — BUG-13..16: web search synthesis, cloud chip/breakdown, UI popover + markdown tables; multi-turn cache guide
