# Owlynn — Local AI Cowork Agent

[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![Node](https://img.shields.io/badge/node-20+-green)](https://nodejs.org)
[![CI](https://img.shields.io/badge/CI-local_scripts%2Fci.sh-059669)](scripts/ci.sh)
[![Frontend](https://img.shields.io/badge/frontend-React_19_%2B_Vite_8-61DAFB)](frontend-v2/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A private, local-first AI productivity agent. **Default is fully local** (`cloud_routing_mode=local_only`); DeepSeek cloud is opt-in. Built on LangGraph with a unified Gemma 4 12B local engine, semantic memory, multi-tier web search, and an Electron desktop UI. Optimized for Apple Silicon (M4 Air 24 GB).

---

## What It Does

Owlynn is a **desktop AI coworker** that keeps your data local. It reasons through complex tasks, calls tools (web search, file ops, document generation, notebook execution, screen/terminal context), remembers across sessions via vector memory, and gates sensitive operations behind human approval — cloud escalation is opt-in.

**Target user**: Developers and power users on Apple Silicon who want a privacy-respecting assistant with pentest/research workflows, optional cloud reasoning, and extensible tools/skills.

---

## Highlights

| Capability | Summary |
|------------|---------|
| **Semantic Cache** | Repeated questions answered in **< 100ms** — full LangGraph pipeline bypassed via Redis vector similarity |
| **Routing** | Deterministic + local-first → `simple` \| `complex-default` (12B) \| optional `complex-cloud` (DeepSeek) |
| **Latency** | Simple/trivia: one 12B generate, no tool schemas, coherence skipped; web: tool-first search then short synthesis |
| **Memory orchestration** | Split inject (`memory_inject_lite` → router → gated `memory_retrieve`), async extraction, PII scrub |
| **Vision proxy** | On-demand Baidu OCR → text path; not preloaded by default |
| **Screen assist** | macOS tmux capture, Accessibility API, browser tab, Kali SSH tmux (Python tools) |
| **HITL** | Security proxy + plan review for sensitive tool calls; `require_approval` default; destructive command blocking |
| **Search** | Browser extension (tier 0.2) → curl_cffi → DDGS → Playwright; SearXNG opt-in |
| **Pentest mode** | Hidden by default (`features.pentest_enabled=false`); Kali via Lima when enabled — never cloud |
| **Study mode** | 16 study tools, SM-2 flashcard review, quiz sessions, exam countdown |

Full roadmap: [`docs/guides/memory-vision-screen-roadmap.md`](docs/guides/memory-vision-screen-roadmap.md)

---

## Architecture

### Full Request Lifecycle (with Semantic Cache)

```
WebSocket intake
      │
      ▼
Semantic Cache check (redisvl, 0.92 cosine similarity threshold)
      │
      ├─ CACHE HIT  → stream reply instantly → idle             < 100ms, no LLM cost
      │
      └─ CACHE MISS ─────────────────────────────────────────────────────────────┐
                                                                                  ▼
memory_inject_lite ──► profile, persona, topics (no vector search)
      │
      ▼
router ──► simple | complex-default | complex-cloud (opt-in); memory gate + scenario id
      │
      ▼
memory_retrieve ──► gated vector memory + scenario markdown; sets active_tokens
      │
      ▼
auto_summarize? ──► if active_tokens > 85% context window
      │
      ├── simple ──► coherence (skipped) ──────────────────────► memory_write ──► END
      │                                                                │
      └── scope_clarify ──► complex_llm ◄──────────────────┐         └──► store_semantic_cache()
                │              │                             │
                │    tool-first web_search (no bind_tools)   │
                │    or bind_tools planning                  │
                │              │                             │
                │    plan_review / security_proxy (HITL)     │
                │              ▼                             │
                │         tool_action ───────────────────────┘
                │
                ▼
           coherence_check (skipped on short/web success) → memory_write → END
```

### Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + LangGraph + Python 3.11+ |
| Frontend | React 19 + TypeScript (Vite 8) + Zustand 5, Electron desktop |
| Local LLM | `gemma-4-e2b-heretic-uncensored-mlx` (routing, vision proxy, background memory extraction) |
| Cloud LLM | `deepseek-v4-flash` / `deepseek-v4-pro` (primary complex reasoning) |
| Pentest LLM | `gemma-4-12b-coder-fable5-composer2.5-v1@q4_k_m` (local-only, security-focused) |
| Semantic Cache | Redis + `redisvl` (`SemanticCache` with nomic-embed vectorizer) |
| File processing | Docling v2 (PDF/DOCX → markdown), StirlingPDF (Docker, OCR), PyMuPDF |
| Memory | Mem0 + Qdrant + JSON STM; Redis extraction worker |
| Checkpointing | Redis `AsyncRedisSaver` + daily eviction of stale threads (falls back to in-memory) |
| Search | Multi-tier: browser extension → curl_cffi / DDGS → Playwright; SearXNG opt-in |
| Package manager | `uv` (Python), npm (Node) |
| Testing | pytest + hypothesis (backend), vitest (frontend) |
| CI | Local [`scripts/ci.sh`](scripts/ci.sh) (pre-push hook) |

---

## Project Structure

```text
src/
  agent/
    core/           graph.py, llm.py, state.py, tool_sets.py
    routing/        router.py, router_utils.py
    nodes/          simple.py, complex.py, memory.py, summarize.py, coherence.py
                    complex_utils/ (vision_proxy, formatter, cloud_payload …)
                    security_proxy.py, scope_clarify.py, plan_review.py
    hitl/           policy.py, context.py, scope_heuristics.py

  memory/
    long_term.py          # LTM (Mem0 + Qdrant)
    memory_manager.py     # STM (JSON)
    semantic_cache.py     # ← NEW: redisvl semantic response cache
    personal_assistant.py
    extraction/           # async atom extractor (Redis stream → Qdrant)
    scenarios.py          # pentest + research L2/L3 markdown loader
    compression.py        # cloud brief memory block

  tools/
    core_tools.py, web_tools.py, doc_generator.py, notebook.py, skills.py
    study_tools.py        # 16 study tools (flashcards, quiz, SM-2, export)
    screen_assist/        # tmux, AX, browser, Kali SSH tools

  api/
    server.py             # FastAPI app
    ws/handler.py         # WebSocket handler (semantic cache integrated)
    routes/               # REST endpoints (study, pentest, browser_extension …)

scenarios/
  pentest/, research/     # playbook + constraints markdown

lima/kali.yaml            # Lima VM for Kali Linux (pentest mode)
frontend-v2/              # React + Electron UI
tests/                    # pytest + benchmarks
docs/                     # architecture, guides, API reference
```

---

## Entry Points

```text
src/api/server.py              # FastAPI (REST + WebSocket + OpenAI-compatible API)
src/agent/core/graph.py        # LangGraph builder, init_agent()
frontend-v2/electron/main.ts   # Electron main process
frontend-v2/src/App.tsx        # React shell + WebSocket lifecycle
./start.sh                     # Full stack launcher
```

---

## Configuration

Settings live in `src/config/defaults.yaml` (override chain: YAML → env → `user_profile.json`).

### Environment Variables

| Variable | Description |
|----------|-------------|
| `REDIS_URL` | LangGraph checkpointing + memory extraction stream + semantic cache |
| `QDRANT_HOST` / `QDRANT_PORT` | Vector memory |
| `SEARXNG_URL` | Optional self-hosted search |
| `DEEPSEEK_API_KEY` | Optional cloud route (`complex-cloud`) |
| `KALI_SSH_HOST` | Remote Kali VM for `capture_kali_terminal` |
| `SCREEN_ASSIST_TMUX_SESSION` | Default local tmux session name |
| `OPTIMIZE_FOR_M4` | M4 Air timeouts and memory limits |

### LLM Setup

| Slot | Default model | Role |
|------|---------------|------|
| Small | `gemma-4-e2b-heretic-uncensored-mlx` | Local unified model (routing, vision proxy, memory extraction) |
| Cloud | `deepseek-v4-flash` | DeepSeek V4 (`complex-cloud`) |
| Pentest | `gemma-4-12b-coder-fable5-composer2.5-v1@q4_k_m` | Local-only security model |
| Embedding | `nomic-embed-text-v1.5` | Memory + RAG + semantic cache vectorizer |

Local models via LM Studio on port `1234`.

---

## Performance

| Scenario | Latency |
|----------|---------|
| **Semantic cache hit** | **< 100ms** TTFT — graph never runs |
| Simple query (local) | < 2s TTFT |
| Complex query (cloud DeepSeek V4) | < 15s TTFT |
| Tool execution (single call) | < 5s |

**Memory budget (sustained, all services running):** ~8.3 GB unified memory on M4 Air.

Full SLOs: [`docs/PERFORMANCE_SLOS.md`](docs/PERFORMANCE_SLOS.md)

---

## Mode System

Owlynn has three modes that change the UI, tools, and system prompt:

| Mode | LLM | Use case |
|------|-----|----------|
| **Normal** | Router decides (local / cloud) | General tasks, coding, writing |
| **Study** | Router decides | Courses, flashcards, quizzes, exam prep |
| **Pentest** | Local model only (Gemma 4 12B Coder) | Security assessments via Kali Lima VM |

Pentest mode **never** uses cloud APIs — enforced at the router level.

---

## Memory System

| Tier | Storage | Role |
|------|---------|------|
| **Semantic Cache** | Redis (`redisvl`) | Cached AI answers — instant replay for similar questions |
| STM | `data/memories.json` | Keyword facts from recent conversations |
| LTM | Qdrant + Mem0 | Semantic recall (gated per turn) |
| L1 atoms | Qdrant via extractor | Structured facts (JSON schema) |
| L2/L3 | `scenarios/*/playbook.md` | Pentest / research workflows |
| Personal | topics, interests, conversations | Time-decay context |

**Inject path:** `memory_inject_lite` → router decides `needs_memory_retrieval` → `memory_retrieve`.

**Write path:** PII scrub + injection neutralization → enqueue Redis stream → 8B worker → Qdrant → `store_semantic_cache()`.

Details: [`docs/features/MEMORY.md`](docs/features/MEMORY.md) · [`docs/features/SEMANTIC_CACHE.md`](docs/features/SEMANTIC_CACHE.md)

---

## Tools

| Category | Tools |
|----------|-------|
| Web | `web_search`, `fetch_webpage`, `deep_research` |
| Files | `read_workspace_file`, `write_workspace_file`, `edit_workspace_file`, `list_workspace_files`, `delete_workspace_file` |
| Documents | `create_docx`, `create_xlsx`, `create_pptx`, `create_pdf` |
| Compute | `notebook_run`, `notebook_reset` |
| Memory | `recall_memories`, `recall_all_memories`, `forget_memory`, `search_workspace_docs` |
| Screen assist | `capture_local_terminal`, `read_screen_element`, `get_active_browser_context`, `capture_kali_terminal` |
| Study | `course_register`, `flashcard_deck_create`, `flashcard_review`, `quiz_session_start`, `export_study_sheet`, + 11 more |
| Tasks / skills | `todo_*`, `list_skills`, `invoke_skill` |
| HITL | `ask_user` |

Full reference: [`docs/features/TOOLS.md`](docs/features/TOOLS.md)

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health + agent ready |
| `GET`/`POST` | `/api/profile` | User profile |
| `GET`/`POST`/`DELETE` | `/api/memories` | Short-term JSON memories |
| `GET` | `/api/mem0/search` | Vector memory search |
| `GET`/`POST` | `/api/projects` | Project CRUD |
| `GET` | `/api/study/dashboard` | Study dashboard |
| `GET` | `/api/pentest/status` | Kali VM status |
| `WS` | `/ws/chat/{thread_id}` | Streaming chat |

Full reference: [`docs/development/API_REFERENCE.md`](docs/development/API_REFERENCE.md) · WebSocket contract: [`docs/development/CHAT_PROTOCOL.md`](docs/development/CHAT_PROTOCOL.md)

---

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

Starts Podman containers (Qdrant + Redis + StirlingPDF), prompts for LM Studio on `:1234`, then backend (`:8000`) + Vite (`:5173`).

### Browser-only dev

```bash
# Terminal 1 — backend
source .venv/bin/activate && uvicorn src.api.server:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend
cd frontend-v2 && npx vite --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Safe Mode and Screen Assist **preview** need Electron IPC; backend screen assist tools work headless on macOS.

### Electron desktop build

Release steps (version bump, Gatekeeper, Podman/LM Studio): [`docs/guides/app-release.md`](docs/guides/app-release.md).

```bash
cd frontend-v2
rm -rf dist dist-electron
npm run build
```

Output: `frontend-v2/dist/Owlynn-0.3.1-arm64.dmg` (and `.app` / zip).

---

## Testing

```bash
./scripts/ci.sh              # Full suite (Python + frontend + build)
./scripts/ci.sh --quick      # Skip frontend production build
./scripts/ci.sh --python-only
./scripts/ci.sh --benchmarks # Optional latency benchmarks
```

**Current suite (local CI):** ~884 backend tests (pytest), 130 frontend tests (vitest).

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for workflow details.

---

## Documentation

**AI agents:** start at [`AGENTS.md`](AGENTS.md) → [`docs/development/PROJECT_GUIDE.md`](docs/development/PROJECT_GUIDE.md).

| Doc | Topic |
|-----|-------|
| [`AGENTS.md`](AGENTS.md) | Agent onboarding and task routing |
| [`docs/development/PROJECT_GUIDE.md`](docs/development/PROJECT_GUIDE.md) | File map by task |
| [`docs/architecture/overview.md`](docs/architecture/overview.md) | System overview |
| [`docs/architecture/AGENT_FLOW.md`](docs/architecture/AGENT_FLOW.md) | LangGraph nodes, edges, and semantic cache bypass |
| [`docs/architecture/REDIS_LIFECYCLE.md`](docs/architecture/REDIS_LIFECYCLE.md) | Redis checkpoint eviction and memory management |
| [`docs/features/SEMANTIC_CACHE.md`](docs/features/SEMANTIC_CACHE.md) | Semantic response cache (< 100ms hits) |
| [`docs/features/MEMORY.md`](docs/features/MEMORY.md) | Full memory system (STM, LTM, personal, semantic cache) |
| [`docs/features/STUDY.md`](docs/features/STUDY.md) | Study mode tools and course system |
| [`docs/features/PENTEST.md`](docs/features/PENTEST.md) | Pentest mode and Kali Lima VM |
| [`docs/architecture/VISION_PROXY.md`](docs/architecture/VISION_PROXY.md) | Cloud vision / OCR pipeline |
| [`docs/architecture/DEEPSEEK_V4_INTEGRATION.md`](docs/architecture/DEEPSEEK_V4_INTEGRATION.md) | Cloud routing and security |
| [`docs/architecture/CLOUD-LLM-ARCHITECTURE.md`](docs/architecture/CLOUD-LLM-ARCHITECTURE.md) | Cloud payload and anonymization |
| [`docs/features/WEB_SEARCH.md`](docs/features/WEB_SEARCH.md) | Search tier fallbacks |
| [`docs/PERFORMANCE_SLOS.md`](docs/PERFORMANCE_SLOS.md) | Latency and memory SLOs |
| [`docs/STATUS.md`](docs/STATUS.md) | Project status and known issues |
| [`docs/INDEX.md`](docs/INDEX.md) | Full doc manifest |

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| **Semantic cache before graph** | Skip LLM cost entirely for repeated questions; < 100ms instead of 3-15s |
| **Redis checkpoint eviction** | Daily scan + 30-day idle threshold prevents unbounded Redis OOM |
| Local-first routing | Privacy + latency; cloud only on `complex-cloud` |
| Split memory inject | Sub-300ms router path; vector search gated after classification |
| Custom extraction (no mem0 infer) | Controlled atom schema + guaranteed PII scrub before LTM |
| Vision as OCR sensor | DeepSeek V4 is text-only; structured JSON not prose |
| Screen assist in Python | tmux/AX/browser need native macOS, not only Electron |
| LangGraph + Redis checkpoint | Stateful tool loops with resume across sessions |
| Local CI | `scripts/ci.sh` on pre-push instead of GitHub Actions quota |
| Pentest local-only enforcement | Cloud APIs reject security content; hard-coded at router |

---

## Recent Updates

- **2026-07-07**: **Security Hardening** — `/v1/chat/completions` auth enforced; execution policy default changed to `require_approval`; notebook sandbox hardened (HTTP clients removed); SSRF protection on `download_to_workspace`; prompt injection boundaries on web fetches and memory writes; destructive command blocking in scope guard. See [`docs/HITL.md`](docs/HITL.md).
- **2026-07-07**: **Semantic Cache** — repeated questions answered in < 100ms via Redis vector similarity (`redisvl`). **Redis checkpoint eviction** — daily background task evicts threads idle > 30 days. Full documentation in [`docs/features/SEMANTIC_CACHE.md`](docs/features/SEMANTIC_CACHE.md) and [`docs/architecture/REDIS_LIFECYCLE.md`](docs/architecture/REDIS_LIFECYCLE.md).
- **2026-07-07**: Complete UI/UX overhaul — glassmorphic Composer, pulsating Thinking indicator, modern tool activity cards, unified `lucide-react` icon system.
- **2026-07-06**: Dependency audit and safe update pass. Cleaned up stale configuration, unused memory vectors, deprecated web tools.

---

## License

[MIT](LICENSE)
