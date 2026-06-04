# Design: Prep and Push to GitHub

> **Purpose:** Execution plan for git workflow. Written in Plan mode after requirements approved.

## Execution Plan

Straightforward git workflow — no code changes, no architecture. Steps:

1. **Stash or commit current work** — capture all tracked-file modifications and untracked files needed for the push
2. **Rebase onto origin/main** — pull latest remote and rebase current branch, resolving any conflicts
3. **Verify clean working tree** — `git status` must show no modified tracked files
4. **Run CI** — `./scripts/ci.sh --quick` must exit 0
5. **Push to main** — `git push origin main` (safe, no force)

## Rollback Plan

If push is rejected (remote divergence): `git pull --rebase origin main`, retry.

## Approval

- `design-review` AskQuestion: pending
