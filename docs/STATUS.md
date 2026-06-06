---
status: active
category: standards
last_updated: 2026-06-04
owner: human
---

# Owlynn Status

> **Purpose:** Project status tracker — bug inventory, phase progress, current risks, and remaining tasks.

## Overview

Project status tracker. Last updated: 2026-06-05 — DeepSeek V4 integration, SwapManager removal, and security hardening.

## Recent Changes (2026-06-04)

| Change | Impact | Commits |
|--------|--------|---------|
| **DeepSeek V4 Upgrade** | 1M Context window, extra_body config, SwapManager removal, Vision guardrail | pending |
| **Config centralization** | ~100 settings → 1 file (`defaults.yaml`). Override chain: YAML → env → profile | `bb04b25` |
| **Qwen3.5 model swap** | Router: qwen3.5-0.8b. Complex: qwen3.5-9b Q6_K. Author-tuned. | `dd69035` → `6367323` |
| **14 bugs fixed** | HITL GraphInterrupt, keyword bypass, thinking budgets, request_timeout, startup race, context overflow | `2b907d2` → `acd9f8d` |
| **Router bypasses** | Code review, creative writing, explain/compare → force complex (9B model) | `6da48bd` |
| **Config audit** | 4 missing entries, 6 stale fallbacks synced, ConfigValidator (60+ paths) | `4011a27` |
| **Model preloading** | Both models preload + warmup at startup. No more 0s first-call failures. | `acd9f8d` |
| **Documentation** | HITL.md, MEMORY.md, architecture overview rewritten, INDEX.md v3 | `ce736b5` → `4ea8223` |

## Current Model Config

| Slot | Model | Context | Temp | Max Tokens |
|------|-------|---------|------|------------|
| Router | `qwen3.5-0.8b` | 16384 | 0.2 | 1024 |
| Complex | `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` | 16384 | 0.7 | 16384 |
| Cloud | `deepseek-v4-flash` | 1048576 | 0.4 | 8192 |

## Evaluation Trajectory

| Eval | Score | Key Finding |
|------|-------|------------|
| v4 (gemma-4 baseline) | 4.02 | Complex latency 180-350s |
| v5 (Qwen3.5 initial) | 2.44 | 33% error rate, 9/12 misrouted |
| v6 (HITL + budgets) | 3.67 | 0 errors, medium model working |
| v7-final | ~4.0 est. | Bypasses confirmed, preload working |

## Remaining Tasks

### 🔴 High Impact
- **R1**: One-turn lag — message correlation IDs in browser (✅ Fixed)
- **R5**: Response coherence check — detect wrong answers, calibrate confidence
- **R2**: Inference latency — 105-276s vs SLO <8s (✅ Fixed via context optimization for M4 Air)

### 🟡 Medium Impact
- **R3**: Cloud fallback test with valid DeepSeek key
- **R7**: Verify web search aggregate timeout (coded, untested)
- **R9**: Verify API thread persistence (coded, untested)
- **R8**: Thermal throttling — run evals on AC power, not battery (✅ Mitigated via defaults.yaml)

### 🟢 Documentation & Code Health
- D1: Decompose `server.py` (✅ Extracted 2283 lines into src/api/routes)
- D2: Refactor `complex.py` (✅ Extracted fallback and formatting utilities)

## Entry Points

```text
docs/STATUS.md                # This file
docs/BUG-ANALYSIS.md          # Bug inventory and analysis
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
| `small_llm_model_name` | `ibm-grok4-ultrafast-coder-1b` |
| `medium_models.default` | `gemma-4-e4b-uncensored-hauhaucs-aggressive` |

### Core Capabilities Status

| Capability | Status |
|------------|--------|
| LangGraph flow (memory \u2192 route \u2192 complex \u2192 tool \u2192 memory) | Active |
| Hybrid model routing (small/medium/cloud) | Active |
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

### Architectural Concerns

| Concern | Impact |
|---------|--------|
| Electron IPC dependency leakage | SafeMode, ScreenAssist, TTS, window sizing require Electron IPC — no browser fallbacks |
| Silent error handling | Multiple try/catch blocks swallow errors (chat title, profile updates, API calls) |
| Loading states without timeouts | Memory and Orchestration panels show "Loading..." indefinitely |
| Mock data in production | Tool Execution panel always shows demo entries |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Phase 8 priority order | BUG-1 (persona leak) is release blocker \u2192 BUG-2 \u2192 BUG-3 \u2192 BUG-5 \u2192 ... | Lower-priority bugs may remain post-release |
| Live Talk removal | Simplified codebase, reduced maintenance | Lost voice interaction capability |

## Next Plan

All known Phase 8 bugs (BUG-1 through BUG-11) have been fixed. Remaining architectural concerns tracked above.

### Lingering Risks

| Risk | Context |
|------|---------|
| Electron on hold | Browser is primary launch mode. SafeMode, ScreenAssist, window sizing require Electron IPC — no browser fallbacks. |
| File processing extraction quality | \u26a0\ufe0f Improved — Docling replaces PyMuPDF/python-docx with layout-aware extraction + table detection. Model downloads on first use (~2 GB). |
| Web search | SearXNG recommended for self-hosted metasearch. DuckDuckGo is backup. |
| Workspace switching UI state | Stale UI in edge transitions |
| Frontend/backend WS payload drift | Integration path mismatches |
| Cloud fallback + anonymization | Regression protection needed |
| Router selection drift | Borderline prompts, long-context/tool-heavy prompts |
| CRUD invariants | Needs hardening under repeated operations |

## Related

- [`docs/BUG-ANALYSIS.md`](BUG-ANALYSIS.md) — bug inventory and analysis
- [`docs/ADR.md`](ADR.md) — architecture decisions
- [`docs/PERFORMANCE_SLOS.md`](PERFORMANCE_SLOS.md) — performance targets

## Last updated

2026-05-31 — `docs-standards-timeline` bug status reconciliation
