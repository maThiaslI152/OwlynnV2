---
status: active
category: standards
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# Documentation Standards

> **Purpose:** How to write and structure project documentation.

## Frontmatter Schema

Every document **MUST** start with YAML frontmatter between `---` delimiters:

```yaml
---
status: active|archived|draft|obsolete
category: architecture|reference|guide|changelog|debugging|planning|standards|audit|archive
audience: agent|human|archive
last_updated: YYYY-MM-DD
owner: ai-agent|human
---
```

### Fields

| Field | Required | Values |
|-------|----------|--------|
| `status` | Yes | `active`, `archived`, `draft`, `obsolete` |
| `category` | Yes | Most specific category enum value |
| `audience` | Yes | `agent` — agents should read; `human` — history/overview; `archive` — skip unless asked |
| `last_updated` | Yes | ISO date (YYYY-MM-DD) |
| `owner` | Yes | `ai-agent` or `human` |

## Template Structure

1. **YAML frontmatter**
2. **`# Title`** — single H1
3. **Purpose blockquote** — 2–3 lines: `> **Purpose:** …`
4. **Content body** — H2 (`##`) for major sections
5. **`## Related`** — links to other docs
6. **`## Last updated`** — date + change slug

## Formatting

- **Mermaid** for flowcharts where helpful
- **Tables** for file maps and comparisons
- Keep files under ~400 lines; split when larger
- Code blocks with language tags

## Forbidden

- Orphan markdown in repo root (except `AGENTS.md`)
- Docs without `## Related` and `## Last updated`
- Deep H4+ nesting
- Stale `src/` paths — grep-verify before committing doc edits

## CHANGELOG Format (docs/changes/)

Optional historical record. New work does **not** require a CHANGELOG entry unless the user asks.

```markdown
## [Task N] YYYY-MM-DDTHH:MMZ
**Type:** feature | fix | refactor | docs | test | chore
**Summary:** One sentence.
### Files
- `path/to/file` — what changed
```

## Related

- [`coding-style.md`](coding-style.md) — code conventions
- [`../INDEX.md`](../INDEX.md) — manifest with audience tags

## Last updated

2026-06-10 — agent-first overhaul; added `audience` field; removed SDD CHANGELOG mandate
