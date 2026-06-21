# Owlynn — Local AI Cowork Agent

[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![Node](https://img.shields.io/badge/node-18+-green)](https://nodejs.org)
[![CI](https://img.shields.io/badge/CI-local_scripts%2Fci.sh-059669)](scripts/ci.sh)
[![Frontend](https://img.shields.io/badge/frontend-React_19_%2B_Vite_8-61DAFB)](frontend-v2/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A private AI productivity agent with **cloud-primary DeepSeek V4** routing and local fallback. LangGraph orchestration, MiniCPM5 router + optional local Qwen9B fallback, Florence-2 vision proxy for images, semantic memory, and an Electron desktop UI. Optimized for Apple Silicon (M4 Air 24GB).

## Goal

Owlynn is a **desktop AI coworker** that keeps your data local. It reasons through complex tasks, calls tools (web search, file ops, document generation, notebook execution, screen/terminal context), remembers across sessions via vector memory, and gates sensitive operations behind human approval — cloud escalation is opt-in.

**Target user**: Developers and power users on Apple Silicon who want a privacy-respecting assistant with pentest/research workflows, optional cloud reasoning, and extensible tools/skills.

## Highlights

| Capability | Summary |
|------------|---------|
| **Routing** | MiniCPM5 router → `simple` \| `complex-default` \| `complex-cloud` |
| **Memory orchestration** | Split inject (`memory_inject_lite` → router → gated `memory_retrieve`), async 8B extraction, PII scrub, pentest/research scenarios |
| **Vision proxy** | Local VLM → JSON OCR → text-only DeepSeek path; lazy load + idle unload |
| **Screen assist** | macOS tmux capture, Accessibility API, browser tab, Kali SSH tmux (Python tools) |
| **HITL** | Security proxy + plan review for sensitive tool calls |
| **Search** | Browser extension (tier 0.2) → curl_cffi → DDGS → Playwright; SearXNG opt-in |

Full roadmap: [`docs/guides/memory-vision-screen-roadmap.md`](docs/guides/memory-vision-screen-roadmap.md)

## Entry Points

```text
src/api/server.py            # FastAPI (REST + WebSocket + OpenAI-compatible API)
src/agent/graph.py           # LangGraph builder, init_agent()
frontend-v2/electron/main.ts   # Electron main process
frontend-v2/src/App.tsx        # React shell + WebSocket lifecycle
./start.sh                     # Full stack launcher
```

## Architecture

```text
User Message
    │
    ▼
memory_inject_lite ──► profile, persona, topics (no vector search)
    │
    ▼
router ──► simple | complex-default | complex-cloud; memory gate + scenario
    │
    ▼
memory_retrieve ──► gated Qdrant/Mem0 + scenario markdown (when needed)
    │
    ▼
auto_summarize? ──► if tokens > 85% context window
    │
    ├── simple ──► memory_write ──► END
    │
    └── scope_clarify ──► complex_llm ◄──┐
              │              │            │
              │    [images + cloud] vision_proxy → DeepSeek (text only)
              │              │            │
              │    plan_review / security_proxy (HITL)
              │              ▼
              │         tool_action ─────┘
              │
              ▼
         memory_write ──► PII scrub → Redis extraction queue → END
```

Routes: **`simple`**, **`complex-default`** (local Qwen), **`complex-cloud`** (DeepSeek V4). Legacy `complex-vision` / `complex-longctx` routes removed.

### Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + LangGraph + Python 3.11+ |
| Frontend | React 19 + TypeScript (Vite 8) + Zustand 5, Electron desktop |
| Router LLM | `minicpm5-1b` (classification) |
| Medium LLM | `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` (local complex + vision proxy) |
| Cloud LLM | `deepseek-v4-flash` / `deepseek-v4-pro` (optional `complex-cloud`) |
| File processing | Docling v2 (PDF/DOCX → markdown) |
| Memory | Mem0 + Qdrant + JSON STM; Redis extraction worker |
| Checkpointing | Redis (`AsyncRedisSaver`; falls back to in-memory) |
| Search | Multi-tier: browser extension → curl_cffi / DDGS → Playwright; SearXNG opt-in |
| Testing | pytest + hypothesis (backend), vitest (frontend) |
| CI | Local [`scripts/ci.sh`](scripts/ci.sh) (pre-push hook) |

## Project Structure

```text
src/agent/
  graph.py, llm.py, state.py, tool_sets.py
  nodes/
    router.py, complex.py, simple.py, memory.py, summarize.py
    complex_utils/vision_proxy.py, vision_schema.py, vision_model_manager.py
    security_proxy.py, scope_clarify.py, plan_review.py

src/memory/
  long_term.py, memory_manager.py, personal_assistant.py
  extraction/          # async 8B atom extractor (Redis stream)
  scenarios.py         # pentest + research L2/L3 markdown loader
  compression.py       # cloud brief memory block

src/tools/
  core_tools.py, web_tools.py, doc_generator.py, notebook.py, skills.py
  screen_assist/       # tmux, AX, browser, Kali SSH tools

scenarios/
  pentest/, research/  # playbook + constraints markdown

frontend-v2/           # React + Electron UI
tests/                 # pytest + benchmarks
docs/                  # architecture, guides, API reference
```

## Configuration

Settings live in `src/config/defaults.yaml` (override chain: YAML → env → `user_profile.json`).

### Environment Variables

| Variable | Description |
|----------|-------------|
| `REDIS_URL` | LangGraph checkpointing + memory extraction stream |
| `QDRANT_HOST` / `QDRANT_PORT` | Vector memory |
| `SEARXNG_URL` | Optional self-hosted search — not started by `./start.sh`; run `podman compose --profile searxng up -d searxng` first |
| `DEEPSEEK_API_KEY` | Optional cloud route (`complex-cloud`) |
| `KALI_SSH_HOST` | Remote Kali VM for `capture_kali_terminal` |
| `SCREEN_ASSIST_TMUX_SESSION` | Default local tmux session name |
| `OPTIMIZE_FOR_M4` | M4 Air timeouts and memory limits |

### LLM Setup

| Slot | Default model | Role |
|------|---------------|------|
| Small | `minicpm5-1b` | Router |
| Medium | `qwen3.5-9b-...@q6_k` | Local complex + vision proxy |
| Cloud | `deepseek-v4-flash` | DeepSeek V4 (`complex-cloud`) |

Local models via LM Studio on port `1234`.

## Testing

```bash
./scripts/ci.sh              # Full suite (Python + frontend + build)
./scripts/ci.sh --quick      # Skip frontend production build
./scripts/ci.sh --python-only
./scripts/ci.sh --benchmarks # Optional latency benchmarks
```

**Current suite (local CI):** ~884 backend tests (pytest), 107 frontend tests (vitest). Benchmarks: 60 tests with `-m benchmark`.

```bash
# Automated memory suite (unit + smoke)
./scripts/test_memory.sh
./scripts/test_memory.sh --redis   # include live Redis enqueue when Redis is up

# Or pytest directly
PYTHONPATH=$(pwd) pytest -q \
  tests/test_phase1_memory_orchestration.py \
  tests/test_memory_retrieve_gate.py \
  tests/test_memory_orchestration_smoke.py \
  -m "not network"
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for workflow details.

## Quick Start

### One-time setup

```bash
git clone <repo-url> && cd OwlynnV2
./setup.sh    # containers, venv, pip, Docling models, .env
```

Set models in `.env` or the Settings UI (see [`docs/guides/dev-startup.md`](docs/guides/dev-startup.md)).

### Launch

```bash
./start.sh
```

Starts Podman containers (Qdrant + Redis), prompts for LM Studio on `:1234`, then backend (`:8000`) + Vite (`:5173`).

### Browser-only dev

```bash
# Terminal 1
source .venv/bin/activate && uvicorn src.api.server:app --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend-v2 && npx vite --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Safe Mode and Screen Assist **preview** need Electron IPC; **backend** screen assist tools work headless on macOS.

### Electron desktop build

```bash
cd frontend-v2 && npm run build
```

Output: `frontend-v2/dist/` (`.app` / `.dmg` on macOS).

## Tools

| Category | Tools |
|----------|-------|
| Web | `web_search`, `fetch_webpage`, `deep_research` |
| Files | `read_workspace_file`, `write_workspace_file`, `edit_workspace_file`, `list_workspace_files`, `delete_workspace_file` |
| Documents | `create_docx`, `create_xlsx`, `create_pptx`, `create_pdf` |
| Compute | `notebook_run`, `notebook_reset` |
| Memory | `recall_memories`, `recall_all_memories`, `forget_memory`, `search_workspace_docs` |
| Screen assist | `capture_local_terminal`, `read_screen_element`, `get_active_browser_context`, `capture_kali_terminal` |
| Tasks / skills | `todo_*`, `list_skills`, `invoke_skill` |
| HITL | `ask_user` |

Toolbox categories: `web_search`, `file_ops`, `data_viz`, `productivity`, `memory`, `screen_assist`, `all`. See [`docs/features/TOOLS.md`](docs/features/TOOLS.md).

## Memory System

| Tier | Storage | Role |
|------|---------|------|
| STM | `data/memories.json` | Keyword facts |
| LTM | Qdrant + Mem0 | Semantic recall (gated per turn) |
| L1 atoms | Qdrant via extractor | Structured facts (JSDoc / JSON) |
| L2/L3 | `scenarios/*/playbook.md` | Pentest / research workflows |
| Personal | topics, interests, conversations | Time-decay context |

**Inject path:** `memory_inject_lite` → router decides `needs_memory_retrieval` → `memory_retrieve`.

**Write path:** PII scrub → enqueue Redis stream `owlynn:memory:extract` → 8B worker → Qdrant.

Details: [`docs/features/MEMORY.md`](docs/features/MEMORY.md) · [`docs/guides/memory-orchestration-phase1.md`](docs/guides/memory-orchestration-phase1.md)

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health + agent ready |
| `GET`/`POST` | `/api/profile` | User profile |
| `GET`/`POST`/`DELETE` | `/api/memories` | Short-term JSON memories |
| `GET` | `/api/mem0/search` | Vector memory search |
| `GET`/`POST` | `/api/projects` | Project CRUD |
| `WS` | `/ws/chat/{thread_id}` | Streaming chat |

Full reference: [`docs/development/API_REFERENCE.md`](docs/development/API_REFERENCE.md) · WebSocket contract: [`docs/development/CHAT_PROTOCOL.md`](docs/development/CHAT_PROTOCOL.md)

## Documentation

**AI agents:** start at [`AGENTS.md`](AGENTS.md) → [`docs/development/PROJECT_GUIDE.md`](docs/development/PROJECT_GUIDE.md).

| Doc | Topic |
|-----|-------|
| [`AGENTS.md`](AGENTS.md) | Agent onboarding and task routing |
| [`docs/development/PROJECT_GUIDE.md`](docs/development/PROJECT_GUIDE.md) | File map by task |
| [`docs/architecture/overview.md`](docs/architecture/overview.md) | System overview |
| [`docs/architecture/AGENT_FLOW.md`](docs/architecture/AGENT_FLOW.md) | LangGraph nodes and edges |
| [`docs/guides/memory-vision-screen-roadmap.md`](docs/guides/memory-vision-screen-roadmap.md) | Memory + vision + screen assist |
| [`docs/architecture/VISION_PROXY.md`](docs/architecture/VISION_PROXY.md) | Cloud vision / OCR pipeline |
| [`docs/guides/screen-assist-phase3.md`](docs/guides/screen-assist-phase3.md) | Terminal / AX / Kali tools |
| [`docs/architecture/DEEPSEEK_V4_INTEGRATION.md`](docs/architecture/DEEPSEEK_V4_INTEGRATION.md) | Cloud routing and security |
| [`docs/architecture/CLOUD-LLM-ARCHITECTURE.md`](docs/architecture/CLOUD-LLM-ARCHITECTURE.md) | Cloud payload and anonymization |
| [`docs/features/WEB_SEARCH.md`](docs/features/WEB_SEARCH.md) | Search tier fallbacks |
| [`docs/STATUS.md`](docs/STATUS.md) | Project status and known issues |
| [`docs/INDEX.md`](docs/INDEX.md) | Full doc manifest |

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Local-first routing | Privacy + latency; cloud only on `complex-cloud` |
| Split memory inject | Sub-300ms router path; vector search gated after classification |
| Custom extraction (no mem0 infer) | Controlled atom schema + guaranteed PII scrub before LTM |
| Vision as OCR sensor | DeepSeek V4 is text-only; structured JSON not prose |
| Screen assist in Python | tmux/AX/browser need native macOS, not only Electron |
| LangGraph + Redis checkpoint | Stateful tool loops with resume across sessions |
| Local CI | `scripts/ci.sh` on pre-push instead of GitHub Actions quota |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Run `./scripts/ci.sh --quick` before pushing.

## License

[MIT](LICENSE)
