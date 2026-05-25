---
last_verified: 2026-05-26
auto_generated: false
---

# Architecture Overview

Owlynn is a local-first AI productivity agent built with LangGraph for orchestration and FastAPI for the backend. Optimized for Apple Silicon (M4 Air 24GB) with a three-tier S/M(swap)/L hybrid LLM architecture.

## Overview

The system operates under a hard VRAM constraint: the M4 Air 24GB unified memory can only hold the S model + one M-tier model + embeddings simultaneously. The S tier (Small) is always loaded. The M tier (Medium) swaps between three task-specific variants. The L tier (Large) is a cloud API used only when local models cannot handle the task.

## Entry Points

```text
src/agent/graph.py          # init_agent(), route_decision()
src/agent/llm.py            # LLMPool singleton
src/agent/swap_manager.py   # SwapManager
src/agent/tool_sets.py      # ToolboxRegistry, resolve_tools()
src/agent/anonymization.py   # AnonymizationEngine
src/api/server.py            # FastAPI + WebSocket handler
frontend-v2/src/App.tsx      # React app shell
```

## Architecture

### Three-Tier LLM Architecture

| Key | Model | Role | VRAM | Context Window |
|-----|-------|------|------|----------------|
| Small_LLM | `ibm-grok4-ultrafast-coder-1b` (Q8_0) | Routing, simple answers, chat titles | ~1.7 GB | 4,096 |
| Medium_Default | `qwen3.5-9b-mlx` (MLX 4bit) | General complex reasoning, tool calling | ~6 GB | 100,000 |
| Medium_Vision | `qwen3.5-9b-mlx` (MLX 4bit) | Image/multimodal processing | ~6 GB | 100,000 |
| Medium_LongCtx | `qwen3.5-9b-mlx` (MLX 4bit) | Extended context tasks | ~6 GB | 131,072 |
| Cloud_LLM | `deepseek-chat` (DeepSeek API) | Frontier-quality reasoning (cloud) | N/A | 131,072 |

Small_LLM and one M-tier model are served via LM Studio on port 1234 (OpenAI-compatible API). Cloud_LLM uses the DeepSeek API at `https://api.deepseek.com/v1`.

### Graph Flow

```
memory_inject → router ──→ simple ──────────────────→ memory_write → END
                  │
                  ├──→ complex-default ──→ complex_llm ↔ security_proxy ↔ tool_action → memory_write → END
                  ├──→ complex-vision  ──→ complex_llm ↔ security_proxy ↔ tool_action → memory_write → END
                  ├──→ complex-longctx ──→ complex_llm ↔ security_proxy ↔ tool_action → memory_write → END
                  └──→ complex-cloud   ──→ complex_llm ↔ security_proxy ↔ tool_action → memory_write → END
```

### Router: Two-Stage Decision

1. **Stage 1**: Classify as `simple` vs `complex` (keyword heuristics + Small_LLM)
2. **Stage 2 (complex only)**: Select model variant:
   - Image attachments → `complex-vision`
   - Input tokens > 80% of Medium_Default context → `complex-longctx`
   - Input tokens > Medium_LongCtx context or frontier-quality indicators → `complex-cloud`
   - Default → `complex-default`
   - Prefer currently-loaded variant when borderline (avoid swap latency)

### Node Descriptions

| Node | Behavior |
|------|----------|
| `memory_inject` | Loads user profile, persona, topics, interests, and long-term memory context |
| `router` | Small_LLM classifies message and selects route + toolbox categories. Keyword heuristics bypass LLM for obvious cases. Conversations with tool history stay on `complex` |
| `simple` | Small_LLM gives short direct answers. No tools. Falls back to Medium_Default on failure |
| `complex_llm` | Selected M-tier or Cloud model with dynamically-bound tools. Emits tool calls or direct answers |
| `security_proxy` | Gates sensitive tools (`write_workspace_file`, `edit_workspace_file`, `delete_workspace_file`, `notebook_run`). Auto-approves safe tools |
| `tool_action` | Executes approved tool calls via `ToolNode`, loops back to `complex_llm` |
| `memory_write` | Extracts topics/interests, saves to Mem0/Qdrant, invalidates cache |

## API

### LLMPool (`src/agent/llm.py`)

Manages three cached instance slots:

| Slot | Method | Description |
|------|--------|-------------|
| `_small_llm` | `get_small_llm()` | Always-loaded Small_LLM. ~700 tok/s prompt, ~110 tok/s gen |
| `_medium_llm` | `get_medium_llm(variant)` | Currently-loaded M-tier model. Returns cached instance if variant matches; triggers SwapManager if not |
| `_cloud_llm` | `get_cloud_llm()` | DeepSeek API client. `streaming=True`, `max_tokens=8192`, `temperature=0.4` |

- `_current_medium_variant` tracks which M-tier model is loaded (`"default"`, `"vision"`, `"longctx"`, or `None`)
- `get_large_llm()` is an alias for `get_medium_llm("default")` (backward compatibility)
- `clear()` resets all slots and `_current_medium_variant`
- API key resolution: `DEEPSEEK_API_KEY` env var → `deepseek_api_key` in User_Profile → cloud disabled

### SwapManager (`src/agent/swap_manager.py`)

Wraps the LM Studio native API (`http://127.0.0.1:1234/api/v1/`) for model load/unload. Uses `httpx.AsyncClient`.

**Swap sequence** (only one M-tier model loaded at a time):

1. `GET /api/v1/models` — get `instance_id` of currently loaded M-tier model
2. `POST /api/v1/models/unload` with `{instance_id}`
3. `POST /api/v1/models/load` with `{model: target_model_key}`
4. Poll `GET /api/v1/models` until target appears in `loaded_instances` (timeout: 120s, poll interval: 2s)

- If unload fails → proceed with load anyway (LM Studio may handle the conflict)
- If load fails or times out → raise `ModelSwapError`, caught by Complex_Node for fallback
- Model key mapping read from `User_Profile["medium_models"]`

### ToolboxRegistry (`src/agent/tool_sets.py`)

Dynamic tool loading reduces token overhead by ~2000 tokens per turn. The router selects toolbox categories; only relevant tools are bound.

**5 Toolbox Categories:**

| Category | Tools |
|----------|-------|
| `web_search` | `web_search`, `fetch_webpage` |
| `file_ops` | `read_workspace_file`, `write_workspace_file`, `edit_workspace_file`, `list_workspace_files`, `delete_workspace_file` |
| `data_viz` | `create_docx`, `create_xlsx`, `create_pptx`, `create_pdf`, `notebook_run`, `notebook_reset` |
| `productivity` | `todo_add`, `todo_list`, `todo_complete`, `list_skills`, `invoke_skill` |
| `memory` | `recall_memories` |

Always included: `ask_user` (HITL escape hatch).

`resolve_tools(toolbox_names, web_search_enabled)` returns the union of requested toolboxes + always-included tools. Passing `"all"` returns the full tool set. When `web_search_enabled=False`, web tools are excluded regardless of selection.

### AnonymizationEngine (`src/agent/anonymization.py`)

PII scrubbing for cloud-bound messages. Applies only when route is `complex-cloud` AND `cloud_anonymization_enabled` is `True`. Local M-tier models are trusted (data never leaves the machine).

`anonymize(text, context) → (anonymized_text, mapping)`
- Scans for sensitive patterns, replaces with `[CATEGORY_N]` placeholders

`deanonymize(response_text, mapping) → original_text`
- Restores placeholders to original values

Detection categories (priority order — longest match first):

1. API keys/tokens (`sk-`, `key-`, `Bearer`, `ghp_`, 32+ char alphanumeric)
2. Email addresses
3. URLs with localhost ports
4. File system paths (`/Users/`, `/home/`, `C:\`, `~/`)
5. IP addresses (excluding `0.0.0.0`, `255.255.255.255`)
6. Phone numbers (international formats)
7. Known names (from User_Profile `name` field)
8. Custom sensitive terms (from User_Profile `custom_sensitive_terms`)

Round-trip property: `deanonymize(anonymize(text, ctx)[0], anonymize(text, ctx)[1]) == text`

### Web Search Pipeline

```
Tier 0:   wttr.in (weather fast path)
Tier 0.5: SearXNG (self-hosted, localhost:8888)
Tier 1:   curl_cffi (DDG/Bing HTML scraping)
Tier 2:   DDGS Python library / httpx fallbacks
Tier 3:   Playwright (full browser)
```

### Tiered Fallback Chain

The system ensures users always get a response:

| Rank | Scenario | Fallback |
|------|----------|----------|
| 1 | Cloud failure | Retry with Medium_Default. HTTP 401/403 → suggest checking API key. HTTP 429 → retry after 2s, then Medium_Default |
| 2 | Medium_Vision failure | Medium_Default |
| 3 | Medium_LongCtx failure | Cloud_LLM first, then Medium_Default with truncated context |
| 4 | Medium_Default failure | Return error suggesting user check LM Studio |
| 5 | Small_LLM failure | Medium_Default |
| 6 | Model swap failure (`ModelSwapError`) | Currently-loaded M-tier variant |

All fallbacks set `model_used` with `-fallback` suffix.

### Frontend Inspector Panels

| Panel | Data Source | Requirements |
|-------|------------|--------------|
| Orchestration | `router_info` WS event | WebSocket |
| Memory & Context | `GET /api/topics`, `GET /api/interests`, `GET /api/mem0/search`, `GET /api/memory-context` | WebSocket + REST |
| Safe Mode | Tauri IPC | Tauri IPC bridge |
| Screen Assist | Tauri IPC | Tauri IPC bridge |
| Tool Execution | Tool lifecycle events + audit export | WebSocket |
| Action Proposals | Security approval interrupts | WebSocket |

### Infrastructure

| Service | Container | Port | Config |
|---------|-----------|------|--------|
| Redis | `redis/redis-stack-server:latest` (AOF persistence, 512 MB cap) | 6379 | `REDIS_URL` |
| Qdrant | Docker image | 6333 | `QDRANT_HOST`, `QDRANT_PORT` |
| SearXNG | `searxng/searxng:latest` | 8888 | `SEARXNG_URL` |
| LM Studio | Native macOS app | 1234 | Small/Medium LLM base URLs |

### Redis Checkpointer

Conversation history persists across model swaps and server restarts via `langgraph-checkpoint-redis` (`AsyncRedisSaver`):

```python
from langgraph_checkpoint_redis import AsyncRedisSaver

checkpointer = AsyncRedisSaver(url=REDIS_URL)
await checkpointer.setup()
```

- Falls back to `MemorySaver` if Redis unavailable
- Each conversation thread maintains isolated state via `Thread_ID`
- Messages, routing metadata, and tool call history preserved across M-tier swaps

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Three-tier S/M/L routing | Local-first with cloud fallback | Swap latency for M-tier model changes |
| Dynamic toolbox selection | Saves ~2000 tokens/turn | Router must classify correctly |
| PII anonymization for cloud | Privacy for cloud-bound messages | Adds processing latency; pattern-based detection may miss novel PII formats |
| Redis checkpointing | Conversation persistence across restarts | Requires Redis container |
| Tauri desktop shell | Native macOS features, small binary | Tauri IPC dependency blocks browser-only deployment |

## Testing

- Backend: `pytest tests/ -v` (unit, integration, property-based)
- Frontend: `cd frontend-v2 && npx vitest run && npm run build`

## Configuration

| Env Var | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis for LangGraph checkpointing |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `SEARXNG_URL` | _(empty)_ | SearXNG instance URL |
| `DEEPSEEK_API_KEY` | _(empty)_ | DeepSeek API key for cloud tier |
| `OPTIMIZE_FOR_M4` | `false` | M4 Air optimizations |

Profile fields (`data/user_profile.json`):

| Field | Type | Default |
|-------|------|---------|
| `cloud_escalation_enabled` | boolean | `true` |
| `cloud_anonymization_enabled` | boolean | `true` |
| `custom_sensitive_terms` | list | `[]` |
| `medium_models` | object | Three variant keys |
