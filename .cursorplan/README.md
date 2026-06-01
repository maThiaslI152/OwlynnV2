# .cursorplan/ — Persisted SDD Plans

> **This directory mirrors Cursor Plan mode output into the repository.** Every SDD change must have a canonical plan here.

## Structure

```
.cursorplan/
├── README.md                          # This file
├── active/
│   └── <change-slug>/
│       ├── plan.md                    # Canonical plan (sections: linked specs, summary, scope, architecture decisions, task sequence, risks, approval history)
│       ├── plan.meta.json             # Metadata: change slug, specs_path, docs_changelog, cursor_plan_uri, updated_at
│       └── revisions/                 # Snapshots of prior plan versions
│           └── plan-001.md
└── archive/                           # Completed changes (mirrors specs/completed/)
    └── <change-slug>/
        └── plan.md
```

## Rules

1. **No implementation phase starts** unless `.cursorplan/active/<slug>/plan.md` exists and `tasks.md` references it (`plan_ref: .cursorplan/active/<slug>/plan.md`).
2. When Plan mode completes design/tasks, the plan MUST be written to `.cursorplan/active/<slug>/plan.md`.
3. On major revisions, snapshot the prior plan to `revisions/plan-NNN.md` before updating `plan.md`.
4. On `feature-verify-review` Approve, move the folder to `.cursorplan/archive/<slug>/`.

## plan.md Structure

```markdown
# Plan: <change-slug>
## Linked specs
- specs/active/<slug>/requirements.md
## Summary
## Scope (in / out)
## Architecture decisions
## Task sequence (high level)
## Risks and open questions
## Approval history
- requirements-review: approved YYYY-MM-DD
```

## plan.meta.json Structure

```json
{
  "change": "<slug>",
  "specs_path": "specs/active/<slug>",
  "docs_changelog": "docs/changes/<slug>/CHANGELOG.md",
  "cursor_plan_uri": null,
  "updated_at": "ISO-8601"
}
```

## Related

- [`specs/`](../specs/) — active and completed specs
- [`docs/changes/`](../docs/changes/) — per-change CHANGELOGs
- [`AGENTS.md`](../AGENTS.md) — SDD workflow

## Last updated

2026-05-31 — `cursor-sdd-enforcement-harness` initial scaffold
