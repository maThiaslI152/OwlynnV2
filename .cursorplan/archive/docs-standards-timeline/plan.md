# Plan: docs-standards-timeline

## Linked specs
- specs/active/docs-standards-timeline/requirements.md
- specs/active/docs-standards-timeline/design.md
- specs/active/docs-standards-timeline/tasks.md

## Summary
Update the entire `docs/` folder with consistent YAML frontmatter + template standards across all docs, and create a unified changelog timeline aggregating all `docs/changes/*/CHANGELOG.md` entries so AI agents can quick-glance the project history and doc status.

## Scope (in / out)
**In scope:**
- YAML frontmatter standard (status, last_verified, category, owner) on every doc under docs/
- Standardized template structure (purpose blockquote, Related, Last updated)
- Update `docs/standards/documentation.md` as the single source of truth
- Unified timeline doc aggregating all docs/changes/*/CHANGELOG.md
- Update `docs/INDEX.md` with full recursive manifest including status and category
- Audit and update all existing docs (~50 files) for compliance
- Update `docs/README.md` to reference new artifacts

**Out of scope:**
- CI-level frontmatter validation hook
- Content changes beyond frontmatter/structure compliance
- Deleting or relocating any existing docs

## Architecture decisions
- Frontmatter uses YAML between `---` delimiters (standard markdown, parseable by any YAML tool)
- Unified timeline is a single `docs/PROJECT_TIMELINE.md` aggregating all changelogs chronologically
- Template structure codified in `docs/standards/documentation.md` (extending existing)

## Task sequence (high level)
1. Update `docs/standards/documentation.md` with enhanced standard (frontmatter + template)
2. Audit and update all top-level docs/*.md for compliance
3. Audit and update subfolder docs (architecture/, standards/, debugging/, guides/, technical/, archive/)
4. Generate unified timeline `docs/PROJECT_TIMELINE.md`
5. Update `docs/INDEX.md` with full recursive manifest + status/category
6. Update `docs/README.md` to reference new artifacts

## Risks and open questions
- ~50 files to audit — agent may hit context limits; batch into multiple tasks
- `docs/INDEX.md` currently lists 10 entries; need full recursive scan of ~50 files
- Some archive/ docs may have ambiguous status — mark as `archived` per AC-5

## Approval history
- requirements-review: pending
- design-review: pending
- tasks-review: pending
