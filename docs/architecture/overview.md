# Architecture Overview

> **System context, bounded modules, data flow, and key entrypoints.** Update when the project structure meaningfully changes.

## Bounded Context

This project is the **Cursor SDD Enforcement Harness** — a set of Cursor-native artifacts (rules, hooks, skills, commands, templates) that enforce Spec-Driven Development inside the Cursor IDE.

It operates **entirely within a single Git repository** and uses Cursor's hook system, rule files, and AskQuestion popups to simulate a phased SDD pipeline.

## Key Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| **Hooks** | `.cursor/hooks/` | `preToolUse`, `sessionStart`, `afterFileEdit` — programmatic enforcement |
| **Rules** | `.cursor/rules/` | Advisory context for agents — SDD phases, mode-specific constraints |
| **Skills** | `.cursor/skills/sdd-kiro-hitl/` | AskQuestion popup scripts for HITL gates |
| **Commands** | `.cursor/commands/` | Slash commands: `/sdd-init`, `/sdd-status`, `/sdd-verify` |
| **Plans** | `.cursorplan/` | Persisted SDD plans synced from Cursor Plan mode |
| **Specs** | `specs/` | Active and completed requirements, design, tasks, verification |
| **Docs** | `docs/` | Project map, standards, architecture docs, per-change changelogs |

## Data Flow (SDD Pipeline)

```mermaid
flowchart LR
  User(User) --> Plan[Plan Mode]
  Plan --> R[requirements.md]
  R -->|AskQuestion| D[design.md]
  D -->|AskQuestion| T[tasks.md]
  T -->|AskQuestion| CP[.cursorplan/ plan.md]
  CP -->|Switch to Agent| Agent[Agent Mode]
  Agent -->|implement-review popup| Hook[Hook gate]
  Hook -->|pass| Code[src/ code]
  Code --> CH[CHANGELOG.md]
  CH --> VS[verify_steps]
  VS -->|task-verify popup| VR[verification-report.md]
  VR -->|feature-verify popup| Archive[specs/completed/]
```

## Key Entrypoints

| Entrypoint | Type | Description |
|------------|------|-------------|
| `AGENTS.md` | Doc | Agent session start — SDD workflow summary |
| `docs/README.md` | Doc | Full project map and reading order |
| `.cursor/rules/sdd-core.mdc` | Rule | Always-on SDD enforcement context |
| `.cursor/hooks.json` | Config | Hook wiring — gate, session, changelog |
| `.cursor/hooks/sdd-gate.sh` | Script | Main enforcement gate (preToolUse) |
| `specs/memory/constitution.md` | Spec | Non-negotiable constraints |
| `state.json` | State | Current phase, approvals, verification status |

## Related

- [`docs/README.md`](../README.md) — project map
- [`specs/memory/constitution.md`](../../specs/memory/constitution.md) — constraints
- [Enhancing Cursor's Agentic Mode.md](../../Enhancing%20Cursor's%20Agentic%20Mode.md) — rationale

## Last updated

2026-05-31 — `cursor-sdd-enforcement-harness` initial architecture doc
