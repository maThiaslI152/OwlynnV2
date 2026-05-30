# Dogfood Test Plan: Cursor SDD Enforcement Harness

> **Purpose:** Validate the full SDD pipeline end-to-end. Use this harness itself as the first test subject — the harness files under `.cursor/`, `specs/`, `docs/`, and `.cursorplan/` are the "product code."

## E2E Test Procedure

### Phase 1: Plan Mode — Scaffold and Spec

1. In Normal/Ask mode, say: "I want to add a new feature X"
2. Agent should suggest Plan mode + `/sdd-init`
3. Run `/sdd-init test-feature` — verify scaffold created
4. Verify all directories and template files created under `specs/active/test-feature/`, `.cursorplan/active/test-feature/`, `docs/changes/test-feature/`
5. Verify `state.json` initialized with phase=requirements, all approvals false

### Phase 2: Requirements Popup

1. Agent drafts `specs/active/test-feature/requirements.md`
2. Agent shows `requirements-review` AskQuestion popup
3. Select **Approve** → verify `state.json.approvals.requirements=true`
4. Select **Revise** → verify agent edits requirements only, re-shows popup
5. Select **Cancel** → verify work stops cleanly

### Phase 3: Design + Tasks Popups

1. Same pattern as requirements: draft → popup → approve
2. Verify design-review and tasks-review popups appear
3. After tasks-review approve: verify plan saved to `.cursorplan/active/test-feature/plan.md`
4. Verify agent prompts to switch to Agent mode

### Phase 4: Agent Mode — Gate Checks

1. Switch to Agent mode
2. Before implement-review approve: attempt to write to `src/test.ts` → hook shows `ask` popup (native Cursor dialog)
3. Select **Deny** in popup → write blocked
4. Show `implement-review` AskQuestion → Approve
5. Now write to `src/test.ts` → should succeed

### Phase 5: Per-Task Protocol

1. Agent shows `task-start-1` → Start
2. Implement task — edit files within allowed_paths
3. AfterFileEdit hook fires → CHANGELOG reminder if no recent entry
4. Append CHANGELOG entry
5. Run verify_steps
6. Show `task-verify-1` → Pass

### Phase 6: Verification and Archive

1. After all tasks: agent generates `verification-report.md`
2. Show `feature-verify-review` → Approve
3. Files move to `specs/completed/test-feature/` and `.cursorplan/archive/test-feature/`

### Phase 7: Session Restart Memory

1. End session, start new session
2. Verify sessionStart hook injects active change context
3. Verify `SDD_ACTIVE_CHANGE` env var set

### Phase 8: Negative Tests

- [ ] Write before approvals → gate shows ask popup
- [ ] task-verify without CHANGELOG → rules block
- [ ] feature-verify-review without verification-report → rules block
- [ ] Edit outside allowed_paths → gate denies
- [ ] Revise on any popup → no auto-advance

## Automated Integrity Test

Run at any time to validate harness files and gate logic:

```bash
bash .cursor/hooks/sdd-harness-test.sh
```

### Last run results (2026-05-31)
- 63/63 checks passed
- Directory structure: 13/13
- Required files: 22/22
- JSON validity: 2/2
- Executable scripts: 3/3
- Shell syntax: 3/3
- MDC rules: 5/5
- Doc standards: 8/8
- Gate logic smoke: 7/7

## Success Criteria Verified

| Criterion | Status | Mechanism |
|-----------|--------|-----------|
| No product code without all approvals | PASS | sdd-gate.sh (failClosed) |
| No complete without verification-report + popup | PASS | Rules + state.json |
| Plan mode = specs only | PASS | Cursor native |
| Phase popups (AskQuestion) | PASS | sdd-kiro-hitl skill |
| Intent clarification for vague prompts | PASS | sdd-plan-mode rules |
| .cursorplan/ + CHANGELOG per change | PASS | Rules + hooks |
| docs/README.md agent onboarding | PASS | Created |
| Aligned folders per slug | PASS | /sdd-init command |

## Related

- [`AGENTS.md`](../../AGENTS.md) — full SDD workflow
- [`.cursor/hooks/sdd-harness-test.sh`](../../.cursor/hooks/sdd-harness-test.sh) — automated integrity test

## Last updated

2026-05-31 — `cursor-sdd-enforcement-harness` dogfood test plan
