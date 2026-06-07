---
last_verified: 2026-05-26
auto_generated: false
---

# Owlynn — Local AI Cowork Agent

[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://python.org)
[![Node](https://img.shields.io/badge/node-18+-green)](https://nodejs.org)
[![CI](https://img.shields.io/badge/CI-local_scripts%2Fci.sh-059669)](scripts/ci.sh)
[![Frontend](https://img.shields.io/badge/frontend-React_19_%2B_Vite_8-61DAFB)](frontend-v2/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A private, local-first AI productivity agent. Runs entirely on your machine with LangGraph orchestration, three-tier LLM routing, and an Electron desktop frontend. Optimized for Apple Silicon (M4 Air 24GB).

## Goal

Owlynn is a **desktop AI coworker** that keeps your data local. It reasons through complex tasks, calls tools (web search, file ops, document generation, notebook execution), remembers across sessions via semantic vector memory, and gates sensitive operations behind human approval — all without sending data to the cloud unless you explicitly opt in.

**Target user**: Developers and power users on Apple Silicon who want an AI assistant that respects privacy, runs locally, and can be extended with custom tools and skills.

## Overview

Owlynn is a desktop AI assistant that keeps data local. It uses a stateful cyclic LangGraph to orchestrate conversations through a small routing model, a medium reasoning model, and an optional cloud fallback — all with a security proxy that gates sensitive tool calls behind human approval.

## Entry Points

```text
src/api/server.py          # FastAPI entry point (REST + WebSocket)
src/agent/graph.py          # LangGraph graph builder, init_agent()
frontend-v2/electron/main.ts # Electron main process runtime
frontend-v2/src/App.tsx     # React app shell, WebSocket lifecycle
./start.sh                  # Full stack launcher
uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

## Architecture

```
User Message
    │
    ▼
memory_inject ──► (85% context?) ──► auto_summarize
    │                                      │
    ▼                                      ▼
  router ─────────────────────────────────►│
    │                                      │
    ├── simple ──► memory_write ──► END
    │
    └── complex_llm ──► (tool call?) ──► security_proxy
            ▲                                  │
            │                           (approved?) ──► tool_action
            │                                              │
            └──────────────────────────────────────────────┘
                                    (loop back)
```

The router uses the small LLM to classify requests into `simple` (greetings, quick answers) or `complex` (reasoning, tool use). Complex requests are further routed to the appropriate model variant: default, vision, long-context, or cloud.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | `FastAPI` + `LangGraph` + Python 3.12+ |
| Frontend | React 19 + TypeScript (Vite 8) + Zustand 5, Electron desktop |
| Small LLM | `minicpm5-1b` (MiniCPM5 1B, routing/classification) |
| Medium LLM | `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k` (local complex + vision) |
| Cloud LLM | `deepseek-v4-flash` / `deepseek-v4-pro` (DeepSeek API, optional `complex-cloud` route) |
| File Processing | Docling v2.96 (PDF/DOCX — layout-aware markdown, table structure detection) |
| Memory | Mem0 + Qdrant + JSON files |
| Checkpointing | Redis (falls back to in-memory `MemorySaver`) |
| Search | Multi-tier: wttr.in / SearXNG (self-hosted) → curl_cffi / DDGS → Playwright |
| Testing | `pytest` + `hypothesis` (backend), `vitest` + `@testing-library/react` (frontend) |
| Desktop | Electron (macOS, Node IPC bridges) |

## Project Progress

### Phase Completion

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Stabilization | Done | Browser multi-switch harness, WS+CRUD timing tests, frontend cutover |
| Phase 2: Reliability | Done | Route/fallback telemetry, WS contract tests, CI gate standardization |
| Phase 3: Capability | Done | Enhanced summarize/context compression, project knowledge panel |
| Phase 4: Governance | Done | ADR log (11 decisions), performance SLOs, release train alignment |
| Phase 5: Live Test | Done | Dead test removal, tool awareness assertions — 203 passed |
| Phase 6: MVP Hardening | Done | Env config, logging, dependency pinning, 89 new tests |
| Phase 7: Test Fixes | Done | 13 skipped tests fixed. **724 passed, 0 failed, 5 skipped** (Redis/integration) |
| **Phase 8: Bug Fixes** | **In Progress** | Fixing 8 bugs found in browser audit (see below) |

Test suite: **724 backend** (pytest + hypothesis), **77 frontend** (vitest + testing-library). All passing.

### Known Bugs (Phase 8)

| Severity | Bug | Location |
|----------|-----|----------|
| **CRITICAL** | Persona/system prompt leaks into first assistant response | `src/agent/nodes/simple.py` / `complex.py` |
| **HIGH** | Orchestration panel empty after message processing | `OrchestrationPanel.tsx` |
| **HIGH** | Memory panel shows "Loading..." indefinitely | `MemoryPanel.tsx` |
| MEDIUM | Chat auto-title defaults to "New Chat" | `src/api/server.py` |
| MEDIUM | Safe Mode depends on Tauri IPC, no browser fallback | `SafeModePanel.tsx` |
| LOW | Tool Execution panel shows permanent mock data | `ToolExecutionPanel.tsx` |
| LOW | Workspace delete shows wrong operator note | `App.tsx` |
| LOW | Audit & Verify sub-panel doesn't expand | `ToolExecutionPanel.tsx` |

Full status: [`docs/STATUS.md`](docs/STATUS.md) | Bug analysis: [`docs/BUG-ANALYSIS.md`](docs/BUG-ANALYSIS.md)

### Architectural Concerns

- **Electron IPC dependency**: SafeMode, ScreenAssist, and window sizing require Electron IPC — no browser fallbacks.
- **Silent error handling**: Multiple try/catch blocks swallow errors silently.
- **Loading states without timeouts**: Memory and Orchestration panels can hang indefinitely.

Performance and memory SLOs: [`docs/PERFORMANCE_SLOS.md`](docs/PERFORMANCE_SLOS.md)

## Project Structure

```text
src/agent/           LangGraph orchestration
  ├── graph.py         Graph builder and init_agent()
  ├── llm.py           LLMPool singleton (small + medium + cloud)
  ├── swap_manager.py  Hot-swap M-tier models via LM Studio API
  ├── state.py         AgentState TypedDict
  └── nodes/           Node implementations
      ├── router.py      5-way routing with HITL clarification
      ├── complex.py     Reasoning node with tool binding + fallback
      ├── simple.py      Fast answers via small LLM
      ├── memory.py      Memory inject/write nodes
      ├── security_proxy.py  HITL gate for sensitive tools
      └── summarize.py  Auto-summarize when context is near capacity

src/api/             FastAPI backend
  ├── server.py        REST endpoints + WebSocket streaming
  └── file_processor.py  Watchdog-based file watcher + format extraction

src/memory/          Memory system
  ├── memory_manager.py     JSON-based fact storage + keyword search
  ├── personal_assistant.py Topic/interest extraction with time decay
  ├── user_profile.py       User profile management
  ├── persona.py            Agent persona configuration
  ├── project.py            Project CRUD manager
  └── long_term.py          Mem0 + Qdrant integration

src/tools/           Tool implementations (20 tools)
  ├── core_tools.py         File ops + memory recall
  ├── web_tools.py          web_search + fetch_webpage
  ├── web_search_enhanced.py SearXNG integration
  ├── doc_generator.py      DOCX/XLSX/PPTX/PDF generation
  ├── notebook.py           Python REPL sandbox
  ├── todo.py               Task management
  ├── skills.py             Reusable prompt templates
  └── ask_user.py           HITL clarification tool

src/config/          Configuration
  └── settings.py      Global settings + M4 optimization config

frontend-v2/          React 19 + TypeScript frontend (active)
  ├── src/
  │   ├── components/    Composer, OrchestrationPanel, SafeModePanel,
  │   │                   ScreenAssistPanel, ToolExecutionPanel,
  │   │                   ActionProposalQueue,
  │   │                   ProjectKnowledgePanel, AppShell
  │   ├── state/         Zustand store (useAppStore)
  │   ├── types/         WebSocket protocol type definitions
  │   └── lib/           tauriBridge, wsClient
  └── package.json

frontend-v2/electron/    Electron Node.js runtime
  ├── main.ts           Electron main process + IPC handlers
  └── preload.ts        Context bridge exposition

skills/              Reusable prompt templates (markdown)
data/                User data (profile, memories, todos, topics)
tests/               pytest + hypothesis test suite
docs/                Architecture and API documentation
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis for LangGraph checkpointing |
| `QDRANT_HOST` | `localhost` | Qdrant host for vector memory |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `SEARXNG_URL` | _(empty)_ | SearXNG URL (e.g. `http://localhost:8888`) |
| `DEEPSEEK_API_KEY` | _(empty)_ | Optional DeepSeek API key — prefer `.env.local` (see `.env.local.example`) |
| `OPTIMIZE_FOR_M4` | `false` | Optional M4 Air timeouts/memory limits |

### LLM Setup

Models configured in `src/config/defaults.yaml`, overridden by `.env` / `.env.local` / Settings UI:

| Slot | Config path | Default | Description |
|------|------------|---------|-------------|
| Small LLM | `models.small.model_name` | `minicpm5-1b` | Router / classification |
| Medium LLM | `models.medium.model_name` | `qwen3.5-9b-...@q6_k` | Local complex + vision |
| Cloud LLM | `models.cloud.model_name` | `deepseek-v4-flash` | DeepSeek V4 (`complex-cloud`) |

Routes: `simple`, `complex-default`, `complex-cloud` only.

All local models served via LM Studio on port 1234.

## Prerequisites

- Python 3.12+ with `pip`/`uv`
- LM Studio with models loaded on port 1234
- Docker/Podman for Qdrant and SearXNG containers
- Node.js 18+ for frontend tests and Electron build

## Testing

Local CI via `scripts/ci.sh` (runs pre-push). See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full development workflow.

```bash
./scripts/ci.sh              # Full suite (Python + frontend tests + build)
./scripts/ci.sh --quick      # Skip frontend build
./scripts/ci.sh --python-only
```

### Backend (`pytest` + `hypothesis`)

```bash
pytest tests/ -v
pytest tests/test_crud_properties.py -v
pytest tests/ -v --hypothesis-show-statistics
```

### Frontend (`vitest` + `@testing-library/react`)

```bash
cd frontend-v2
npx vitest run
```

## Quick Start

### One-time setup

```bash
git clone <repo-url> && cd owlynn
./setup.sh              # containers, venv, pip install, Docling models, .env
```

Edit `.env` and set your LM Studio model name:
```
MEDIUM_LLM_MODEL_NAME=gemma-4-e4b-uncensored-hauhaucs-aggressive
```

### Launch

```bash
./start.sh
```

Launches 3 stages:
1. **Podman containers** — Qdrant (port 6333) + Redis (port 6379)
2. **LM Studio** — prompts you to start the server on port 1234
3. **Backend + Frontend** — uvicorn (port 8000) + Vite dev server

## Electron Desktop App

The application is primarily distributed as an Electron `.app` for macOS.

To build the desktop application locally:

```bash
cd frontend-v2 && npm run build
```

This will output the packaged `.app` and `.dmg` inside `frontend-v2/dist/`.

Press `Ctrl+C` to stop all services.

### Browser-Only (Backend + Frontend HMR)

```bash
# Terminal 1 — backend
source .venv/bin/activate && uvicorn src.api.server:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (hot reload)
cd frontend-v2 && npx vite --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Safe Mode and Screen Assist require Electron IPC — unavailable in browser mode.

### CLI / Headless (Backend Only)

```bash
source .venv/bin/activate
uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

Backend at `http://127.0.0.1:8000`. Use REST API or WebSocket (`ws://127.0.0.1:8000/ws/chat/{thread_id}`). Full API reference in [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).

| Mode | Backend | Frontend | Electron | Best For |
|------|---------|----------|----------|----------|
| `./start.sh` | Yes | Vite HMR | No | Daily browser use |
| Browser (manual) | Yes | Vite HMR | No | Dev, hot reload |
| CLI | Yes | No | No | Scripting, API testing |

## API

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check (agent ready status) |
| `GET` | `/api/profile` | Get user profile |
| `POST` | `/api/profile` | Update user profile |
| `GET` | `/api/memories` | List stored short-term (JSON) memories |
| `POST` | `/api/memories` | Save a fact to short-term memory |
| `DELETE` | `/api/memories` | Delete from short-term memory |
| `GET` | `/api/mem0/search` | Search Mem0/Qdrant vector long-term memory |
| `GET` | `/api/mem0/count` | Count memories in Mem0 |
| `POST` | `/api/mem0/delete` | Delete a memory by ID from Mem0 |
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create a project |
| `GET` | `/api/topics` | Get tracked topics with relevance |
| `GET` | `/api/files` | List workspace files |
| `GET` | `/api/tools` | List available tools |
| `WS` | `/ws/chat/{thread_id}` | WebSocket for streaming chat |

Full reference: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

## Tools (22)

| Category | Tools |
|----------|-------|
| Web | `web_search`, `fetch_webpage` |
| Files | `read`, `write`, `edit`, `list`, `delete` workspace files |
| Documents | `create_docx`, `create_xlsx`, `create_pptx`, `create_pdf` |
| Compute | `notebook_run`, `notebook_reset` |
| Memory | `recall_memories`, `recall_all_memories`, `forget_memory` |
| Tasks | `todo_add`, `todo_list`, `todo_complete` |
| System prompts | `list_skills`, `invoke_skill` |
| HITL | `ask_user` (with choice buttons) |

## Skills (18)

Reusable prompt templates in `skills/`. Zero token cost until invoked.

| Skill | Triggers |
|-------|----------|
| Research Assistant | research, investigate |
| Document Summarizer | summarize, tldr |
| Morning Briefing | briefing, daily summary |
| Visual Comparison | compare, vs, chart |
| Data Visualization | graph, plot, histogram |
| Data Analyzer | analyze data, statistics, insights, trends |
| Meeting Notes | meeting notes, action items |
| Email Drafter | draft email, compose |
| Report Generator | create report, weekly report |
| Presentation Builder | make slides, powerpoint |
| Content Rewriter | rewrite, polish, proofread |
| Brainstorm | brainstorm, ideas, what if |
| Code Reviewer | review code, code review, review |
| Fact Checker | fact check, verify, check facts |
| Information Scanner | scan, find, search for information |
| Explainer | explain, how does, what is |
| Todo Planner | plan tasks, organize, schedule |
| Weekly Review | weekly review, week summary, recap |

## Memory System

Three-tier memory architecture:

### Short-Term Memory (JSON)

- File-based fact storage in `data/memories.json`
- Managed by `src/memory/memory_manager.py`
- Simple keyword-overlap search, 200-entry cap
- Used for quick recall of user facts during a session

### Long-Term Memory (Mem0 + Qdrant)

- Vector-based semantic memory with Mem0 + Qdrant backend (`cowork_memory_nomic` collection)
- Embeddings: LM Studio (`nomic-embed-text-v1.5`, 768-dim)
- Managed by `src/memory/long_term.py`

| Feature | Description |
|---------|-------------|
| Project isolation | Memories scoped by `project:<id>`. `default` project uses global `owner` user ID |
| Cross-session recall | Semantic search surfaces memories from past conversations within same project |
| Cross-project knowledge | Non-default projects pull global user memories (profile name) |
| Selective memory gate | Skips trivial/greeting exchanges |
| Semantic dedup | Similarity search before write avoids near-duplicates |
| Context cache | 5-minute `MemoryContextCache` per thread |
| WebSocket notification | `memory_updated` event triggers UI refresh |

### Personal Assistant Memory

Managed by `src/memory/personal_assistant.py`:

- Topic extraction: regex-based, 10 categories, stored in `data/topics.json`
- Interest detection: 8 types, stored in `data/interests.json`
- Conversation summaries: last 100 entries in `data/conversations.json`
- Time-decay relevance scoring

### Memory Tools

| Tool | Description |
|------|-------------|
| `recall_memories` | Search short-term JSON memories (keyword overlap) |
| `recall_all_memories` | Deep semantic search of Mem0/Qdrant vector store |
| `forget_memory` | Delete specific memories by their ID hash |

### Memory Node Flow (LangGraph)

1. `memory_inject_node` (pre-reasoning): Builds memory context from Mem0 + profile + topics + project instructions
2. `memory_write_node` (post-reasoning): Extracts topics/interests, saves enriched facts to Mem0, invalidates cache

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Three-tier LLM routing | Local-first with cloud fallback | Added swap latency for M-tier model changes |
| LangGraph orchestration | Stateful cyclic graph with checkpointing | More complex than linear pipelines |
| Tauri desktop shell | Native macOS integration, small binary | macOS-only features, Tauri IPC dependency |
| Mem0 + Qdrant memory | Semantic vector search | Requires Docker container for Qdrant |
| Security proxy HITL | Gated destructive operations | Adds latency for approved sensitive tool calls |

## Documentation

- [`docs/ARCHITECTURE_OVERVIEW.md`](docs/ARCHITECTURE_OVERVIEW.md)
- [`docs/AGENT_FLOW.md`](docs/AGENT_FLOW.md)
- [`docs/TOOLS.md`](docs/TOOLS.md)
- [`docs/CHAT_PROTOCOL.md`](docs/CHAT_PROTOCOL.md)
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)
- [`docs/STATUS.md`](docs/STATUS.md) — project status, known bugs, next steps
- [`docs/ADR.md`](docs/ADR.md) — architecture decision records
- [`docs/PERFORMANCE_SLOS.md`](docs/PERFORMANCE_SLOS.md) — latency, memory, CPU targets
- [`docs/BUG-ANALYSIS.md`](docs/BUG-ANALYSIS.md) — bug inventory and audit reports
- [`docs/HUMAN_PROJECT_GUIDE.md`](docs/HUMAN_PROJECT_GUIDE.md) — human workflow guide
- [`docs/AI_AGENT_PROJECT_GUIDE.md`](docs/AI_AGENT_PROJECT_GUIDE.md) — AI agent execution guide
- [`docs/AI_AGENT_INDEX.md`](docs/AI_AGENT_INDEX.md) — file-level navigation for AI agents

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup, code style, and testing guidelines. PRs welcome — please scope changes per the `docs/AI_AGENT_INDEX.md` concern areas and ensure all tests pass before submitting.

## License

[MIT](LICENSE)
