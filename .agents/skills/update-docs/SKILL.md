---
name: update-docs
description: Update project documentation to reflect code changes. Trigger after implementing features, fixing bugs, or modifying architecture. Scans git diff, maps changes to docs, and updates them.
---

# Update Documentation

Keep documentation in sync with code changes. Run this after any significant code modification.

## Workflow

### Step 1: Identify Changes

Run `git diff --name-only HEAD` and `git diff --stat` to find what changed. If there are no uncommitted changes, compare against the last commit: `git diff --name-only HEAD~1`.

Group changed files by area:

| Changed path | Doc area to check |
|---|---|
| `src/agent/nodes/*.py` | `docs/architecture/`, `docs/development/`, `AGENTS.md` |
| `src/agent/routing/*.py` | `docs/development/EXTENDING_AGENT.md`, `docs/architecture/overview.md` |
| `src/tools/*.py` | `docs/features/TOOLS.md`, `AGENTS.md` task routing table |
| `src/api/routes/*.py` | `docs/API_REFERENCE.md`, `docs/development/CHAT_PROTOCOL.md` |
| `src/api/ws/*.py` | `docs/development/CHAT_PROTOCOL.md` |
| `src/memory/*.py` | `docs/features/MEMORY.md` |
| `src/config/*.py` or `defaults.yaml` | `docs/architecture/overview.md`, relevant feature docs |
| `src/pdf/*.py` | `docs/guides/dev-startup.md` |
| `frontend-v2/src/**/*.tsx` | `docs/architecture/overview.md`, relevant feature docs |
| `docker-compose.yml` | `docs/guides/dev-startup.md`, `docs/architecture/overview.md` |
| `scripts/*.sh` or `scripts/*.py` | `docs/standards/EVALUATION.md`, `docs/guides/dev-startup.md` |
| `.agents/skills/*/SKILL.md` | `AGENTS.md` skills section |
| `src/agent/hitl/*.py` | `docs/HITL.md` |
| `src/memory/semantic_cache.py` | `docs/features/SEMANTIC_CACHE.md` |
| `src/agent/core/graph.py` | `docs/architecture/POSTGRES_MEMORY_LIFECYCLE.md` |

### Step 2: Find Referencing Docs

For each changed file, search the `docs/` directory and `AGENTS.md` for references to that file path. Use grep:

```
grep -rl "path/to/changed/file" docs/ AGENTS.md
```

Also check if the changed module is mentioned in:
- `docs/INDEX.md` (machine manifest)
- `docs/README.md` or `docs/INDEX.md` (navigation)
- Any `CHANGELOG.md` in `docs/changes/`

### Step 3: Read and Update Each Doc

For each doc that references changed code:

1. **Read the doc** to understand its structure and conventions
2. **Verify accuracy** — does the doc still describe the code correctly?
3. **Update stale content**:
   - Function signatures that changed
   - File paths that moved
   - New parameters or config options
   - Removed features or deprecated code
   - New tools, nodes, or modules
4. **Update timestamps** — find the `last_updated:` field in frontmatter or `Last updated` line and set it to today's date (`YYYY-MM-DD`)
5. **Preserve style** — match the existing doc's formatting, heading levels, and conventions

### Step 4: Update AGENTS.md Task Routing Table

If the change adds a new module, tool, or feature area:

1. Check if a row already exists in the "Task routing" table in `AGENTS.md`
2. If not, add a row following the existing format: `| I want to… | Read | Edit |`
3. If the row exists but the "Edit" column is stale, update it

### Step 5: Update docs/INDEX.md

If any doc's `last_updated` changed:

1. Read `docs/INDEX.md`
2. Find the matching entry in the YAML manifest
3. Update its `last_updated` field
4. Bump the `manifest.version` if entries were added/removed
5. Update `manifest.generated` timestamp

### Step 6: Create Changelog Entry (if significant)

If the change is a user-facing feature or a breaking change:

1. Create `docs/changes/<feature-name>/CHANGELOG.md` following the existing pattern
2. Use format: `## <date> — <summary>` with sections for What, Why, Files

## Rules

- **Never delete docs** — only update or add. If a doc is fully obsolete, mark it with `status: deprecated` in frontmatter.
- **Never add comments** to code files — only update `.md` files.
- **Preserve frontmatter** — keep all YAML frontmatter fields, only update `last_updated`.
- **Use today's date** for all timestamps, format: `YYYY-MM-DD`.
- **Be surgical** — only modify the lines that are stale. Don't rewrite entire sections.
- **Check before editing** — always read the file first to understand its structure.

## Quick Reference: Common Updates

### New tool added
1. `docs/features/TOOLS.md` — add to appropriate toolbox section
2. `AGENTS.md` — update task routing if it maps to a new "I want to…" row
3. `src/agent/nodes/security_proxy.py` — check if it needs to be in `SENSITIVE_TOOLS` or `SAFE_TOOLS`

### New config option in defaults.yaml
1. Find the feature doc that covers this config area
2. Add the option to the relevant config table or section
3. Document the env var override if applicable

### New API endpoint
1. `docs/API_REFERENCE.md` or create if needed
2. `docs/development/CHAT_PROTOCOL.md` if it's a WebSocket event
3. `AGENTS.md` if it changes task routing

### New node in agent graph
1. `docs/architecture/overview.md` — add to module table
2. `docs/development/EXTENDING_AGENT.md` if it changes routing
3. `AGENTS.md` task routing table

### Security-related change
1. `docs/HITL.md` if it affects approval flow
2. `docs/architecture/CLOUD-LLM-ARCHITECTURE.md` if it affects cloud calls
3. Any feature doc that references the changed security mechanism
