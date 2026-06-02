# AGENTS.md — SDD Onboarding for Cursor Agents

> **Purpose:** Single entry point for every Cursor agent session in this repo. Read this before touching any code.

## Mandatory SDD Workflow

This repository enforces **Spec-Driven Development (SDD)** — specs before code, human gates between phases.

### Quick start

0. **To run the app:** read [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) — prerequisites, env setup, launch steps
1. Read [`docs/README.md`](docs/README.md) → [`docs/INDEX.md`](docs/INDEX.md)
2. Read [`docs/architecture/overview.md`](docs/architecture/overview.md)
3. Read [`specs/memory/constitution.md`](specs/memory/constitution.md) + [`docs/standards/coding-style.md`](docs/standards/coding-style.md)
4. Find active change: check [`specs/active/`](specs/active/) or run `/sdd-status`
5. For new changes: agent runs autonomous discovery (see `sdd-orchestrator` skill) — explores codebase, inventories tools, presents findings BEFORE any popups
6. If active change exists, read:
   - `specs/active/<slug>/requirements.md`
   - `specs/active/<slug>/design.md`
   - `specs/active/<slug>/tasks.md`
   - `.cursorplan/active/<slug>/plan.md`
   - `docs/changes/<slug>/CHANGELOG.md`
7. Then touch code

### SDD Phases (never skip)

| # | Phase | Cursor Mode | Artifact |
|---|-------|-------------|----------|
| 0 | Discovery | Plan | Proposal summary (no file — presented in chat) |
| 1 | Requirements | Plan | `specs/active/<slug>/requirements.md` |
| 2 | Design | Plan | `specs/active/<slug>/design.md` |
| 3 | Tasks | Plan | `specs/active/<slug>/tasks.md` |
| 4 | Implementation | Agent | Product code + `docs/changes/<slug>/CHANGELOG.md` |
| 5 | Verification | Agent | `specs/active/<slug>/verification-report.md` |
| done | Archive | Agent | Move to `specs/completed/<slug>/` |

### Hard gates (enforced by hooks + rules)

- **Plan mode:** NEVER write product code (enforced natively). Create only spec artifacts under `specs/`, `.cursorplan/`, `docs/changes/`, `.cursor/`, `docs/`.
- **Before requirements:** Agent MUST complete autonomous discovery — explore codebase, inventory tools, present findings (see `sdd-orchestrator` skill).
- **Before tasks-review:** Agent MUST run pre-task validation — AC coverage check, pattern consistency check, duplication check.
- **Agent mode:** NEVER implement until ALL of these approvals are `true` in `state.json`:
  - `approvals.requirements`
  - `approvals.design`
  - `approvals.tasks`
  - `approvals.implement`
- **Every phase transition** requires an **AskQuestion popup** with `approve` selected. Chat text like "looks fine" does NOT count.
- **Every implementation task** requires:
  1. Implementation
  2. Append to `docs/changes/<slug>/CHANGELOG.md`
- **All tasks done:** run ALL `verify_steps` from `tasks.md` → generate `verification-report.md` → `feature-verify-review` AskQuestion → on Approve, move to `specs/completed/`.

### Commands

| Command | Description |
|---------|-------------|
| `/sdd-init <slug>` | Scaffold a new SDD change |
| `/sdd-status` | Show current phase, approvals, pending review |
| `/sdd-verify` | Re-run verify_steps for active change |
| `/sdd-bootstrap <path>` | Copy harness into another project |

### Rules files (loaded automatically)

- `.cursor/rules/sdd-core.mdc` — always active; core SDD philosophy
- `.cursor/rules/sdd-plan-mode.mdc` — Plan-mode constraints
- `.cursor/rules/sdd-agent-mode.mdc` — Agent-mode constraints
- `.cursor/rules/coding-style.mdc` — Code conventions by file glob

### Skills

- `.cursor/skills/sdd-kiro-hitl/SKILL.md` — Human-in-the-loop AskQuestion popup scripts
- `.cursor/skills/sdd-orchestrator/SKILL.md` — Autonomous discovery, codebase exploration, pre-task validation

### Critical: never infer approval

The only valid approval is an **AskQuestion** response with `id` matching the phase and option `approve`. Chat confirmations are advisory and must be followed by the actual popup.

## Using this harness in another project

### New projects: GitHub template (easiest)

1. Use `Cursor_Spec_Driven` as a GitHub template — click "Use this template" on the repo page
2. Clone the new repo — all framework files are already in place
3. Open in Cursor, run `/sdd-init <slug>` to start your first change

### Existing projects: bootstrap

1. Clone this repo: `git clone https://github.com/maThiaslI152/Cursor_Spec_Driven /tmp/sdd-harness`
2. Run: `bash /tmp/sdd-harness/.cursor/hooks/sdd-bootstrap.sh /path/to/your-project`
3. Or in Cursor, open this repo and run `/sdd-bootstrap <path>`
4. Open your project in Cursor — framework loads automatically

The bootstrap only copies `.cursor/`, `.cursorplan/`, `specs/`, `docs/`, and `AGENTS.md`. Your existing `src/` and config files are untouched.

## Related

- [Enhancing Cursor's Agentic Mode.md](Enhancing%20Cursor's%20Agentic%20Mode.md) — research rationale
- [`docs/README.md`](docs/README.md) — full project map

## Last updated

2026-06-02 — autonomous orchestration layer + task-start-1 removal
