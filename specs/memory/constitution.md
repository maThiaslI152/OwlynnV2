# Project Constitution

> **Non-negotiable constraints for all agents and contributors.** Any deviation requires an ADR under `docs/architecture/decisions/ADR-NNN.md`.

## 1. Spec-Driven Development (SDD)

All non-trivial changes **MUST** follow the SDD pipeline:

```
requirements.md → design.md → tasks.md → implement → verify → completed/
```

No product code (`src/`) edits are permitted before all four implementation prerequisites are approved via AskQuestion popups.

## 2. Human-in-the-Loop Gates

Every phase transition **MUST** present an AskQuestion popup. The agent **MUST NOT** proceed until the user selects `approve`.

| Phase | AskQuestion `id` |
|-------|-------------------|
| Requirements complete | `requirements-review` |
| Design complete | `design-review` |
| Tasks complete | `tasks-review` |
| Begin implementation | `implement-review` |
| All tasks verified | `feature-verify-review` |

Chat text confirmations ("looks fine", "LGTM") are **NEVER** sufficient. Only popup `approve` selections count.

## 3. Artifact Integrity

- **Plan mode:** specs, plans, docs only — no product code.
- **Agent mode:** one task at a time from `tasks.md`, with CHANGELOG append + verify_steps before task-verify popup.
- **Every change** must have aligned folders under:
  - `specs/active/<slug>/` or `specs/completed/<slug>/`
  - `.cursorplan/active/<slug>/` or `.cursorplan/archive/<slug>/`
  - `docs/changes/<slug>/`

## 4. Coding Style

All code **MUST** follow [`docs/standards/coding-style.md`](docs/standards/coding-style.md). When editing an existing file, match its conventions. For new files, apply the project standard.

Linter/formatter commands are specified in `docs/standards/coding-style.md`. Run them before marking any task complete.

## 5. Test Discipline

- Every implementation task **MUST** include `verify_steps` in `tasks.md`.
- Agent **MUST** run all `verify_steps` before showing `task-verify-{n}` popup.
- Default test commands are defined in [`specs/memory/verification.md`](verification.md).
- `approvals.verify` is only set after `verification-report.md` is generated and `feature-verify-review` is approved.

## 6. Change Tracking

Every implementation task **MUST** append an entry to `docs/changes/<slug>/CHANGELOG.md` using the strict format defined in `docs/standards/documentation.md`.

## 7. Documentation Standards

All project docs **MUST** follow the structure rules in [`docs/standards/documentation.md`](docs/standards/documentation.md). No orphan markdown files in repo root (except `AGENTS.md`).

## 8. Scope Enforcement

Each change has an `allowed_paths` list in `state.json`. The `sdd-gate.sh` hook **MUST** deny writes outside these paths when implementation is active.

## Related

- [`docs/standards/coding-style.md`](../docs/standards/coding-style.md)
- [`docs/standards/documentation.md`](../docs/standards/documentation.md)
- [`specs/memory/verification.md`](verification.md)
- [Enhancing Cursor's Agentic Mode.md](../../Enhancing%20Cursor's%20Agentic%20Mode.md)

## Last updated

2026-05-31 — `cursor-sdd-enforcement-harness` initial constitution
