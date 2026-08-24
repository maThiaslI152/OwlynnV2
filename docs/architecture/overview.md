---
status: active
category: architecture
last_updated: 2026-08-24
owner: ai-agent
audience: agent
---

# Architecture Overview — OwlynnV2

> **System context, modules, data flow, and key entrypoints.**

## System Context

Owlynn is a **privacy-first hybrid** coworker for Apple Silicon (Mac M4 Air 24GB). **Local:** workspace files, PostgreSQL/pgvector and Redis memory, routing, embeddings, and unified model routing, embedding, and memory extraction stay on-device. **Cloud (opt-in):** complex reasoning uses **DeepSeek V4** when a key is configured; prompts are **best-effort anonymized** before send (see `src/agent/anonymization.py`). Startup preloads **Gemma 4 12B Agentic (`gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m`) unified local model + MXBAI embedding (`text-embedding-mxbai-embed-large-v1`)**.

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
  ├─► Local LLM Provider (LM Studio: 1234 / Ollama: 11434)
  │     ├─► Main Local Model: gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m (Unified Local Engine: Routing, Simple, Extraction, Fallback, Pentest)
  │     ├─► Vision Model: baidu.unlimited-ocr (Vision Transcription Proxy)
  │     ├─► Embedding Model: text-embedding-mxbai-embed-large-v1 (1024 dims)
  │     └─► Pentest Model: gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m (90% Tool Accuracy, Zero-Latency Mode Switching)
  │
  ├─► PostgreSQL (port 5432)
  │     ├─► LangGraph checkpointing / session persistence
  │     └─► pgvector Long-Term Memory (memory_vectors @ 1024 dims)
  │
  └─► Redis (port 6379)
        └─► Semantic Cache / Memory extraction queue
```

## Key Modules

| Module | Path | Responsibility |
|--------|------|----------------|
| **Config** | `src/config/defaults.yaml` | Single source of truth for all settings (`models.main`, `models.vision`, `models.embedding`, `models.pentest`, `models.cloud`). Override chain: YAML → env → profile |
| **Config Loader** | `src/config/config_loader.py` | Layered config with typed accessors (`get_main_model_name`, `get_vision_model_name`, `get_embedding_model_name`, `get_pentest_model_name`), env var mapping, validation |
| **Agent Graph** | `src/agent/core/graph.py` | LangGraph orchestration: memory→router→simple/complex→tools→memory |
| **Checkpointer** | `src/agent/core/checkpointer.py`| PostgreSQL checkpointer (`AsyncPostgresSaver`) managing state |
| **Router** | `src/agent/routing/router.py` | Routing: `simple`, `complex-default`, `complex-cloud` — keyword bypass, LLM classifier, HITL |
| **Simple Node** | `src/agent/core/simple.py` | Fast answers via local unified model (`gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m`), retry-once on failure |
| **Complex Facade** | `src/agent/core/complex.py` | Tool-augmented reasoning coordinator facade |
| **Complex Prompt** | `src/agent/core/complex_prompt.py` | Prompt templates, stable/volatile layering, deterministic tool sorting |
| **Complex Executor** | `src/agent/core/complex_executor.py` | LLM invocation, fallback management, cutoff continuation |
| **Complex Tool Action** | `src/agent/core/complex_tool_action.py` | Parallel tool dispatch, output bounding, in-place error recovery |
| **Cloud payload** | `src/agent/cloud/cloud_payload.py` | Anonymization, brief gate, stable/volatile prompt layers, cache metrics |
| **Cloud invoke** | `src/agent/cloud/cloud_invoke.py` | Raw DeepSeek client, tool strict mode, reasoning replay |
| **Error Classifier** | `src/agent/cloud/error_classifier.py` | Fine-grained API error categorization and jittered exponential backoff |
| **Vision proxy** | `src/agent/core/complex_utils/vision_*.py` | Dedicated VLM (`baidu.unlimited-ocr`) → structured OCR → text for DeepSeek cloud path |
| **Screen assist** | `src/tools/screen_assist/` | tmux, macOS AX, browser, Kali SSH tools |
| **Memory** | `src/agent/nodes/memory.py` | Memory injection + write: STM, LTM (PostgreSQL pgvector 1024-dim), personal context |
| **Summarizer** | `src/agent/nodes/summarize.py` | 3-tier context compaction: tool output pre-pruning + reference-only task snapshot header |
| **HITL** | `src/agent/hitl/` | Safety gates: scope_clarify, plan_review, security_proxy |
| **LLM Pool** | `src/agent/llm.py` | Singleton pool: main local model + vision + cloud instances |
| **Tool Registry** | `src/tools/registry.py` | Dynamic tool registry with `@registry.register`, `check_fn` gating, error bounding |
| **Tools** | `src/tools/` | Web search, file ops, notebook, skills, MCP |
| **Tool Reranker** | `src/agent/tool_reranker.py` | Semantic tool reranking using MXBAI embeddings |
| **API** | `src/api/server.py` | FastAPI with REST + WebSocket + OpenAI-compatible endpoints |
| **Scheduler** | `src/api/scheduler_manager.py` | APScheduler for autonomous background jobs |
| **Power monitor** | `src/api/power_monitor.py` | Async battery status watcher via pmset, handles Eco-Mode transitions |
| **Idle manager** | `src/api/idle_manager.py` | Resource optimization watcher (LLM model unload, StirlingPDF shutdown) |
| **Thought Graph** | `src/memory/thought_graph.py` | Conversation identity for Normal/Study (ThoughtNode = LangGraph thread). Chat-only: no project folders / file watcher; uploads inlined into turns. Graph API adds cluster/dormancy metadata (`topic_cluster_id`, `fade_alpha`, `radial_tier`) without merging thread IDs; Mindmap Canvas fades/drifts dormant topics and groups by cluster. Pentest uses isolated engagement graph endpoints. |
| **Frontend** | `frontend-v2/` | React 19 + Vite + Zustand + ForceGraph2D (Coggle Organic Mindmap + Maya Node Editor) + Electron |

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
  ├── simple ──► simple_node (Main local model, direct response)
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
- `docs/features/MEMORY.md` — Memory system documentation
- `docs/architecture/CLOUD-LLM-ARCHITECTURE.md` — Cloud connection, caches, cost tracking
- `docs/architecture/DEEPSEEK_V4_INTEGRATION.md` — DeepSeek V4 API + optimization reference
- `docs/guides/dev-startup.md` — Dev setup and config reference
- `src/config/defaults.yaml` — Centralized configuration
- `docs/standards/coding-style.md` — Code conventions
