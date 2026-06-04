# Plan: project-qa-sweep

> **Purpose:** CI/testing suite audit and comprehensive project QA testing.

## Goal

Audit the CI pipeline and testing suite for relevance, identify gaps, and then test the project across three critical axes:
1. Workspaces should behave correctly
2. Chat should support long conversations without cutoff or weird memory recall
3. HITL popups should be context-aware, not just templated

## Scope

Full sweep — audit + CI fixes + test workspace/chat/HITL end-to-end. No constraints on what can be fixed.

## Approach

4 phases, 10 tasks:

**Phase 1 — CI Infrastructure (Tasks 1-4):**
- Recreate missing pre-push hook (`.git/hooks/pre-push`)
- Add `--strict-markers` to pytest.ini
- Add coverage baseline config (pytest-cov, report only)
- Fix benchmark harness (empty report issue), add `--benchmarks` flag to ci.sh

**Phase 2 — Workspace Testing (Task 5):**
- Run property tests: `test_project_context_isolation_properties.py`, `test_complex_workspace_paths.py`
- Run unit tests: `test_workspace_tool_automation.py`, `test_crud_operations.py`, `test_project_chat_management.py`
- Fix any failures found

**Phase 3 — Long Conversation Testing (Task 6):**
- Run continuity tests: `test_conversation_continuity.py`, `test_conversation_continuity_properties.py`
- Run summarize tests: `test_auto_summarize_threshold_properties.py`, `test_protected_message_preservation_properties.py`
- Run isolation tests: `test_separate_chat_histories_properties.py`, `test_bugfix_persona_leak.py`
- Fix any failures found

**Phase 4 — HITL Context-Awareness (Tasks 7-9):**
- Baseline: run `test_hitl_graph_routing.py`, `test_multi_chat_hitl_e2e.py`, audit context code
- E2E manual: trigger all 4 HITL types (router, scope clarify, security proxy, plan review)
- Post-merge: re-test after `hitl-context-awareness` merges

**Phase 5 — Final CI + Report (Task 10):**
- Full `ci.sh` run (all stages)
- Generate `verification-report.md`

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Coverage: baseline only (no threshold) | Enforcing a threshold now without agreed-upon target would block CI |
| Benchmarks: opt-in `--benchmarks` flag, not default | Adds latency; developers can opt in |
| HITL: baseline before, retest after merge | Ensures regression-free improvements |
| Pre-push hook: create only if missing | Don't overwrite custom hooks silently |

## Risks

- **hitl-context-awareness overlap**: HITL tests run against current state first, then post-merge — handles this
- **Benchmark harness may be broken**: If `run.py` doesn't work, may need fix — scoped to Task 4
- **Existing test failures**: If tests were already broken before this sweep, fix them (in scope, no constraints)

---

**Status:** tasks approved 2026-06-02T06:39:00Z — ready for Agent mode implementation.
