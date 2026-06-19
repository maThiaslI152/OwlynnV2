---
status: active
category: standards
last_updated: 2026-06-18
owner: ai-agent
audience: agent
---

# Owlynn Status

> **Purpose:** Project status tracker — bug inventory, phase progress, current risks, and remaining tasks.

## Overview

Project status tracker. Last updated: 2026-06-19 — Qwen3-VL-4B vision proxy replaces Florence-2; cloud-only pivot stable.

## Recent Changes (2026-06-19)

| Change | Impact | Doc |
|--------|--------|-----|
| **Qwen3-VL-4B vision proxy** | Replaces Florence-2 (unloadable via LM Studio API). Full multimodal VLM; F9.1 100/100; 11 source files + 16 docs updated. LM Studio: 4 models, 7.5 GB. | [`changes/qwen3vl-vision-proxy/CHANGELOG.md`](changes/qwen3vl-vision-proxy/CHANGELOG.md) |
| **Cloud-only pivot** | 3-tier → 2-tier cloud-only; `complex-default` removed; all complex reasoning → `complex-cloud`; local Qwen eliminated; medium slot removed from LLM pool; memory extraction → gemma-4-e2b; simple retry-once MiniCPM5; strict-cloud concept removed (`cloud_strict.py` deleted); 26 test files + 8 docs rewired | [`changes/cloud-only-pivot/CHANGELOG.md`](changes/cloud-only-pivot/CHANGELOG.md) |
| **R5 coherence self-correction** | `coherence_retry.py` node + `coherence_retry_gate`; bounded by `coherence.max_retries: 1`; threshold 0.4; cloud-only (no local fallback) | [`changes/coherence-self-correction/CHANGELOG.md`](changes/coherence-self-correction/CHANGELOG.md) |
| **Playwright MCP** | `@playwright/mcp` host-native (npx + cached Chromium); no podman container overhead | — |

## Recent Changes (2026-06-18)

| Change | Impact | Doc |
|--------|--------|-----|
| **Strict-cloud round 2** | BUG-27 cloud payload compaction; BUG-28 circuit-breaker per browser turn; BUG-29 turn-scoped assistant scrape; educator EDU5–8 nudges | [`evaluations/strict-cloud-debug-2026-06-16.md`](evaluations/strict-cloud-debug-2026-06-16.md) |
| **Eval harness HITL** | All eval scripts set `execution_policy=auto_approve` during runs (scope/plan/security) | [`standards/EVALUATION.md`](standards/EVALUATION.md) |

## Recent Changes (2026-06-16)

| Change | Impact | Doc |
|--------|--------|-----|
| **Multi-model review fixes** | Notebook RCE gated (loopback token + CORS lockdown); cells default non-runnable; embed URLs restricted; cloud `user` fingerprint; anonymization reframed best-effort | [`changes/multi-model-review-fixes/CHANGELOG.md`](changes/multi-model-review-fixes/CHANGELOG.md) |

## Recent Changes (2026-06-15)

| Change | Impact | Doc |
|--------|--------|-----|
| **Tool preamble / read_file UX** | No streamed “Reading workspace file…”; false ERROR on PDF reads fixed; `[Attached: …]` filename normalization | [`changes/tool-preamble-read-file-fix/CHANGELOG.md`](changes/tool-preamble-read-file-fix/CHANGELOG.md) |
| **Browser Bridge active tab** | User push + agent `get_active_browser_context` via Brave extension v1.1 | [`changes/browser-extension-active-tab/CHANGELOG.md`](changes/browser-extension-active-tab/CHANGELOG.md) |

## Recent Changes (2026-06-11)

| Change | Impact | Doc |
|--------|--------|-----|
| **Notebook & Word Doc Hardening** | Added Word doc parsing support, notebook thread-isolation, 15s cell timeouts, and 100 recursion limit | [`walkthrough.md`](../walkthrough.md), [`docs/AGENT_FLOW.md`](AGENT_FLOW.md), [`docs/TOOLS.md`](TOOLS.md) |
| **Chrome Search Bridge** | Browser extension search routing via Brave to bypass bot detection/CAPTCHAs | [`changes/browser-extension-search-bridge/CHANGELOG.md`](changes/browser-extension-search-bridge/CHANGELOG.md) |
| **Frontier eval harness** | WS tool merge, idle stall exit, F4 fixture, M4 greeting gate, F8/F9 fixes; 82% → **~94%** | [`changes/frontier-eval-memory-session/CHANGELOG.md`](changes/frontier-eval-memory-session/CHANGELOG.md) |
| **Scoring-only cloud strict** | Qwen fallback on cloud-intended turns caps grade at 49 (no runtime block) | `scripts/run_local_frontier_eval.py` |
| **Vision proxy upgrade** | Qwen3-VL-4B replaces Florence-2; full multimodal VLM; LM Studio API load confirmed; F9.1 100/100 | — |
| **Background memory extraction** | Qwen extraction defers until chat idle + lower CPU nice | `local_llm_scheduler.py` |

## Recent Changes (2026-06-04)

| Change | Impact | Commits |
|--------|--------|---------|
| **DeepSeek V4 Upgrade** | 1M Context window, extra_body config, SwapManager removal, Vision guardrail | Complete |
| **Config centralization** | ~100 settings → 1 file (`defaults.yaml`). Override chain: YAML → env → profile | `bb04b25` |
| **MiniCPM5 router** | Router: minicpm5-1b. Complex: deepseek-v4-flash (cloud). | `dd69035` → `6367323` |
| **14 bugs fixed** | HITL GraphInterrupt, keyword bypass, thinking budgets, request_timeout, startup race, context overflow | `2b907d2` → `acd9f8d` |
| **Router bypasses** | Code review, creative writing, explain/compare → force complex (9B model) | `6da48bd` |
| **Config audit** | 4 missing entries, 6 stale fallbacks synced, ConfigValidator (60+ paths) | `4011a27` |
| **Model preloading** | Both models preload + warmup at startup. No more 0s first-call failures. | `acd9f8d` |
| **Documentation** | HITL.md, MEMORY.md, architecture overview rewritten, INDEX.md v3 | `ce736b5` → `4ea8223` |

## Current Model Config

| Slot | Model | Context | Temp | Max Tokens |
|------|-------|---------|------|------------|
| Router | `minicpm5-1b` | 8192 | 0.2 | 512 |
| Cloud | `deepseek-v4-flash` | 1048576 | 0.4 | 8192 |
| Vision | `qwen3-vl-4b-instruct-c_abliterated-v2-mlx` | 8192 | 0.1 | 2048 |
| Extraction | `gemma-4-e2b-heretic-uncensored-mlx` | 8192 | 0.1 | 1024 |

## Evaluation Trajectory

| Eval | Score | Key Finding |
|------|-------|------------|
| v4 (gemma-4 baseline) | 4.02 | Complex latency 180-350s |
| v5 (Qwen3.5 initial) | 2.44 | 33% error rate, 9/12 misrouted |
| v6 (HITL + budgets) | 3.67 | 0 errors, medium model working |
| v7-final | ~4.0 est. | Bypasses confirmed, preload working |
| v8 (2026-06-10) | 75.8% cloud (6 turns) | F1 empty reply, F3–F6 DSML/HITL — [`evaluations/local-frontier-eval-2026-06-10-v2.md`](evaluations/local-frontier-eval-2026-06-10-v2.md) (superseded) |
| v9 (2026-06-11) | 82.4% mechanical (19 turns) | Pre-fix pipeline — [`evaluations/local-frontier-eval-2026-06-11.md`](evaluations/local-frontier-eval-2026-06-11.md) |
| v9b (2026-06-11) | **94.2%** post-fix (1790/1900) | WS waiter, F4 fixture, M4/F8/F9 fixes |
| v9c (2026-06-11) | **94.0%** post-fix (1785/1900) | Latest artifact; F9 Florence variance |
| v10 (2026-06-11) | **Quality A/B** vs raw DeepSeek | Owlynn vs frontier chat + blind pro judge — [`evaluations/frontier-comparison-2026-06-11.md`](evaluations/frontier-comparison-2026-06-11.md) |
| v11 (2026-06-17) | **91.3%** strict cloud (1644/1800) | Runtime `cloud_no_local_fallback`; F5.1 only `qwen_fallback` — [`evaluations/strict-cloud-debug-2026-06-16.md`](evaluations/strict-cloud-debug-2026-06-16.md) |
| v11b (2026-06-18) | **Fixes landed** (re-run pending) | BUG-27..29 + educator harness/product fixes committed |

| v12b (2026-06-19) | **85.0%** cloud-only pivot (1615/1900) | First eval post-pivot. Effective ~93.2% (transient routing + Florence unavailable). No pivot regression. — [`evaluations/cloud-only-pivot-eval-2026-06-19.md`](evaluations/cloud-only-pivot-eval-2026-06-19.md) |
| v12c (2026-06-19) | **Qwen3-VL-4B** replaces Florence-2. F9.1: 100/100. | Florence unloadable via LM Studio API — Qwen3-VL fixes this. |

## Remaining Tasks

### 🔴 High Impact
- **R1**: One-turn lag — message correlation IDs in browser (✅ Fixed)
- **R2**: Inference latency — 105-276s vs SLO <8s (✅ Fixed via context optimization for M4 Air)
- **BUG-17**: Vision route not deterministic — image attach doesn't reliably trigger `vision_cloud` (F9.1 variance) (✅ Fixed)
- **BUG-18**: Simple-path empty reply — streaming bubble doesn't surface even when route + model correct (F1.1) (✅ Fixed)
- **BUG-19**: Tool-call XML leaks as literal text in assistant reply — Qwen format not stripped (F3.1/F4.1) (✅ Fixed)
- **BUG-20**: Greeting routed to `complex-cloud` instead of `simple` — keyword bypass gap (M4.1) (✅ Fixed)
- **BUG-24..29**: Strict-cloud eval regressions — MiniCPM empty reply, harness idle/scrape, F5.1 cloud replay, browser circuit breaker, educator turns (✅ Fixed — re-run evals to confirm scores)

> See [`docs/BUG-TRACKER.md`](BUG-TRACKER.md) for root cause analysis and fix approaches for BUG-17..20. Strict-cloud BUG-24..29: [`evaluations/strict-cloud-debug-2026-06-16.md`](evaluations/strict-cloud-debug-2026-06-16.md).

### 🟡 Medium Impact
- **R10**: Frontier eval ≥97% — at **~94%** after harness fixes; F1/F6/F9 variance remains
- **R7**: Web search aggregate timeout (✅ `tests/test_web_search_aggregate_timeout.py`)
- **R9**: API thread_id in OpenAI compat config (✅ `tests/test_openai_thread_persistence.py`)
- **R8**: Thermal throttling — run evals on AC power, not battery (✅ Mitigated via defaults.yaml)

### 🟢 Documentation & Code Health
- D1: Decompose `server.py` (✅ Extracted 2283 lines into src/api/routes)
- D2: Refactor `complex.py` (✅ Extracted fallback and formatting utilities)

## Entry Points

```text
docs/STATUS.md                # This file
docs/BUG-TRACKER.md           # Canonical bug fix log (BUG-1..16)
docs/BUG-ANALYSIS.md          # Historical audit symptoms (2026-05-25)
docs/ADR.md                   # Architecture decisions
docs/PERFORMANCE_SLOS.md      # Performance targets
src/api/server.py              # Backend runtime
frontend-v2/src/App.tsx        # Frontend runtime
```

## Current Progress

| Phase | Status | Date |
|-------|--------|------|
| Phase 6 (MVP Hardening) | Complete | — |
| Phase 7 (Post-MVP Polish) | Complete | 2026-05-11 |
| Phase 8 (Browser Audit Bug Fixes) | Complete | 2026-05-31 |

### Phase 7 Results

- 13 skipped tests fixed across 3 root causes:
  - Skill matcher: added `scikit-learn` dependency
  - Graph LLM tests: added `LLMPool._test_overrides` mechanism
  - WS contract tests: mocked `generate_chat_title_router_llm`, fixed chunk event type assertion
- Core test suite: **705 passed, 0 failed, 5 skipped** (Redis/integration)

### Active Runtime Configuration

| Key | Value |
|-----|-------|
| `small_llm_model_name` | `minicpm5-1b` |

### Core Capabilities Status

| Capability | Status |
|------------|--------|
| LangGraph flow (memory \u2192 route \u2192 complex \u2192 tool \u2192 memory) | Active |
| Cloud-primary routing (router → vision → complex-cloud) | Active |
| M-tier model swap logic | Removed (2026-06-05) |
| Security proxy HITL approval | Active |
| Backend API + WebSocket chat | Active |
| Electron frontend shell | Active |
| Live Talk (wake-word, STT) | Removed (2026-04-29) |
| TTS (`speak_text` via macOS `say`) | Active |
| RAG File Intake (PDF/DOCX/XLSX \u2192 Qdrant) | \u2705 Fixed (Docling) |
| Workspace Tools (read/save/search/list) | Active |

## Testing

| Suite | Status | Count |
|-------|--------|-------|
| Backend core | Pass | 203 passed |
| Frontend-v2 (vitest) | Pass | 50 passed |
| Frontend-v2 (build) | Pass | Build passes |

## Architecture

### Phase Resolutions

| Phase | Key Deliverables |
|-------|-----------------|
| Phase 1: Stabilization | Browser multi-switch harness, WS+CRUD timing tests, frontend cutover, component regression tests (35 total) |
| Phase 2: Reliability | Route/fallback telemetry, WS contract tests (20 total, +5 new), CI gate standardization, summarize-node routing, observability |
| Phase 3: Capability | Enhanced summarize/context compression, project vault knowledge panel, orchestration controls in frontend |
| Phase 4: Governance | ADR log (11 decisions), performance SLOs, release train alignment |
| Phase 5: Live Test | Removed dead tests, fixed tool awareness assertions. 203 passed, 0 failed |
| Phase 6: MVP Hardening | `.env.example`, logging, dependency pinning, bug fixes, 58 backend + 31 frontend tests added |
| Phase 7: Test Fixes | 13 skipped tests fixed. 705 passed, 0 failed, 5 Redis/integration skipped |

## API

### Recent Bug Fixes

| Bug | Date | Resolution |
|-----|------|------------|
| LTM ValueError (mem0 search) | 2026-04-25 | Fixed 6 `search()` calls — `user_id` moved from `filters` dict to keyword argument |
| New chat reversion | 2026-04-25 | Fixed `loadProjects()` race — checks if `currentThreadId` exists before overwriting |
| Topics not used in simple path | 2026-04-25 | Extracted knowledge section into `simple_node()` prompt |
| 13 skipped tests | 2026-05-11 | Fixed: scikit-learn dependency, LLMPool mock overrides, WS contract assertions |

### Known Bugs (Browser Audit 2026-05-25)

| ID | Severity | Description | Location | Status |
|----|----------|-------------|----------|--------|
| BUG-1 | **CRITICAL** | Persona/system prompt leaks into first assistant response | `src/agent/nodes/simple.py` or `complex.py` | Fixed |
| BUG-2 | **HIGH** | Orchestration panel empty after message processing | `src/api/server.py` or `OrchestrationPanel.tsx` | Fixed |
| BUG-3 | **HIGH** | Memory panel shows "Loading..." indefinitely | `MemoryPanel.tsx` | Fixed |
| BUG-4 | **MEDIUM** | Chat auto-title defaults to "New Chat" | `src/api/server.py` lines 1600-1614 | Fixed |
| BUG-5 | **MEDIUM** | Safe Mode depends on Electron IPC, no browser fallback | `SafeModePanel.tsx` | Fixed |
| BUG-6 | **LOW** | Tool Execution panel shows permanent mock data | `ToolExecutionPanel.tsx` | Fixed |
| BUG-7 | **LOW** | Workspace delete shows wrong operator note | `App.tsx` `handleDeleteProject()` | Fixed |
| BUG-8 | **LOW** | Audit & Verify sub-panel doesn't expand | `ToolExecutionPanel.tsx` | Fixed |
| BUG-9 | **CRITICAL** | Default project file auto-indexing into Qdrant skipped (cache path mismatch) | `src/api/server.py` lines 80, 82-86, 1045 | Fixed |
| BUG-10 | **MEDIUM** | DOCX table content not extracted (python-docx limitation) | `src/api/file_processor.py` `_process_word()` | Fixed |
| BUG-11 | **LOW** | XLSX merged cells produce "Unnamed" column headers in markdown output | `src/api/file_processor.py` `_process_table()` | Fixed |
| BUG-12 | **MEDIUM** | Cloud `tools_off` path omitted `api_tokens_used` | `src/agent/nodes/complex.py` | Fixed |
| BUG-13 | **CRITICAL** | Web search turns stall on DeepSeek tool loop | `src/api/ws/handler.py` | Fixed |
| BUG-14 | **MEDIUM** | Cloud Cost Chip disappears on chat switch | `CloudSettingsPanel.tsx` | Fixed |
| BUG-15 | **LOW** | Cloud Usage popover transparent overlap | CSS styles | Fixed |
| BUG-16 | **MEDIUM** | Markdown tables overflow narrow chat panel | CSS styles | Fixed |
| BUG-17 | **HIGH** | Vision route not triggered deterministically | `src/agent/nodes/router.py` | Fixed |
| BUG-18 | **HIGH** | Simple-path empty visible reply | `src/agent/nodes/simple.py` | Fixed |
| BUG-19 | **MEDIUM** | Tool-call XML leaks as literal text in reply | `formatter.py` / `ws/handler.py` | Fixed |
| BUG-20 | **MEDIUM** | Greeting routed to `complex-cloud` instead of `simple` | `src/agent/nodes/router.py` | Fixed |
| BUG-21 | **CRITICAL** | Silent crash in notebook loop (exceeded recursion limit) | `defaults.yaml` & Graph run configs | Fixed |
| BUG-22 | **HIGH** | Notebook session leakage and infinite loop hangs | `src/tools/notebook.py` | Fixed |
| BUG-23 | **MEDIUM** | Legacy Word document (.doc) ingest & parsing failures | `src/api/shared.py`, `file_processor.py`, `core_tools.py` | Fixed |
| BUG-24 | **HIGH** | MiniCPM empty simple reply (F1.1) — `reasoning_content` only | `simple.py`, `handler.py` | Fixed |
| BUG-25 | **HIGH** | Eval harness `composer-stop` stuck 900s | `App.tsx`, eval waiter | Fixed |
| BUG-26 | **MEDIUM** | Scope/plan HITL stalls automated eval | eval scripts | Fixed |
| BUG-27 | **HIGH** | F5.1 cloud fail on tool-loop round 2 (bloated tool-call args) | `cloud_payload.py`, `complex.py` | Fixed |
| BUG-28 | **MEDIUM** | Browser eval mid-thread `large-cloud-failed` (circuit breaker) | `run_browser_eval.py` | Fixed |
| BUG-29 | **MEDIUM** | Educator stale assistant scrape (EDU6–8 = EDU5 text) | `run_local_frontier_eval.py` | Fixed |

### Architectural Concerns

| Concern | Impact | Status |
|---------|--------|--------|
| Electron IPC for Screen Assist / TTS | Screen Assist and TTS require Electron main process; no browser fallback | Open — by design for desktop-only features |
| Safe Mode in browser | REST fallback via `electronBridge.ts` when IPC unavailable | Mitigated (BUG-5 fixed) |
| Silent error handling | Some try/catch blocks swallow errors (profile updates, API calls) | Open — partial mitigation in BUG-3/BUG-4 |
| Memory/Orchestration loading UX | Panels could hang without feedback | Mitigated (BUG-2, BUG-3 fixed — error/empty states) |
| Tool panel stale data | Mock or stale execution entries after disconnect | Mitigated (BUG-6 fixed) |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Phase 8 complete | BUG-1 through BUG-11 fixed and verified | See [`docs/BUG-TRACKER.md`](BUG-TRACKER.md) |
| Live Talk removal | Simplified codebase, reduced maintenance | Lost voice interaction capability |
| Browser-first launch | `./start.sh` opens Vite; Electron optional via `npm run dev` | Desktop-only features inactive in browser |

## Next Plan

All known Phase 8 bugs (BUG-1 through BUG-29) are fixed. Open work is R10 (eval ≥97%) and architectural concerns marked Open in the table.

### Lingering Risks

| Risk | Context |
|------|---------|
| Electron on hold | Browser is primary launch mode. SafeMode, ScreenAssist, window sizing require Electron IPC — no browser fallbacks. |
| File processing extraction quality | \u26a0\ufe0f Improved — Docling replaces PyMuPDF/python-docx with layout-aware extraction + table detection. Model downloads on first use (~2 GB). |
| Web search | SearXNG recommended for self-hosted metasearch. DuckDuckGo is backup. |
| Workspace switching UI state | Stale UI in edge transitions |
| Frontend/backend WS payload drift | Integration path mismatches |
| Cloud fallback + anonymization | Best-effort redaction + hashed cloud `user` fingerprint; full NER/preview UI deferred |
| Router selection drift | Borderline prompts, long-context/tool-heavy prompts |
| CRUD invariants | Needs hardening under repeated operations |

## Related

- [`docs/BUG-TRACKER.md`](BUG-TRACKER.md) — canonical fix log (BUG-1..20)
- [`docs/COMPLETENESS_REVIEW.md`](COMPLETENESS_REVIEW.md) — frontier chat & co-work gap analysis (source of BUG-17..20)
- [`docs/BUG-ANALYSIS.md`](BUG-ANALYSIS.md) — historical audit symptoms
- [`docs/ADR.md`](ADR.md) — architecture decisions
- [`docs/PERFORMANCE_SLOS.md`](PERFORMANCE_SLOS.md) — performance targets

## Last updated

2026-06-16 — multi-model review fixes (notebook token gate, privacy hardening); see `changes/multi-model-review-fixes/CHANGELOG.md`
