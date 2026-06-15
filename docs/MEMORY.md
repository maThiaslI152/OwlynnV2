---
status: active
category: architecture
last_updated: 2026-06-11
owner: ai-agent
audience: agent
---

# Memory System — Short-Term, Long-Term, and Personal

> **Purpose:** Three-tier memory, inject/retrieve/write pipeline, and project scoping.

## Overview

Owlynn uses layered memory (STM, LTM, personal context, scenarios) with a **split inject path** so the router stays under ~300ms.

| Tier | Storage | What It Stores | Retrieval |
|------|---------|---------------|-----------|
| **Short-Term (STM)** | `data/memories.json` | Important facts from recent conversations | Keyword search via `memory_manager.py` |
| **Long-Term (LTM)** | Qdrant via Mem0 | Embedding-indexed facts + L1 atoms | Semantic search (gated) |
| **Personal** | `data/topics.json`, `data/interests.json`, `data/conversations.json` | User topics, interests, conversation history | Time-decay-weighted relevance |
| **L2/L3 scenarios** | `scenarios/*/playbook.md`, `constraints.md` | Pentest / research workflows | Router `scenario_id` + markdown loader |

## Memory Injection Flow (Phase 1)

```text
memory_inject_lite → router → memory_retrieve → …
```

1. **`memory_inject_lite`** — profile, persona, topics (no vector search)
2. **Router** — sets `needs_memory_retrieval`, optional `scenario_id`
3. **`memory_retrieve`** — Qdrant/Mem0 only when gated; loads scenario markdown; compresses for cloud brief

Caches the lite bundle for 5 minutes (TTL configurable).

See [memory-vision-screen-roadmap.md](guides/memory-vision-screen-roadmap.md) for the full 3-phase arc (memory, vision proxy, screen assist).

## Memory Write Flow

After the agent responds, `memory_write_node`:
1. PII-scrubs content before persistence
2. Enqueues custom extraction (Redis stream → worker → L1 atoms in Qdrant)
3. Extracts topics and updates topic/interests tracking
4. Records the conversation in `conversations.json`
5. Invalidates the memory cache for the next turn

### Background extraction (Qwen) — resource deferral

LTM atom extraction uses the **medium** slot (Qwen3.5-9B) in a background worker. To avoid GPU/CPU contention with active chat or local fallback:

```text
memory_write → Redis queue → worker waits for idle window → invoke_medium_background() → Mem0
```

**Defer conditions** (configurable in `defaults.yaml`):

- No active graph run (`GraphSession` registers start/end)
- No foreground medium-LLM call (agent complex/simple local path)
- Post-turn cooldown (`idle_cooldown_seconds`, default 8s)
- Lower CPU priority during invoke (`process_nice`, default 10)

LM Studio does **not** expose per-request GPU throttling via the OpenAI API; defer-until-idle is the practical mitigation on Apple Silicon unified memory.

**Module:** `src/agent/local_llm_scheduler.py`  
**Worker:** `src/memory/extraction/worker.py` (`get_medium_llm(foreground=False)`)

## Configuration

```yaml
memory:
  max_facts: 200                    # Max STM facts before pruning
  search_window: 50                 # STM search result limit
  cache:
    ttl: 300                        # Memory context cache (5 min)
    cleanup_interval: 600           # Cache cleanup interval (10 min)
  thread_cleanup_interval: 3600     # Thread state cleanup (1 hour)
  decay:
    topic_half_life_days: 14       # Topic relevance half-life
    interest_half_life_days: 21    # Interest relevance half-life
    focus_window_days: 3           # Recent focus detection window
    relevance_floor: 0.05          # Minimum relevance score
  extraction:
    temperature: 0.1
    max_tokens: 1024
    idle_cooldown_seconds: 8       # Wait after turn before extraction
    idle_poll_seconds: 2
    max_idle_wait_seconds: 600     # Run anyway after 10m
    defer_while_graph_active: true
    process_nice: 10                 # Lower CPU priority (Unix)
```

## Context Budget Management

Memory context is capped at 12000 characters (~3000 tokens) to stay within the model's context window. This prevents exceeding LM Studio's default `n_ctx=8192`.

The summarization system compresses older conversation turns when token usage exceeds 85% of the context window. Recent turns (last 10) are preserved in full. Summaries include a "Topics Discussed" section for continuity across compressions.

## Vector Lifecycle Management

The `VectorLifecycleManager` orchestrates the insertion and deletion of vector data within Mem0 and Qdrant. It is hooked into the file watcher events to ensure data integrity:
- **Orphan Prevention**: Deleting a workspace file instantly drops its vectors from Qdrant.
- **Deduplication Check**: When a file is updated, the system natively deletes the old chunks before embedding the new ones, preventing a `1+N` vector explosion per save.
- **Project Scope Isolation**: `MemoryContextCache` explicitly keys memories to `thread_id:project_id` to strictly prevent bleeding context when a user switches workspaces. Additionally, the `recall_all_memories` tool dynamically binds its search queries to the current active project via `ContextVar`.

## Known Issues

1. **Mem0 requires `mem0ai[nlp]`** — install with `pip install mem0ai[nlp]` for spaCy/fastembed support
2. **Memory context cap may cut important facts** — injected memory text is capped at **12000 characters** in `format_memory_context` (see `memory.py`); enhanced blocks use a separate 6000-char budget
3. **No STM→LTM promotion** — frequently recalled facts aren't auto-promoted to LTM with higher priority

## Related Files

- `src/agent/nodes/memory.py` — `memory_inject_lite`, `memory_retrieve`, `memory_write`
- `src/memory/extraction/` — Custom extractor worker + schema
- `src/agent/local_llm_scheduler.py` — Foreground/background medium LLM deferral
- `src/memory/scenarios.py` — L2/L3 scenario markdown
- `src/memory/compression.py` — Cloud brief memory block
- `src/agent/pii_scrubber.py` — PII scrub before LTM writes
- `src/memory/memory_manager.py` — STM (memories.json)
- `src/memory/long_term.py` — LTM (Mem0 + Qdrant)
- `src/memory/personal_assistant.py` — Topic/interest tracking
- `src/agent/nodes/summarize.py` — Auto-summarization
- `src/config/defaults.yaml` — Memory configuration
