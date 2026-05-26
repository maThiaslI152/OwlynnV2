---
last_verified: 2026-05-26
auto_generated: false
purpose: "Project status tracker: phase progress, test counts, active bugs (7), bug fix priority list, and lingering risks."
---

# Owlynn Status

## Overview

Project status tracker. Last updated: 2026-05-26 (Documentation audit).

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
| Phase 8 (Browser Audit Bug Fixes) | Pending | — |

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
| LangGraph flow (memory → route → complex → tool → memory) | Active |
| Hybrid model routing (small/medium/cloud) | Active |
| M-tier model swap logic | Active |
| Security proxy HITL approval | Active |
| Backend API + WebSocket chat | Active |
| Tauri frontend shell | Active |
| Live Talk (wake-word, STT) | Removed (2026-04-29) |
| TTS (`speak_text` via macOS `say`) | Active |

## Testing

| Suite | Status | Count |
|-------|--------|-------|
| Backend core (pytest) | Pass | 705+ passed (Phase 7), 0 failed, 5 skipped (Redis/integration) |
| Frontend-v2 (vitest) | Pass | 77+ passed |
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

| ID | Severity | Description | Location |
|----|----------|-------------|----------|
| BUG-1 | **CRITICAL** | Persona/system prompt leaks into first assistant response | `src/agent/nodes/simple.py` or `complex.py` |
| BUG-2 | **HIGH** | Orchestration panel empty after message processing | `src/api/server.py` or `OrchestrationPanel.tsx` |
| BUG-3 | **HIGH** | Memory panel shows "Loading..." indefinitely | `MemoryPanel.tsx` |
| BUG-4 | **MEDIUM** | Chat auto-title defaults to "New Chat" | `src/api/server.py` lines 1600-1614 |
| BUG-5 | **MEDIUM** | Safe Mode depends on Tauri IPC, no browser fallback | `SafeModePanel.tsx` |
| BUG-6 | **LOW** | Tool Execution panel shows permanent mock data | `ToolExecutionPanel.tsx` |
| BUG-7 | **LOW** | Workspace delete shows wrong operator note | `App.tsx` `handleDeleteProject()` |
| BUG-8 | **LOW** | Audit & Verify sub-panel doesn't expand | `ToolExecutionPanel.tsx` |

### Architectural Concerns

| Concern | Impact |
|---------|--------|
| Tauri IPC dependency leakage | SafeMode, ScreenAssist, TTS, window sizing require Tauri IPC — no browser fallbacks |
| Silent error handling | Multiple try/catch blocks swallow errors (chat title, profile updates, API calls) |
| Loading states without timeouts | Memory and Orchestration panels show "Loading..." indefinitely |
| Mock data in production | Tool Execution panel always shows demo entries |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Phase 8 priority order | BUG-1 (persona leak) is release blocker → BUG-2 → BUG-3 → BUG-5 → ... | Lower-priority bugs may remain post-release |
| Live Talk removal | Simplified codebase, reduced maintenance | Lost voice interaction capability |

## Next Plan

Phase 8 (post-audit bug fixes) — address 8 bugs found in browser audit:

| Priority | Item | Status |
|----------|------|--------|
| 1 | BUG-1 — Fix persona/system prompt leak | Pending |
| 2 | BUG-2 — Restore Orchestration panel routing data | Pending |
| 3 | BUG-3 — Fix Memory panel loading state | Pending |
| 4 | BUG-5 — Add browser fallback for Safe Mode | Pending |
| 5 | BUG-4 — Fix chat auto-title generation | Pending |
| 6 | BUG-6 — Remove mock data from Tool Execution | Pending |
| 7 | BUG-7 — Fix workspace delete operator note | Pending |
| 8 | BUG-8 — Fix Audit & Verify sub-panel expand | Pending |
| — | Add loading timeouts to Memory/Orchestration panels | Pending |
| — | Add error logging to silent try/catch blocks | Pending |

### Lingering Risks

| Risk | Context |
|------|---------|
| Workspace switching UI state | Stale UI in edge transitions |
| Frontend/backend WS payload drift | Integration path mismatches |
| Cloud fallback + anonymization | Regression protection needed |
| Router selection drift | Borderline prompts, long-context/tool-heavy prompts |
| CRUD invariants | Needs hardening under repeated operations |
