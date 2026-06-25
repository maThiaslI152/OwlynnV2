# Architecture Overview — OwlynnV2

> **System context, modules, data flow, and key entrypoints.**
> Last updated: 2026-06-10

## System Context

Owlynn is a **privacy-first hybrid** coworker for Apple Silicon (Mac M4 Air 24GB). **Local:** workspace files, Qdrant/Redis memory, routing, embeddings, and unified model routing, embedding, and memory extraction stay on-device. **Cloud (opt-in):** complex reasoning uses **DeepSeek V4** when a key is configured; prompts are **best-effort anonymized** before send (see `src/agent/anonymization.py`). Startup preloads **Gemma-4-E2B unified model + nomic embedding**.

```
Browser (http://127.0.0.1:5173)
  │
  ├─► Vite Dev Server (port 5173)
  │     └─► React 19 + Zustand + WebSocket client
  │
  ├─► FastAPI Backend (port 8000)
  │     ├─► LangGraph Agent (router → simple/complex nodes)
  │     ├─► WebSocket handler (streaming responses)
  │     └─► Tool execution (web search, file ops, REPL, MCP)
  │
  ├─► LM Studio (port 1234)
  │     ├─► Gemma-4-E2B unified local model (startup preload)
  │     └─► nomic embedding (startup preload)
  │
  ├─► Qdrant (port 6333)
  │     └─► Long-term memory (Mem0 embeddings)
  │
  └─► Redis (port 6379)
        └─► LangGraph checkpointing / session persistence
```

## Key Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| **Config** | `src/config/defaults.yaml` | Single source of truth for all settings. Override chain: YAML → env → profile |
| **Config Loader** | `src/config/config_loader.py` | Layered config with typed accessors, env var mapping, validation |
| **Agent Graph** | `src/agent/graph.py` | LangGraph orchestration: memory→router→simple/complex→tools→memory |
| **Router** | `src/agent/routing/router.py` | Cloud-primary routing: `simple`, `complex-cloud` — keyword bypass, LLM classifier, HITL |
| **Simple Node** | `src/agent/core/simple.py` | Fast answers via local unified model (Gemma-4-E2B), retry-once on failure |
| **Complex Node** | `src/agent/core/complex.py` | Tool-augmented reasoning — Cloud DeepSeek V4 |
| **Cloud payload** | `src/agent/nodes/complex_utils/cloud_payload.py` | Anonymization, brief gate, stable/volatile prompt layers, cache metrics |
| **Cloud invoke** | `src/agent/nodes/complex_utils/cloud_invoke.py` | Raw DeepSeek client, tool strict mode, reasoning replay |
| **Vision proxy** | `src/agent/nodes/complex_utils/vision_*.py` | Lazy VLM → JSON OCR → text for DeepSeek cloud path |
| **Screen assist** | `src/tools/screen_assist/` | tmux, macOS AX, browser, Kali SSH tools |
| **Memory** | `src/agent/nodes/memory.py` | Memory injection + write: STM, LTM (Mem0/Qdrant), personal context |
| **Summarizer** | `src/agent/nodes/summarize.py` | Auto-compress older turns when context >85% of window |
| **HITL** | `src/agent/hitl/` | Safety gates: scope_clarify, plan_review, security_proxy |
| **LLM Pool** | `src/agent/llm.py` | Singleton pool: router + extraction + cloud instances |
| **Tools** | `src/tools/` | Web search, file ops, notebook, skills, MCP |
| **API** | `src/api/server.py` | FastAPI with REST + WebSocket + OpenAI-compatible endpoints |
| **Frontend** | `frontend-v2/` | React 19 + Vite + Zustand + Electron main process |

## Agent Flow

```
User Message
  │
  ▼
memory_inject_lite ──► Profile, persona, topics (no vector search)
  │
  ▼
router ──► Classify: simple | complex-cloud; memory gate + scenario
  │
  ▼
memory_retrieve ──► Gated Qdrant/Mem0 + scenario markdown (when needed)
  │
  ▼
after_memory_retrieve ──► If tokens >85% context: auto_summarize → compress history
  │
  ▼
simple | scope_clarify → complex_llm
  │
  ├── simple ──► simple_node (Gemma-4-E2B, fast)
  │
  └── complex ──► scope_clarify ──► complex_llm
                        │              │
                        │    cloud (complex-cloud)
                        │              │
                        │    plan_review / security_proxy (HITL)
                        │              │
                        │    tool_action ──► web search, file ops, REPL
                        │              │
                        │    complex_llm ──► cycle until no tools pending
                        │
                        ▼
                   memory_write ──► PII scrub → extraction queue → invalidate caches
```

## Configuration Architecture

Single source of truth in `src/config/defaults.yaml` (19 top-level sections, ~150 settings).

**Override priority (lowest → highest):**
```
defaults.yaml  →  environment variables  →  user_profile.json
```

**Key sections:**
- `models` — small/cloud/extraction/standard: names, base_urls, temps, budgets, pricing
- `cloud` — thinking mode, reasoning effort, vision cache TTL
- `routing` — confidence thresholds, budget tiers, keyword bypasses
- `memory` — max facts, cache TTL, decay constants
- `web_search` — backend timeouts, user-agents, aggregate cap
- `summarization` — threshold ratio, keep_recent_turns
- `complex` — safety margins, cutoff retries, token budgets

Validation runs at startup via `ConfigValidator` — 60+ required paths checked.

## Memory Architecture

Three-tier system:
- **STM** (`data/memories.json`) — recent facts, keyword search
- **LTM** (`Mem0 + Qdrant`) — embedding-indexed semantic search
- **Personal** (`topics.json`, `interests.json`) — time-decay-weighted relevance

Context budget: memory capped at 6000 chars (~1500 tokens) to stay within model context window.

## Related

- `docs/HITL.md` — Safety gates documentation
- `docs/MEMORY.md` — Memory system documentation
- `docs/CLOUD-LLM-ARCHITECTURE.md` — Cloud connection, caches, cost tracking
- `docs/architecture/DEEPSEEK_V4_INTEGRATION.md` — DeepSeek V4 API + optimization reference
- `docs/guides/dev-startup.md` — Dev setup and config reference
- `src/config/defaults.yaml` — Centralized configuration
- `docs/standards/coding-style.md` — Code conventions
