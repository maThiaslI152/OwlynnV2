# Memory System — Short-Term, Long-Term, and Personal

> **Last updated:** 2026-06-04

## Overview

Owlynn uses a three-tier memory system to maintain conversation context across sessions:

| Tier | Storage | What It Stores | Retrieval |
|------|---------|---------------|-----------|
| **Short-Term (STM)** | `data/memories.json` | Important facts from recent conversations | Keyword search via `memory_manager.py` |
| **Long-Term (LTM)** | Qdrant via Mem0 | Embedding-indexed facts | Semantic search via Mem0 API |
| **Personal** | `data/topics.json`, `data/interests.json`, `data/conversations.json` | User topics, interests, conversation history | Time-decay-weighted relevance |

## Memory Injection Flow

Every user message triggers `memory_inject_node` which:
1. Searches Mem0/Qdrant for semantically relevant past facts
2. Loads user profile, persona, project instructions
3. Retrieves enhanced context (topics, interests, recent conversations)
4. Formats everything into a `memory_context` string injected before the router
5. Caches the result for 5 minutes (TTL configurable)

## Memory Write Flow

After the agent responds, `memory_write_node`:
1. Extracts key facts from the conversation turn
2. Saves facts to Mem0 for future semantic retrieval
3. Extracts topics and updates topic/interests tracking
4. Records the conversation in `conversations.json`
5. Invalidates the memory cache for the next turn

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
```

## Context Budget Management

Memory context is capped at 6000 characters (~1500 tokens) to stay within the model's context window. This was reduced from unlimited to prevent exceeding LM Studio's default `n_ctx=8192`.

The summarization system compresses older conversation turns when token usage exceeds 85% of the context window. Recent turns (last 10) are preserved in full. Summaries include a "Topics Discussed" section for continuity across compressions.

## Known Issues

1. **Mem0 requires `mem0ai[nlp]`** — install with `pip install mem0ai[nlp]` for spaCy/fastembed support
2. **Memory context cap may cut important facts** — the 6000-char limit is a trade-off for context window compatibility
3. **No STM→LTM promotion** — frequently recalled facts aren't auto-promoted to LTM with higher priority

## Related Files

- `src/agent/nodes/memory.py` — Memory injection and write nodes
- `src/memory/memory_manager.py` — STM (memories.json)
- `src/memory/long_term.py` — LTM (Mem0 + Qdrant)
- `src/memory/personal_assistant.py` — Topic/interest tracking
- `src/agent/nodes/summarize.py` — Auto-summarization
- `src/config/defaults.yaml` — Memory configuration
