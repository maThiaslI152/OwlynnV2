# Plan: plan-to-create-repo-and-push

## Linked specs
- specs/active/plan-to-create-repo-and-push/requirements.md
- specs/active/plan-to-create-repo-and-push/design.md
- specs/active/plan-to-create-repo-and-push/tasks.md

## Summary
Initialize this project (Cursor SDD Enforcement Harness) as a git repository, configure .gitignore, create a GitHub remote, and push all harness files.

## Scope (in / out)
**In scope:**
- `.gitignore` with exclusions for OS metadata, uploads, transcripts, MCP descriptors
- `git init` + initial commit on `main` branch
- GitHub repo creation via `gh` CLI (private, named `Cursor_Spec_Driven`)
- `git push -u origin main`

**Out of scope:**
- CI/CD, branch protection, README.md, collaborators, team settings

## Architecture decisions
- Use `gh` CLI for GitHub integration (simplest auth + repo creation)
- Exclude `mcps/`, `uploads/`, `agent-transcripts/` (Cursor runtime metadata, not project source)
- Private repo default (safety-first)
- No README.md (project uses AGENTS.md + docs/README.md)

## Task sequence (high level)
1. Create `.gitignore`
2. `git init` → `git add -A` → `git commit`
3. `gh repo create` → `git remote add` → `git push`

## Risks and open questions
- `gh` CLI must be authenticated; if not, guide user through `gh auth login`
- Repo name conflict handled by `gh repo create` error

## Approval history
- requirements-review: approved 2026-05-31
- design-review: approved 2026-05-31
- tasks-review: approved 2026-05-31
