# Owlynn — Local AI Cowork Agent

A private, local-first AI productivity agent inspired by Anthropic's Cowork. Runs entirely on your machine with LangGraph orchestration, three-tier LLM routing, and a Tauri desktop frontend. Optimized for Apple Silicon (M4 Air 24GB).

## Overview

Owlynn is a desktop AI assistant that keeps your data local. It uses a stateful cyclic LangGraph to orchestrate conversations through a small routing model, a medium reasoning model, and an optional cloud fallback — all with a security proxy that gates sensitive tool calls behind human approval.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + LangGraph + Python 3.12+ |
| Frontend | React 19 + TypeScript (Vite 8) + Zustand 5, served via Tauri desktop shell |
| Small LLM | Gemma 4 E2B Heretic Uncensored (MLX, routing) |
| Medium LLM | LFM2 8B A1B Absolute Heresy MPOA (MLX, reasoning + tool calling) |
| Cloud LLM | DeepSeek API (optional escalation) |
| Memory | Mem0 + Qdrant + JSON files |
| Checkpointing | Redis (falls back to in-memory `MemorySaver`) |
| Search | Multi-tier: SearXNG (self-hosted) → Brave/Serper/Tavily → DuckDuckGo → Playwright |
| Testing | pytest + hypothesis (backend), vitest + @testing-library/react (frontend) |
| Desktop | Tauri v2.10 (Rust, macOS vibrancy) |

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

The router uses the small LLM to classify requests into simple (greetings, quick answers) or complex (reasoning, tool use). Complex requests are further routed to the appropriate model variant: default, vision, long-context, or cloud.

## Project Structure

```
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

src-tauri/            Tauri v2 desktop runtime
  ├── src/main.rs       Tauri command/event runtime
  ├── src/voice/mod.rs  TTS orchestration (macOS `say` command)
  └── tauri.conf.json   Tauri v2 configuration

skills/              Reusable prompt templates (markdown)
data/                User data (profile, memories, todos, topics)
tests/               pytest + hypothesis test suite
docs/                Architecture and API documentation
```

## Prerequisites

- **Python 3.12+** with pip/uv
- **LM Studio** with models loaded on port 1234
- **Docker/Podman** for Qdrant and SearXNG containers
- **Node.js 18+** for frontend tests
- **Rust & Cargo** for building the Tauri desktop app

## Quick Start

```bash
# 1. Clone and install Python dependencies
git clone <repo-url> && cd owlynn
pip install -r requirements.txt

# 2. Copy and configure environment variables
cp .env.example .env
# Edit .env with your settings (see Configuration below)

# 3. Start LM Studio with both models loaded (port 1234)
# - Small key: gemma-4-e2b-heretic-uncensored-mlx
# - Medium key: lfm2-8b-a1b-absolute-heresy-mpoa-mlx

# 4. Start services + backend + desktop app
./start.sh

# Run just the backend (without frontend):
# uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```
The app opens at `http://127.0.0.1:8000` or as a Tauri desktop window.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis for LangGraph checkpointing |
| `QDRANT_HOST` | `localhost` | Qdrant host for vector memory |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `SEARXNG_URL` | _(empty)_ | SearXNG URL (e.g. `http://localhost:8888`) |
| `DEEPSEEK_API_KEY` | _(empty)_ | Optional DeepSeek API key for cloud tier |
| `OPTIMIZE_FOR_M4` | `false` | Enable M4 Mac Air optimizations |

### LLM Setup

Models are configured in the user profile (`data/user_profile.json`) or via the Settings UI:

- **Small LLM**: `small_llm_model_name` — routing model (default: `liquid/lfm2.5-1.2b`)
- **Medium LLM**: `medium_models.default` — reasoning model (default: `qwen/qwen3.5-9b`)
- **Medium Vision**: `medium_models.vision` — for image inputs
- **Medium LongCtx**: `medium_models.longctx` — for large context windows
- **Cloud LLM**: `cloud_llm_model_name` — DeepSeek fallback (default: `deepseek-chat`)

Current verified local profile keys:
- **Small LLM**: `gemma-4-e2b-heretic-uncensored-mlx`
- **Medium LLM (default)**: `lfm2-8b-a1b-absolute-heresy-mpoa-mlx`

## API Overview

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

Full reference: [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

## Tools (20)

| Category | Tools |
|----------|-------|
| Web | web_search, fetch_webpage |
| Files | read, write, edit, list, delete workspace files |
| Documents | create_docx, create_xlsx, create_pptx, create_pdf |
| Compute | notebook_run, notebook_reset |
| Memory | recall_memories, recall_all_memories, forget_memory |
| Tasks | todo_add, todo_list, todo_complete |
| System prompts | list_skills, invoke_skill |
| HITL | ask_user (with choice buttons) |

## Skills (11)

Reusable prompt templates in `skills/`. Zero token cost until invoked.

| Skill | Triggers |
|-------|----------|
| Research Assistant | research, investigate |
| Document Summarizer | summarize, tldr |
| Morning Briefing | briefing, daily summary |
| Visual Comparison | compare, vs, chart |
| Data Visualization | graph, plot, histogram |
| Meeting Notes | meeting notes, action items |
| Email Drafter | draft email, compose |
| Report Generator | create report, weekly report |
| Presentation Builder | make slides, powerpoint |
| Content Rewriter | rewrite, polish, proofread |
| Brainstorm | brainstorm, ideas, what if |

## Memory System

Owlynn uses a three-tier memory architecture:

### 1. Short-Term Memory (JSON)
File-based fact storage in `data/memories.json`. Managed by `src/memory/memory_manager.py`. Simple keyword-overlap search, 200-entry cap. Used for quick recall of user facts during a session.

### 2. Long-Term Memory (Mem0 + Qdrant)
Vector-based semantic memory using Mem0 with a Qdrant backend (`cowork_memory_nomic` collection). Embeddings served by LM Studio (`nomic-embed-text-v1.5`, 768-dim). Managed by `src/memory/long_term.py`.

Key features:
- **Project isolation**: Memories are scoped by `project:<id>` for non-default projects. Conversations in different projects do not share long-term memory stores. The `default` project uses a global `owner` user ID, so all chats within `default` share the same memory pool.
- **Cross-session recall**: Within the same project (or within `default`), memories from past conversations are surfaced via semantic search — the LLM recalls facts and topics you discussed in previous chats.
- **Cross-project user knowledge**: In non-default projects, the assistant also pulls global user memories (profile name), so it retains general knowledge about you while keeping project-specific conversations isolated.
- **Selective memory gate**: Skips trivial/greeting exchanges to avoid memory pollution
- **Semantic dedup**: Avoids saving near-duplicate memories via similarity search before write
- **5-minute context cache**: Avoids rebuilding memory context on every request
- **WebSocket notification**: `memory_updated` event triggers UI refresh after memory write

### 3. Personal Assistant Memory
Managed by `src/memory/personal_assistant.py`:
- **Topic extraction**: Regex-based, 10 categories, stored in `data/topics.json`
- **Interest detection**: 8 types, stored in `data/interests.json`  
- **Conversation summaries**: Last 100 entries in `data/conversations.json`
- **Time-decay relevance scoring**: Topics/interests decay over time

### Memory Tools

| Tool | Description |
|------|-------------|
| `recall_memories` | Search short-term JSON memories (keyword overlap) |
| `recall_all_memories` | Deep semantic search of Mem0/Qdrant vector store |
| `forget_memory` | Delete specific memories by their ID hash |

### Memory API Endpoints

See [API Reference](docs/API_REFERENCE.md) for the full list, including `/api/mem0/search`, `/api/mem0/delete`, `/api/topics`, `/api/interests`, and `/api/memory-context`.

### Memory Node Flow (LangGraph)

The agent graph has two memory nodes:
1. **memory_inject_node** (pre-reasoning): Builds memory context from Mem0 + profile + topics + project instructions
2. **memory_write_node** (post-reasoning): Extracts topics/interests, saves enriched facts to Mem0, invalidates cache

## Testing

### Backend (pytest + hypothesis)

```bash
# Run all tests
pytest tests/ -v

# Run property-based tests only
pytest tests/test_crud_properties.py -v

# Run with hypothesis verbose output
pytest tests/ -v --hypothesis-show-statistics
```

### Frontend (vitest + @testing-library/react)

```bash
cd frontend-v2
npm install
npx vitest run
```

## Documentation

- [Architecture Overview](docs/ARCHITECTURE_OVERVIEW.md)
- [Agent Flow](docs/AGENT_FLOW.md)
- [Tools Reference](docs/TOOLS.md)
- [Chat Protocol](docs/CHAT_PROTOCOL.md)
- [API Reference](docs/API_REFERENCE.md)
- [Human Project Guide](docs/HUMAN_PROJECT_GUIDE.md)
- [AI Agent Project Guide](docs/AI_AGENT_PROJECT_GUIDE.md)
- [AI Agent Navigation Index](docs/AI_AGENT_INDEX.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, testing requirements, and PR process.

## License

_License TBD_
