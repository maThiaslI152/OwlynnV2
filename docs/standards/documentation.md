# Documentation Standards

> **How to write and structure project documentation.** All docs, changelogs, and spec artifacts **MUST** follow these rules.

## File Structure Rules

Every document **MUST**:

1. **Start with `# Title`** — single H1 at the top
2. **Include a 2-3 line purpose blockquote** immediately after the title:
   ```
   > **Purpose:** What this doc covers and when to read it.
   ```
3. **Use H2 (`##`) for major sections only** — no deep H4+ nesting
4. **Include `## Related` section** — links to other `docs/` paths or specs
5. **End with `## Last updated`** — date (YYYY-MM-DD) + change slug

## Formatting

- **Mermaid** for flowcharts and architecture diagrams
- **Tables** for comparisons, matrices, and structured data
- Keep files under approximately 400 lines; split longer docs into subfolders
- Use code blocks with language tags for all code examples

## Forbidden

- Orphan markdown files in repo root (except `AGENTS.md`)
- Docs without a `## Related` section
- Docs without a `## Last updated` footer
- Deeply nested headers (H4, H5, etc.)

## CHANGELOG Format (docs/changes/<slug>/CHANGELOG.md)

Every implementation task **MUST** append at least one entry using this exact format:

```markdown
## [Task N] YYYY-MM-DDTHH:MMZ
**Type:** feature | fix | refactor | docs | test | chore
**Spec:** AC-2, AC-3
**Summary:** One sentence describing what changed and why.
### Files
- `path/to/file.ts` — what changed
### Notes
- migrations, breaking changes, follow-ups
```

### Type Selection

| Type | Use when |
|------|----------|
| `feature` | New behavior per spec acceptance criteria |
| `fix` | Bug fix or regression correction |
| `refactor` | Code structure change with no behavior change |
| `docs` | Documentation only (no code) |
| `test` | Test additions or changes only |
| `chore` | Build, CI, tooling, dependency updates |

### Entry Timing

- Entry **MUST** be written before `task-verify-{n}` AskQuestion popup
- Missing entry blocks `task-verify` (enforced by `sdd-changelog.sh` hook)
- Multiple entries per task are allowed (e.g., multiple commits)

## Related

- [`docs/standards/coding-style.md`](coding-style.md) — code conventions
- [`specs/memory/constitution.md`](../../specs/memory/constitution.md) — non-negotiable rules
- [`specs/templates/`](../../specs/templates/) — fill-in templates

## Last updated

2026-05-31 — `cursor-sdd-enforcement-harness` initial doc standards
