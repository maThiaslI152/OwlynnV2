# Requirements: Browser-Only Startup

> **Purpose:** Update Owlynn's startup documentation, scripts, and agent skills to reflect browser-only development. Tauri desktop development is paused — mark it as such, keep code intact, but remove it from the active startup flow.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | Developer | `start.sh` to reliably launch containers, backend, and frontend in browser-only mode | I can start developing without Tauri overhead |
| US-2 | Developer | the `run-user-test` skill to launch the browser dev server instead of Tauri | Cursor agents don't try to build/launch Tauri when I ask to "launch Owlynn" |
| US-3 | Developer | the `dev-startup.md` guide to clearly state Tauri is paused and browser is the primary dev path | new contributors aren't confused by dual launch paths |
| US-4 | Developer | the backend to start reliably from the Cursor agent's Shell tool context | agents can start the backend without it dying prematurely |

## Acceptance Criteria (EARS format)

| ID | Criterion |
|----|-----------|
| AC-1 | When an agent reads `run-user-test.mdc`, it shall launch the browser dev server (Vite on port 5173) instead of Tauri (`tauri dev`). |
| AC-2 | When `./start.sh` is executed, it shall successfully start containers, backend, and frontend without any Tauri-related steps. |
| AC-3 | When reading `docs/guides/dev-startup.md`, the Tauri section shall be marked as **paused** with a clear notice that browser-only development is the current mode. |
| AC-4 | When the backend is started from the Cursor Shell tool (`uvicorn ... &`), it shall remain running and respond to health checks on port 8000. |
| AC-5 | When the frontend loads at `http://127.0.0.1:5173`, it shall proxy API requests to the backend without Tauri-specific IPC bridges being required. |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Reliability | `start.sh` must succeed on first run without manual intervention (assuming pre-existing containers and LM Studio). |
| NFR-2 | Documentation | All Tauri references in active docs/skills must clearly state "paused" and point to browser-only flow. |

## Edge Cases and Error States

- Backend port 8000 already in use — `start.sh` already handles this (kills stale port). Verify this works from agent context.
- LM Studio not running — `start.sh` already prompts user. No change needed.
- Containers not running — `start.sh` already auto-starts them. No change needed.
- Agent launches backend via Shell tool — must not exit prematurely (currently exits with code 0 after ~5s).

## Out of Scope

- Removing Tauri config/code from `src-tauri/` — code stays intact
- Removing Tauri from `package.json` scripts or dependencies
- Frontend build pipeline changes
- CI changes related to Tauri

## Dependencies

- None (standalone change to docs, scripts, and agent skills)

## References

- `start.sh` — current launcher (already says "browser-first, no Tauri")
- `.cursor/rules/run-user-test.mdc` — agent skill for launching Owlynn
- `docs/guides/dev-startup.md` — dev startup guide
- `src-tauri/` — Tauri config (untouched, marked paused)

## Approval

- `requirements-review` AskQuestion: approved (2026-06-01T19:18:00Z)
