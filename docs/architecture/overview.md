# Architecture Overview — OwlynnV2

> **System context, modules, data flow, and key entrypoints.**
> Last updated: 2026-06-04

## System Context

Owlynn is a local-first AI coworker for Apple Silicon (Mac M4 Air 24GB). It runs entirely on-device using LM Studio for LLM inference with a three-tier model strategy. No data leaves the machine unless the user explicitly opts into cloud escalation.

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
  │     └─► Local LLM inference (small/medium models)
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
| **Router** | `src/agent/nodes/router.py` | 5-way routing with keyword bypasses, LLM classification, HITL gates |
| **Simple Node** | `src/agent/nodes/simple.py` | Fast answers via small model (0.8B), with medium fallback |
| **Complex Node** | `src/agent/nodes/complex.py` | Tool-augmented reasoning via medium model (9B), cloud escalation |
| **Memory** | `src/agent/nodes/memory.py` | Memory injection + write: STM, LTM (Mem0/Qdrant), personal context |
| **Summarizer** | `src/agent/nodes/summarize.py` | Auto-compress older turns when context >85% of window |
| **HITL** | `src/agent/hitl/` | Safety gates: scope_clarify, plan_review, security_proxy |
| **LLM Pool** | `src/agent/llm.py` | Singleton pool: small + medium (swappable) + cloud instances |
| **Swap Manager** | `src/agent/swap_manager.py` | LM Studio model hot-swap for medium variants |
| **Tools** | `src/tools/` | Web search, file ops, notebook, skills, MCP |
| **API** | `src/api/server.py` | FastAPI with REST + WebSocket + OpenAI-compatible endpoints |
| **Frontend** | `frontend-v2/` | React 19 + Vite + Zustand + Playwright evals |

## Agent Flow

```
User Message
  │
  ▼
memory_inject ──► Load LTM/STM/persona/profile context
  │
  ▼
summarize_gate ──► If tokens >85% context: auto_summarize → compress history
  │
  ▼
router ──► Classify: simple vs complex (keyword bypass → LLM classifier)
  │
  ├── simple ──► simple_node (0.8B small model, fast)
  │                  │
  │                  ▼
  │              memory_write ──► Save facts, topics, invalidate cache
  │
  └── complex ──► scope_clarify ──► complex_llm (9B medium model)
                        │                  │
                        │    ┌─────────────┘
                        │    ▼
                        │  plan_review / security_proxy (HITL gates)
                        │    │
                        │    ▼
                        │  tool_action ──► web search, file ops, REPL
                        │    │
                        │    ▼
                        │  complex_llm ──► cycle until no tools pending
                        │
                        ▼
                   memory_write
```

## Configuration Architecture

Single source of truth in `src/config/defaults.yaml` (19 top-level sections, ~150 settings).

**Override priority (lowest → highest):**
```
defaults.yaml  →  environment variables  →  user_profile.json
```

**Key sections:**
- `models` — small/medium/cloud/embedding: names, base_urls, temps, budgets, extra_body
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
- `docs/guides/dev-startup.md` — Dev setup and config reference
- `src/config/defaults.yaml` — Centralized configuration
- `specs/memory/constitution.md` — Non-negotiable constraints
