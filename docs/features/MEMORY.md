---
status: active
category: architecture
last_updated: 2026-08-26
owner: ai-agent
audience: agent
---

# Memory System — Short-Term, Long-Term, and Personal

> **Purpose:** Three-tier memory, inject/retrieve/write pipeline, and project scoping.

## Overview

Owlynn uses layered memory (STM, LTM, personal context, scenarios) with a **split inject path** so the router stays under ~300ms. **Postgres + pgvector is the durable hub** for checkpoints, LTM, semantic cache, extraction jobs, and thought-graph data. Redis/Qdrant are not used.

| Tier | Storage | What It Stores | Retrieval |
|------|---------|---------------|-----------|
| **Short-Term (STM)** | PostgreSQL (`memories` table) | Important facts from recent conversations | Keyword search via `memory_manager.py`. |
| **Long-Term (LTM)** | PostgreSQL pgvector (`memory_vectors` table) | Embedding-indexed facts + L1 atoms | Semantic search (gated via text-embedding-mxbai-embed-large-v1, 1024-dim) |
| **Thought Graph** | PostgreSQL (`thought_nodes`, `thought_edges` tables) | Interconnected mindmap thoughts, attack chains, and knowledge relations | Graph traversal, semantic topic clusters (no thread-ID merge), dormancy fade/drift signals, REST API (`/api/graph/data`) |
| **Personal** | `data/topics.json`, `data/interests.json`, `data/conversations.json` | User topics, interests, conversation history | Time-decay-weighted relevance |
| **L2/L3 scenarios** | `scenarios/*/playbook.md`, `constraints.md` | Pentest / research workflows | Router `scenario_id` + markdown loader |
| **Semantic Cache** | PostgreSQL pgvector (`semantic_cache` table) | Previous AI answers keyed by prompt embedding | Vector similarity (`>= 0.92`) — bypasses graph entirely |
| **Extraction Queue** | PostgreSQL (`extraction_jobs` table) + LISTEN/NOTIFY | Async memory & procedural skill synthesis queue | Dual-channel extraction worker (`worker.py`) |

**HTTP:** Canonical LTM paths are `/api/memory/*` (legacy `/api/mem0/*` aliases). The `mem0_uid` DB column remains — not the Mem0 library.

## Memory Injection Flow (Phase 1)

```text
memory_inject_lite → router → memory_retrieve → …
```

1. **`memory_inject_lite`** — profile, persona, topics (no vector search)
2. **Router** — sets `needs_memory_retrieval`, optional `scenario_id`
3. **`memory_retrieve`** — pgvector LTM only when gated; loads scenario markdown; compresses for cloud brief

Caches the lite bundle for 5 minutes (TTL configurable).

See [memory-vision-screen-roadmap.md](guides/memory-vision-screen-roadmap.md) for the full 3-phase arc (memory, vision proxy, screen assist).

## Memory Write Flow

After the agent responds, `memory_write_node`:
1. PII-scrubs content before persistence
2. Neutralizes prompt injection patterns (e.g., "ignore previous instructions") via `pii_scrubber.scrub_for_memory_write()`
3. Enqueues custom extraction (Postgres `extraction_jobs` → worker → L1 atoms in `memory_vectors`)
4. Extracts topics and updates topic/interests tracking
5. Records the conversation in `conversations.json`
6. Invalidates the memory cache for the next turn

### Background extraction (Gemma 4 12B Agentic) — resource deferral

LTM atom extraction uses the unified local model (`models.main`, `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m`) in a background worker. It has been upgraded to an Observer/Reflector 2-phase LLM pipeline for deduplication. To avoid GPU/CPU contention with active chat or local fallback:

```text
memory_write → Postgres extraction_jobs → worker waits for idle window → invoke_main_background() → memory_vectors
```

**Defer conditions** (configurable in `defaults.yaml`):

- No active graph run (`GraphSession` registers start/end)
- No foreground local-LLM call (agent complex/simple local path)
- Post-turn cooldown (`idle_cooldown_seconds`, default 8s)
- Lower CPU priority during invoke (`process_nice`, default 10)
- **Eco-Mode (Battery Power)**: The background extraction worker automatically suspends and queues jobs when the Mac is disconnected from power, avoiding battery drain.

LM Studio does **not** expose per-request GPU throttling via the OpenAI API; defer-until-idle is the practical mitigation on Apple Silicon unified memory.

### Dual-Channel Autonomous Learning Loop (Hermes-Style)

The PostgreSQL extraction worker operates a dual-channel learning pass:
1. **Declarative Fact Channel:** Extracts structured memory atoms (L1) with semantic deduplication and stores them in `memory_vectors`.
2. **Procedural Skill Channel:** Analyzes user corrections, workflow sequences, and tool execution recipes using `SkillLearnerEngine` (`src/memory/skills_learner.py`). It applies a 4-tier cascade:
   - *Patch Active Skill:* Appends learned pitfalls/workarounds to loaded skill packages.
   - *Update Umbrella:* Extends domain umbrella skills.
   - *Author Support Files:* Generates `references/`, `templates/`, and `scripts/` inside `skills/<category>/<skill_name>/`.
   - *Synthesize Class-Level Skill:* Automatically creates new `agentskills.io` compliant skill packages.

**Module:** `src/agent/local_llm_scheduler.py`  
**Worker:** `src/memory/extraction/worker.py` (`get_extraction_llm(foreground=False)`)  
**Skill Engine:** `src/memory/skills_learner.py` (`SkillLearnerEngine`)

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

Memory context is capped at 24000 characters (~6000 tokens) to stay within the model's context window. This prevents exceeding LM Studio's default `n_ctx=8192`.

The summarization system compresses older conversation turns when token usage exceeds 85% of the context window. Recent turns (last 10) are preserved in full. Summaries include a "Topics Discussed" section for continuity across compressions.

## Vector Lifecycle Management

The `VectorLifecycleManager` orchestrates insertion and deletion of vector data in Postgres `memory_vectors`. **Normal/Study are chat-only** (no file watcher / durable project folders); uploads are inlined into the turn. Pentest evidence remains under engagement-scoped paths.
- **Conversation identity**: `ThoughtNode.id` = LangGraph `thread_id`. `MemoryContextCache` keys by `thread_id`.
- **Organic map shaping**: `/api/graph/data` ranks nodes by recency + dormancy (pinned resist fade). Related threads share `topic_cluster_id` / `topic_label` via semantic edges; IDs are never merged (`merges_with` is an edge label only). Manual `canvas_x`/`canvas_y` suppress `allow_radial_drift`. Selecting or `get_or_create` immediately revives `last_active_at`. Title (+ tags) is the embedding fallback when summary is empty. The Mindmap Canvas applies `fade_alpha` / reduced link particles, optional radial drift for unplaced nodes, cluster cohesion, backend `search=` (override fade + beyond the 300-node cap), and a **Focus recent** control (`show_dormant=false`). Pentest stays off the shared graph.
- **User id for memory rows**: profile name (or `"owner"`) via `mem0_uid` — not `project:{id}` silos.
- **Deduplication** (when vectors are written): updates replace old chunks before embedding new ones.
- **`recall_all_memories`**: binds search to the active thread via `ContextVar` where applicable.

## When Postgres is degraded

Postgres is core (single local container — not HA). Soft-fail behavior:

| Subsystem | Degraded behavior |
|-----------|-------------------|
| Chat / tools | Continues |
| LTM search/add, semantic cache, extraction enqueue, thought-graph writes | Skip / empty / soft-miss |
| Checkpoints | Startup may fall back to `MemorySaver`; durability lost until Postgres returns |
| Profile / persona JSON | Unaffected |

See [`docs/architecture/POSTGRES_MEMORY_LIFECYCLE.md`](../architecture/POSTGRES_MEMORY_LIFECYCLE.md).

## Known Issues

1. **Memory context cap may cut important facts** — injected memory text is capped at **24000 characters** in `format_memory_context` (see `memory.py`); enhanced blocks use a separate 6000-char budget
2. **No STM→LTM promotion** — frequently recalled facts aren't auto-promoted to LTM with higher priority
3. **Legacy chats without checkpoints** — chats created before the Postgres checkpointer was enabled show "History unavailable" in the UI. The sidebar displays a ⚠️ icon on affected chats. These conversations cannot be recovered.

## Checkpoint Persistence

Conversation history is stored in PostgreSQL natively via LangGraph's `AsyncPostgresSaver` (in `src/agent/core/checkpointer.py`). Each graph run automatically saves checkpoints after every step.

### Startup Verification

On startup, `init_agent()` performs a round-trip write test (`aput` → `aget_tuple` → cleanup) to verify the PostgreSQL checkpointer can actually persist data. If the test fails, the system falls back to `MemorySaver` with a warning — conversations will NOT persist across restarts.

### Legacy Chat Detection

On startup, a background task scans all PostgreSQL chat records and checks for corresponding checkpoint tuples via `aget_tuple()`. Chats without checkpoint data are logged:

```
[startup] 5/20 chats have no checkpoint data (created before checkpointer).
These chats will show 'history unavailable' when opened.
```

The `/api/projects/{project_id}` endpoint enriches each chat object with a `has_checkpoint` boolean. The frontend uses this to display a ⚠️ icon in the sidebar.

### Post-Run Verification

After each graph run completes, `GraphSession._execute` fires a background check to verify the checkpoint was persisted. If no checkpoint key is found for the thread, a warning is logged:

```
No checkpoint found for thread <thread_id> after graph run —
history may not persist across restarts
```

### History API Response Format

`GET /api/history/{thread_id}` returns a structured response:

```json
{
  "messages": [...],
  "status": "ok" | "no_checkpoint_data" | "error" | "agent_unavailable"
}
```

The frontend handles both the new structured format and the legacy array format for backward compatibility.

## Related Files

- `src/agent/nodes/memory.py` — `memory_inject_lite`, `memory_retrieve`, `memory_write`
- `src/memory/extraction/` — Custom extractor worker + schema
- `src/agent/local_llm_scheduler.py` — Foreground/background unified local model deferral
- `src/memory/scenarios.py` — L2/L3 scenario markdown
- `src/memory/compression.py` — Cloud brief memory block
- `src/agent/pii_scrubber.py` — PII scrub before LTM writes
- `src/memory/memory_manager.py` — STM
- `src/memory/long_term.py` — LTM (Postgres pgvector)
- `src/memory/semantic_cache.py` — Semantic response cache (pgvector)
- `src/memory/personal_assistant.py` — Topic/interest tracking
- `src/agent/nodes/summarize.py` — Auto-summarization
- `src/config/engagement_crypto.py` — Fernet master key storage (macOS Keychain)
- `src/config/defaults.yaml` — Memory configuration
- `src/agent/core/checkpointer.py` — `AsyncPostgresSaver` LangGraph checkpointer initialization
- `docs/features/SEMANTIC_CACHE.md` — Semantic cache feature documentation
- `docs/architecture/POSTGRES_MEMORY_LIFECYCLE.md` — Postgres extraction + semantic-cache lifecycle
