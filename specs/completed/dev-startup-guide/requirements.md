# Requirements: Dev Startup Guide

> **Purpose:** Define what the change must do. Written in Plan mode before design. Must be approved via AskQuestion `requirements-review` popup before proceeding to design.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | Developer (or LLM agent) picking up this project cold | a single authoritative startup document that covers all prerequisites and launch steps | I can get the full app running without scanning multiple files, start.sh internals, or docker-compose.yml |
| US-2 | Developer running the app on a fresh machine | clear, sequential instructions for each prerequisite layer (containers, LM Studio, .venv, frontend deps) | I can bootstrap the project from scratch in one pass |
| US-3 | Developer debugging startup failures | a troubleshooting section per layer with common failure modes and fixes | I can self-diagnose issues without deep codebase knowledge |

## Acceptance Criteria (EARS format)

| ID | Criterion |
|----|-----------|
| AC-1 | When an LLM agent reads the startup guide, the system shall provide enough information to execute `./start.sh` successfully without needing to explore other files for setup steps. |
| AC-2 | When a human developer reads the startup guide, the system shall list all prerequisites (Python ≥3.11, Node ≥20, Podman/Docker, LM Studio) with install commands for macOS. |
| AC-3 | When the `.env` file is not yet configured, the guide shall document every mandatory variable, where to get the value, and the exact `cp` command from `.env.example`. |
| AC-4 | When LM Studio is not yet configured, the guide shall reference `docs/guides/lm_studio.md` for model setup and note the exact `.env` variables that must match loaded models. |
| AC-5 | When containers fail to start, the guide shall list the three container backends attempted by `start.sh` (podman compose → podman-compose → docker compose) and their minimum versions. |
| AC-6 | When the frontend dev server fails, the guide shall document the `cd frontend-v2 && npm install` step and the expected port (5173). |
| AC-7 | The guide shall be discoverable from `AGENTS.md` and `docs/README.md` so LLM agents find it on session start without scanning the full codebase. |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Discoverability | The startup guide must be linked from the "Quick start" section of `AGENTS.md` and `docs/README.md` reading order. |
| NFR-2 | Maintainability | The guide must reference `start.sh` and `.env.example` rather than duplicating volatile details — documentation should survive minor script/env changes. |
| NFR-3 | Completeness | The guide must cover all three tiers (infra containers, LLM backend, frontend) in dependency order. |

## Edge Cases and Error States

- What happens when the user has Docker but not Podman? `start.sh` fallback chain handles it — guide must document this.
- What happens when Redis is unavailable? Falls back to `MemorySaver` — guide must note this is fine for dev and the fallback is automatic.
- What happens when `start.sh` says `.venv` not found? Guide must document `python3 -m venv .venv && pip install -r requirements.txt`.

## Out of Scope

- Tauri desktop app build/packaging — browser-first dev flow only
- Production deployment
- LM Studio model selection recommendations (covered by `docs/guides/lm_studio.md`)
- Detailed Qdrant/Redis configuration (covered by `.env.example` comments)

## Dependencies

- `start.sh` (existing launcher script)
- `.env.example` (environment template)
- `docker-compose.yml` (container definitions)
- `docs/guides/lm_studio.md` (LM Studio setup guide)

## References

- `start.sh` — the single launcher script that orchestrates all three tiers
- `.env.example` — all configurable environment variables
- `docs/guides/quickstart.md` — existing chat UX guide (complement, not replacement)
- `docs/guides/lm_studio.md` — LM Studio model configuration

## Approval

- `requirements-review` AskQuestion: approved ✅
