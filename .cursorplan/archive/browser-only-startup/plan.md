# Plan: Browser-Only Startup

> **Change:** browser-only-startup
> **Phase:** tasks approved — ready for implementation
> **Last updated:** 2026-06-01T19:22:00Z

## Summary

Overhaul the Owlynn startup process to be exclusively browser-based. Tauri desktop app development is paused — mark it as paused in docs, keep code intact, but remove it from the active startup flow in agent skills and documentation.

## Task Breakdown

| # | Task | Maps To | Files |
|---|------|---------|-------|
| 1 | Update `run-user-test.mdc` for browser-only launch | AC-1, AC-4 | `.cursor/rules/run-user-test.mdc` |
| 2 | Update `dev-startup.md` — mark Tauri as paused | AC-3 | `docs/guides/dev-startup.md` |
| 3 | Polish `start.sh` — consistency fixes | AC-2 | `start.sh` |
| 4 | Verify backend startup reliability | AC-4 | None (verification) |
| 5 | End-to-end browser-only startup verification | AC-1, AC-2, AC-5 | None (verification) |

## Key Decisions

- Tauri code stays intact, marked as paused in docs
- Backend startup fixed via `block_until_ms: 0` Shell tool pattern
- No new scripts or flags — just polish existing artifacts
- Browser dev server at `http://127.0.0.1:5173` is the primary launch target

## References

- `specs/active/browser-only-startup/requirements.md`
- `specs/active/browser-only-startup/design.md`
- `specs/active/browser-only-startup/tasks.md`
- `docs/changes/browser-only-startup/CHANGELOG.md`
