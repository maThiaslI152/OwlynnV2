# CHANGELOG: cursor-sdd-enforcement-harness

> **Change:** Initial implementation of the Cursor SDD Enforcement Harness.

## [Task 1] 2026-05-30T23:30:00Z
**Type:** feature
**Spec:** N/A (harness bootstrap)
**Summary:** Initial scaffold of SDD enforcement harness: specs templates, AGENTS.md, docs/ structure, .cursorplan/, .cursor/ rules, hooks, skills, and commands.
### Files
- `AGENTS.md` — agent onboarding entry point
- `docs/README.md` — project documentation map
- `docs/INDEX.md` — machine-readable manifest
- `docs/architecture/overview.md` — system architecture overview
- `docs/standards/coding-style.md` — coding conventions
- `docs/standards/documentation.md` — doc structure and CHANGELOG rules
- `docs/changes/cursor-sdd-enforcement-harness/CHANGELOG.md` — this file
- `.cursorplan/README.md` — plan persistence rules
- `specs/memory/constitution.md` — non-negotiable constraints
- `specs/memory/verification.md` — project-level test contract
- `specs/templates/requirements.md` — requirements template
- `specs/templates/design.md` — design template
- `specs/templates/tasks.md` — tasks template
- `specs/templates/verification-report.md` — verification report template
- `specs/templates/state.json` — state schema
- `.cursor/rules/coding-style.mdc` — code style enforcement
- `.cursor/rules/sdd-core.mdc` — core SDD rules (alwaysApply)
- `.cursor/rules/sdd-plan-mode.mdc` — Plan mode constraints
- `.cursor/rules/sdd-agent-mode.mdc` — Agent mode constraints
- `.cursor/skills/sdd-kiro-hitl/SKILL.md` — HITL popup skill
- `.cursor/commands/sdd-init.md` — scaffold command
- `.cursor/commands/sdd-status.md` — status command
- `.cursor/commands/sdd-verify.md` — verify command
- `.cursor/hooks.json` — hook wiring
- `.cursor/hooks/sdd-gate.sh` — preToolUse gate (failClosed)
- `.cursor/hooks/sdd-session.sh` — sessionStart context injection
- `.cursor/hooks/sdd-changelog.sh` — afterFileEdit CHANGELOG reminder
- `.cursor/hooks/sdd-allowlist.txt` — allowlist paths
- `.cursor/hooks/sdd-harness-test.sh` — integrity test (63 checks)
### Notes
- All hook scripts are executable and pass bash syntax check
- Gate logic tested: allowlists specs/.cursorplan/docs/changes, blocks product writes without approvals
- All 63 integrity checks pass via sdd-harness-test.sh
