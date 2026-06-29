# AGENTS.md — Agent Onboarding

> **Purpose:** Single entry point for every Cursor agent session. Read this before touching code.

## Quick start (run app)

→ [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) — prerequisites, `./setup.sh` (first time), `./start.sh` (daily launch)

## Before editing code (required reads)

1. [`docs/development/PROJECT_GUIDE.md`](docs/development/PROJECT_GUIDE.md) — file map by task
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
| `src/pdf/` | Unified PDF text intake (StirlingPDF + PyMuPDF fallback) |
| `src/integrations/` | External service clients (StirlingPDF) |
| `frontend-v2/` | React + Electron UI |
| `tests/` | Python unit, property, contract, and benchmark tests |
| `scripts/ci.sh` | Local CI (run before push) |
| `scripts/run_browser_eval.py` | Playwright conversation eval (12 prompts) |
| `scripts/run_local_frontier_eval.py` | Frontier eval — `--profile auto/local/cloud`, `--cloud-off`, `--strict-cloud` |
| `scripts/run_educator_eval.py` | Educator eval (EDU1–EDU8) — `--strict-cloud` |
| `scripts/archive/` | Retired one-off patch scripts (not CI) |
| `scripts/manual/` | Live tool smoke scripts (not pytest) |
| `docs/evaluations/` | Evaluation run reports (write after significant evals) |

## Task routing

| I want to… | Read | Edit |
|------------|------|------|
| Change routing / model selection | [`docs/development/EXTENDING_AGENT.md`](docs/development/EXTENDING_AGENT.md) | `src/agent/nodes/router.py`, `src/agent/router/`, `src/config/defaults.yaml` |
| Change PDF intake / OCR | [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) | `src/pdf/intake.py`, `src/integrations/stirling_pdf.py`, `docker-compose.yml` |
| Add or change a tool | [`docs/features/TOOLS.md`](docs/features/TOOLS.md) | `src/tools/`, `src/agent/tool_sets.py` |
| Change WebSocket events | [`docs/development/CHAT_PROTOCOL.md`](docs/development/CHAT_PROTOCOL.md) | `src/api/ws/handler.py`, `frontend-v2/src/` |
| Fix memory / context injection | [`docs/features/MEMORY.md`](docs/features/MEMORY.md) | `src/agent/nodes/memory.py`, `src/memory/` |
| Change HITL / approvals | [`docs/HITL.md`](docs/HITL.md) | `src/agent/hitl/`, `src/agent/nodes/{scope_clarify,plan_review,security_proxy}.py` |
| Debug a symptom | [`docs/debugging/README.md`](docs/debugging/README.md) | Follow symptom → file table |
| Change cloud / anonymization | [`docs/architecture/CLOUD-LLM-ARCHITECTURE.md`](docs/architecture/CLOUD-LLM-ARCHITECTURE.md) | `src/agent/nodes/complex.py`, `src/agent/nodes/complex_utils/` |
| Run or configure the app | [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md) | `start.sh`, `setup.sh`, `.env` |
| Run CI / tests / evaluation | [`docs/standards/EVALUATION.md`](docs/standards/EVALUATION.md) | `scripts/ci.sh`, `scripts/run_*_eval.py` |
| Change mode system (Normal/Study/Pentest) | — | `frontend-v2/src/components/ModeSwitcher.tsx`, `frontend-v2/src/state/useAppStore.ts`, `src/api/ws/handler.py` |
| Change study tools / courses | — | `src/tools/study_tools.py`, `src/api/routes/study.py`, `skills/` |
| Change pentest scenario | — | `scenarios/pentest/`, `src/memory/scenarios.py`, `frontend-v2/src/components/PentestScopePanel.tsx` |
| Change browser extension | [`docs/features/BROWSER_EXTENSION.md`](docs/features/BROWSER_EXTENSION.md) | `browser-extension/`, `src/api/routes/browser_extension.py` |

## Mode System

Owlynn has three modes that change the UI, tools, and system prompt:

| Mode | Response Style | Scenario | Sidebar | Right Panel |
|------|---------------|----------|---------|-------------|
| **Normal** | User choice | Auto-detected | Standard projects/chats | Orchestration, cloud usage |
| **Study** | `learning` (forced) | `study` (forced) | Courses, exam countdown, study progress | Study progress, weak areas |
| **Pentest** | `concise` (forced) | `pentest` (forced) | Scope & constraints panel | (MVP: sidebar only) |

- Mode is persisted per-project in `projects.json` (`mode` field)
- Mode switcher is in the left sidebar top
- Mode → WS payload: frontend sends `scenario_id` to backend
- Backend maps `scenario_id` to forced response_style and scenario injection
- `src/memory/project.py`: `_PROJECT_WRITABLE_FIELDS` includes `mode`

## Pentest Mode — Local-Only (Hard Enforcement)

Cloud APIs (DeepSeek, OpenAI, etc.) refuse security/pentest content. Pentest mode **always** uses the local model. No override.

- Config: `models.pentest` in `defaults.yaml` — set `model_name` to a dedicated pentest model
- Falls back to `models.small` (Qwen3 VL 4B) if no pentest model configured
- Accessor: `ConfigLoader.get_pentest_model_name()`
- Pentest mode forces `scenario_id="pentest"` and `response_style="concise"`
- Router returns `complex-default` (not `complex-cloud`) for pentest
- **Pentest model**: Gemma 4 12B Coder Q4 (`gemma-4-12b-coder-fable5-composer2.5-v1@q4_k_m`)
  - Winner of pentest benchmark (84.1% overall, 41 tok/s)
  - Benchmark: `scripts/bench_pentest_models.py`
  - Results: `docs/evaluations/pentest-model-benchmark-2026-06-28.md`

### Pentest Infrastructure (Kali VM)

Owlynn uses **Lima** (Apple Virtualization Framework) to run Kali Linux locally on macOS.

| Component | Setup | RAM |
|-----------|-------|-----|
| Lima VM | `./scripts/setup-kali-lima.sh` | ~2GB |
| Kali tools | Auto-installed on first boot (kali-linux-headless + tool suites) | — |
| SSH | Key auth, port 60022, user `kali` | — |
| tmux | Session `main` for Owlynn screen assist | — |

- Lima config: `lima/kali.yaml`
- VM name: `owlynn-kali`
- Auto-detected by pentest status API (`/api/pentest/status`)
- Bridged networking for raw socket access (nmap SYN scan, masscan)
- Falls back to remote Kali via SSH if Lima not available

## Study System

16 study tools in `src/tools/study_tools.py`:

| Tool | Purpose |
|------|---------|
| `course_register` | Register course, auto-creates workspace project when linked_files provided |
| `course_workspace_create` | On-demand workspace creation for existing course |
| `course_chat_create` | Create named chat in course project |
| `course_list` / `course_get` | List/get course metadata |
| `study_note_save` / `study_note_search` | Save/search study notes |
| `flashcard_deck_create` / `flashcard_review` | Create decks, SM-2 spaced repetition review |
| `flashcard_suggest` | Generate flashcard content from course files |
| `quiz_session_start` / `quiz_session_answer` | Multi-question quiz sessions |
| `study_session_log` | Log sessions for streak tracking |
| `study_weak_areas` | Detect weak topics from misconception history |
| `mastery_record` | Save mastery/misconception atoms to Mem0 |
| `export_study_sheet` | Export study guide as PDF/DOCX |

API endpoints: `GET /api/study/dashboard`, `GET /api/study/exam-countdown`

## Skip unless asked

- `docs/archive/` — superseded plans and legacy notes
- `docs/evaluations/` — conversation eval reports
- `docs/changes/` — per-feature changelogs from past work

## Before push

```bash
./scripts/ci.sh --quick
```

Pre-push hook runs this automatically. Skip only when intentional: `git push -o no-ci`.

## Learned Rules

### Evaluation Harness Modifications
When modifying or extending `scripts/run_local_frontier_eval.py` or any UI-driven test harness, **never rely on DOM element polling (e.g., `is_graph_busy`) to determine if a conversational turn is complete.** Always use the WebSocket event stream (specifically the `idle` status event) as the definitive source of truth to avoid race conditions during parallel tool execution or streaming delays.

### Frontend Error Handling
Do not allow API fetches or WebSocket unhandled promise rejections to fail silently with console warnings. Always surface operational and network failures visibly to the user using the project's toast notification library (e.g., `react-hot-toast`).

### Cache Key Generation for Chat Contexts
When generating cache keys for chat histories or context gatekeepers (e.g., in `cloud_payload.py`), ensure the key is resilient to follow-up messages. Always include the total message count (`len(messages)`) and a slice of the final message's content to guarantee cache invalidation on new turns.

## Related

- [`docs/README.md`](docs/README.md) — full documentation map
- [`docs/INDEX.md`](docs/INDEX.md) — machine-readable manifest (filter by `audience`)

## Last updated

2026-06-29 — Deep browser extension security audit (v1.3.0→v1.4.0): 12 critical/high fixes (fetch_urls broken, selector injection, get_html leaks, password masking, submit_form, constant-time token comparison), 8 medium fixes (WS message limits, message type allowlist, isSecureUrl exact match, reconnect backoff, configurable URL, cookieConsentCache persistence, screenshot consolidation, fetch_urls parallel), 3 low fixes (wait_for_navigation readyState check, innerHTML dead code removed, Moodle selector escaping). Memory multimodal content fix (BUG-41), base64 image display fix (BUG-42), WS error schema fix (BUG-43). Total BUG-41..52 fixed.
