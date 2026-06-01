# Requirements: Prep and Push to GitHub

> **Purpose:** Define what the change must do. Written in Plan mode before design. Must be approved via AskQuestion `requirements-review` popup before proceeding to design.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | Developer | to prep the working tree (resolve conflicts, rebase, run CI) before pushing | the remote main branch stays clean and passing |
| US-2 | Developer | to push the current branch to `main` via safe (non-force) push | the latest changes are published on GitHub |

## Acceptance Criteria (EARS format)

| ID | Criterion |
|----|-----------|
| AC-1 | When the current branch is prepared, the system shall have zero merge conflicts against `origin/main`. |
| AC-2 | When CI is run (`./scripts/ci.sh --quick`), the system shall exit 0 with all checks passing. |
| AC-3 | When `git push origin main` is executed, the system shall succeed without `--force` and the remote shall be at the same HEAD commit as local. |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Reliability | Push must use safe (fast-forward / non-force) semantics only |
| NFR-2 | Safety | Working tree must be clean (no unstaged/modified tracked files) before push |

## Edge Cases and Error States

- What if `git rebase` produces conflicts that can't be auto-resolved?
- What if CI fails — should we fix or abort?
- What if `git push` is rejected due to remote divergence?

## Out of Scope

- Creating new branches or PRs
- Code reviews or design changes
- Deployments or releases

## Dependencies

- GitHub remote (`origin`) must be reachable
- Local CI dependencies (Python venv, node_modules) must be installed
- All unstaged changes must be committable

## References

- `scripts/ci.sh` — local CI runner

## Approval

- `requirements-review` AskQuestion: pending
