# docs/INDEX.md — Machine Manifest

> **Machine-readable index of all documentation paths in this project.** Updated whenever a doc is added, renamed, or removed.

```yaml
manifest:
  version: 1
  generated: "2026-05-31T00:00:00Z"
  files:
    - path: docs/README.md
      summary: "Project documentation map, reading order, and SDD workflow quick reference."
      last_updated: "2026-05-31"

    - path: docs/INDEX.md
      summary: "This manifest — machine-readable index of all doc paths."
      last_updated: "2026-05-31"

    - path: docs/architecture/overview.md
      summary: "System context, bounded modules, data flow, and key entrypoints."
      last_updated: "2026-05-31"

    - path: docs/standards/coding-style.md
      summary: "Language-agnostic coding conventions, naming, file layout, imports, error handling, and lint commands."
      last_updated: "2026-05-31"

    - path: docs/standards/documentation.md
      summary: "Rules for writing project docs and CHANGELOG entries."
      last_updated: "2026-05-31"

    - path: docs/changes/
      summary: "Per-feature edit history with mandatory CHANGELOG.md per change."
      last_updated: "2026-05-31"

    - path: specs/memory/constitution.md
      summary: "Non-negotiable project constraints — SDD, HITL gates, artifact integrity, coding style, test discipline."
      last_updated: "2026-05-31"

    - path: specs/memory/verification.md
      summary: "Project-level test contract — default commands, pass criteria, agent verification protocol."
      last_updated: "2026-05-31"

    - path: specs/templates/requirements.md
      summary: "Template for requirements.md — user stories, EARS acceptance criteria, out-of-scope."
      last_updated: "2026-05-31"

    - path: specs/templates/design.md
      summary: "Template for design.md — architecture, mermaid diagrams, APIs, data model."
      last_updated: "2026-05-31"

    - path: specs/templates/tasks.md
      summary: "Template for tasks.md — checkbox tasks with depends_on, files, maps_to ACs, verify_steps."
      last_updated: "2026-05-31"

    - path: specs/templates/verification-report.md
      summary: "Template for verification-report.md — AC ↔ evidence ↔ status table."
      last_updated: "2026-05-31"
```

## Related

- [`docs/README.md`](README.md)
- [`AGENTS.md`](../AGENTS.md)

## Last updated

2026-05-31 — `cursor-sdd-enforcement-harness` initial manifest
