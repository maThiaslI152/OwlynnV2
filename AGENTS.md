# AGENTS.md — Agent Onboarding

> **Purpose:** Single entry point for every Cursor agent session. Read this before touching code.

## Quick start (run app)

→ [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) — prerequisites, `./setup.sh` (first time), `./start.sh` (daily launch)

## Before editing code (required reads)

1. [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) — file map by task
2. [`docs/architecture/overview.md`](docs/architecture/overview.md) — system shape, modules, data flow
3. [`docs/standards/coding-style.md`](docs/standards/coding-style.md) — naming, patterns, lint

## Repo layout (top-level)

| Path | Role |
|------|------|
| `src/agent/` | LangGraph graph, nodes, router, LLM pool, HITL |
| `src/api/` | FastAPI routes + WebSocket handler |
| `src/config/` | `defaults.yaml` — single source of truth |
| `src/memory/` | STM/LTM/personal memory managers |
| `src/tools/` | Agent tool implementations |
| `frontend-v2/` | React + Electron UI |
| `tests/` | Python unit, property, contract, and benchmark tests |
| `scripts/ci.sh` | Local CI (run before push) |
| `scripts/run_browser_eval.py` | Playwright conversation eval (12 prompts) |
| `scripts/run_local_frontier_eval.py` | Frontier eval — `--profile auto/local/cloud`, `--cloud-off` |
| `scripts/archive/` | Retired one-off patch scripts (not CI) |
| `scripts/manual/` | Live tool smoke scripts (not pytest) |
| `docs/evaluations/` | Evaluation run reports (write after significant evals) |

## Task routing

| I want to… | Read | Edit |
|------------|------|------|
| Change routing / model selection | [`docs/EXTENDING_AGENT.md`](docs/EXTENDING_AGENT.md) | `src/agent/nodes/router.py`, `src/agent/router/`, `src/config/defaults.yaml` |
| Add or change a tool | [`docs/TOOLS.md`](docs/TOOLS.md) | `src/tools/`, `src/agent/tool_sets.py` |
| Change WebSocket events | [`docs/CHAT_PROTOCOL.md`](docs/CHAT_PROTOCOL.md) | `src/api/ws/handler.py`, `frontend-v2/src/` |
| Fix memory / context injection | [`docs/MEMORY.md`](docs/MEMORY.md) | `src/agent/nodes/memory.py`, `src/memory/` |
| Change HITL / approvals | [`docs/HITL.md`](docs/HITL.md) | `src/agent/hitl/`, `src/agent/nodes/{scope_clarify,plan_review,security_proxy}.py` |
| Debug a symptom | [`docs/debugging/README.md`](docs/debugging/README.md) | Follow symptom → file table |
| Change cloud / anonymization | [`docs/CLOUD-LLM-ARCHITECTURE.md`](docs/CLOUD-LLM-ARCHITECTURE.md) | `src/agent/nodes/complex.py`, `src/agent/nodes/complex_utils/` |
| Run or configure the app | [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) | `start.sh`, `setup.sh`, `.env` |
| Run CI / tests / evaluation | [`docs/standards/EVALUATION.md`](docs/standards/EVALUATION.md) | `scripts/ci.sh`, `scripts/run_*_eval.py` |

## Skip unless asked

- `docs/archive/` — superseded plans and legacy notes
- `docs/evaluations/` — conversation eval reports
- `docs/changes/` — per-feature changelogs from past work

## Before push

```bash
./scripts/ci.sh --quick
```

Pre-push hook runs this automatically. Skip only when intentional: `git push -o no-ci`.

## Related

- [`docs/README.md`](docs/README.md) — full documentation map
- [`docs/INDEX.md`](docs/INDEX.md) — machine-readable manifest (filter by `audience`)

## Last updated

2026-06-10 — CI/eval routing; BUG-13..16 fixes committed
