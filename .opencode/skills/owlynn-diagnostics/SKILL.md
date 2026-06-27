---
name: owlynn-diagnostics
description: Use when diagnosing Owlynn agent behavior, debugging conversations, checking routing decisions, reviewing logs or traces, fixing tool failures, or understanding the agent graph. Covers architecture, node flow, routing, memory, HITL, logging, and conversation traces. Trigger on keywords: owlynn, agent, router, trace, logcat, audit, conversation, thread, HITL, memory, tool failure, complex-cloud, simple route, defaults.yaml, start.sh.
---

# Owlynn Diagnostics

Comprehensive reference for diagnosing and fixing issues in the Owlynn AI coworker agent.

## Quick Start

### Health Check

```bash
# Containers (Qdrant + Redis)
podman ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "qdrant|redis"

# LM Studio (expect >= 1 model loaded)
curl -s http://127.0.0.1:1234/v1/models | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',[])))"

# Backend
curl -s http://127.0.0.1:8000/api/unified-settings | head -c 80

# CI gate
./scripts/ci.sh --quick
```

### "What happened in conversation X?"

```bash
# View latest conversation trace
python scripts/trace_view.py --latest

# View specific thread (JSON for programmatic use)
python scripts/trace_view.py <thread_id> --json

# List all traces
python scripts/trace_view.py --list
```

### Start the App

```bash
./start.sh          # Containers → LM Studio → Backend + Frontend
./start.sh --debug  # With DEBUG logging + audit enabled
```

---

## Architecture

### Port Map

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | `http://127.0.0.1:5173` | React 19 + Vite + Electron |
| Backend | `http://127.0.0.1:8000` | FastAPI (REST + WebSocket) |
| LM Studio | `http://127.0.0.1:1234` | Local LLM inference |
| Qdrant | `http://127.0.0.1:6333` | Vector DB (LTM / Mem0) |
| Redis | `redis://localhost:6379` | LangGraph checkpointing |
| StirlingPDF | `http://localhost:8090` | PDF text extraction + OCR |

### Key Modules

| Module | Path |
|--------|------|
| Config (single source of truth) | `src/config/defaults.yaml` |
| Config loader | `src/config/config_loader.py` |
| Agent graph | `src/agent/core/graph.py` |
| Router | `src/agent/routing/router.py`, `src/agent/routing/classifier.py`, `src/agent/routing/budget.py`, `src/agent/routing/selector.py` |
| Simple node | `src/agent/core/simple.py` |
| Complex node | `src/agent/core/complex.py` |
| Cloud payload | `src/agent/core/complex_utils/cloud_payload.py` |
| Cloud invoke | `src/agent/core/complex_utils/cloud_invoke.py` |
| Vision proxy | `src/agent/core/complex_utils/vision_proxy.py` |
| Memory nodes | `src/agent/nodes/memory.py` |
| Memory managers | `src/memory/` (STM: `memory_manager.py`, LTM: `long_term.py`, personal: `personal_assistant.py`) |
| Summarizer | `src/agent/nodes/summarize.py` |
| Security proxy | `src/agent/nodes/security_proxy.py` |
| Scope clarify | `src/agent/nodes/scope_clarify.py` |
| Plan review | `src/agent/nodes/plan_review.py` |
| Coherence check | `src/agent/nodes/coherence.py` |
| LLM pool | `src/agent/llm.py` |
| Tool registry | `src/agent/tool_sets.py` |
| Tool implementations | `src/tools/` |
| API server | `src/api/server.py` |
| WebSocket handler | `src/api/ws/handler.py` |
| Graph session | `src/api/controllers/graph_session.py` |
| Audit log | `src/config/audit_log.py` |
| Log middleware | `src/config/log_middleware.py` |
| Trace writer | `src/config/trace_writer.py` |
| AgentState definition | `src/agent/core/state.py` |
| User profile | `src/memory/user_profile.py` |

### Config Override Priority

```
defaults.yaml  →  environment variables (.env, .env.local)  →  user_profile.json
```

Validate config at startup:
```bash
python3 -c "from src.config.config_loader import validate_config; print(validate_config())"
```

---

## Agent Graph

### Node Flow

```
START
  → memory_inject_lite    (profile, persona, topics — no vector search)
  → router                (classify: simple | complex-cloud)
  → memory_retrieve       (gated Qdrant/Mem0 + scenario markdown)
  → [simple] OR [scope_clarify → complex_llm]
      │
      ├─ simple → simple_node (Qwen3-VL-4B) → memory_write → END
      │
      └─ complex → scope_clarify → complex_llm
                       │
                       ├─ cloud path (complex-cloud, DeepSeek V4)
                       ├─ plan_review / security_proxy (HITL gates)
                       ├─ tool_action → web search, file ops, REPL
                       ├─ complex_llm (cycle until no tools pending)
                       └─ memory_write → END
```

### Routes

| Route | Model | When |
|-------|-------|------|
| `simple` | Qwen3-VL-4B (local) | Simple factual, greetings, short tasks |
| `complex-cloud` | DeepSeek V4 (cloud) | Tool-augmented, complex reasoning, web search |

### Classification Sources

`keyword_bypass`, `deterministic`, `llm_classifier`, `hitl`

### Key AgentState Fields

| Field | Type | Purpose |
|-------|------|---------|
| `messages` | `Sequence[BaseMessage]` | Conversation history |
| `route` | `str \| None` | `"simple"` or `"complex-cloud"` |
| `model_used` | `str \| None` | `"small-local"`, `"large-cloud"`, or with `-fallback` suffix |
| `needs_memory_retrieval` | `bool \| None` | Router gate for vector retrieval |
| `selected_toolboxes` | `list[str] \| None` | e.g. `["web_search", "file_ops"]` or `["all"]` |
| `token_budget` | `int \| None` | Dynamic budget set by router |
| `pending_tool_calls` | `bool \| None` | Whether tools are queued |
| `security_decision` | `str \| None` | `"approved"` or `"denied"` |
| `active_tokens` | `int \| None` | Current token count |
| `context_window` | `int \| None` | Active model's context window |
| `api_tokens_used` | `dict \| None` | `{"prompt_tokens": int, "completion_tokens": int}` |
| `router_metadata` | `dict \| None` | Telemetry from routing decision |
| `fallback_chain` | `list[dict] \| None` | Ordered model attempt list |
| `clarified_scope` | `dict \| None` | User-approved requirements from scope_clarify |
| `plan_review_approved` | `bool \| None` | Plan review HITL result |
| `response_confidence` | `float \| None` | Coherence score |
| `coherence_retry_reason` | `str \| None` | Last coherence issue |
| `_coherence_retry_round` | `int \| None` | Coherence retry counter |

---

## Routing

### Current Models

| Slot | Model | Purpose |
|------|-------|---------|
| `models.small` | `qwen3-vl-4b-instruct-c_abliterated-v2-mlx` | Router, vision, extraction, simple answers |
| `models.cloud` | `deepseek-v4-flash` | Complex reasoning (tool-augmented) |
| `models.embedding` | `text-embedding-nomic-embed-text-v1.5-embedding` | LTM vector embeddings |

**Changing models:** Edit only `defaults.yaml` (`models.small.model_name`, `models.cloud.model_name`). ConfigLoader centralizes all model name resolution via `get_small_model_name()` / `get_cloud_model_name()`.

### Key Routing Config (`defaults.yaml`)

```yaml
routing:
  confidence_threshold: 0.6         # HITL triggered below this
  skill_clarification_threshold: 0.5
  scope_clarification_enabled: true
  plan_review_enabled: true
  keyword_bypass: true
  hitl_enabled: true
  max_input_chars: 2000             # Router input truncation
  budget_tiers:
    - [40, 256]
    - [150, 512]
    - [400, 1536]
    - [800, 3072]
    - [1600, 4096]
```

### Environment Variable Overrides

| Env Var | Overrides |
|---------|-----------|
| `SMALL_LLM_BASE_URL` | `models.small.base_url` |
| `SMALL_LLM_MODEL_NAME` | `models.small.model_name` |
| `CLOUD_LLM_BASE_URL` | `models.cloud.base_url` |
| `CLOUD_LLM_MODEL_NAME` | `models.cloud.model_name` |
| `DEEPSEEK_API_KEY` | Cloud API key |

---

## Memory

### Three-Tier Architecture

| Tier | Storage | Retrieval |
|------|---------|-----------|
| **STM** | `data/memories.json` | Keyword search (recent 50 entries) |
| **LTM** | Qdrant via Mem0 | Semantic search (gated by router) |
| **Personal** | `data/topics.json`, `data/interests.json`, `data/conversations.json` | Time-decay-weighted relevance |
| **Scenarios** | `scenarios/*/playbook.md`, `constraints.md` | Router `scenario_id` + markdown loader |

### Injection Flow

```
memory_inject_lite → router → memory_retrieve → ...
```

- `memory_inject_lite`: Profile, persona, topics (no vector search). Cached 5 min.
- Router sets `needs_memory_retrieval` and optional `scenario_id`.
- `memory_retrieve`: Qdrant/Mem0 only when gated; loads scenario markdown.

### Write Flow (after agent responds)

1. PII-scrubs content
2. Enqueues custom extraction (Redis stream → worker → L1 atoms in Qdrant)
3. Extracts topics and updates topic/interests tracking
4. Records conversation in `conversations.json`
5. Invalidates memory cache for next turn

### Config

```yaml
memory:
  max_facts: 200
  search_window: 50
  cache:
    ttl: 300                  # 5 min
  decay:
    topic_half_life_days: 14
    interest_half_life_days: 21
  extraction:
    idle_cooldown_seconds: 8
    defer_while_graph_active: true
```

---

## Tools

### Toolbox Categories

| Toolbox | Tools |
|---------|-------|
| Always | `ask_user` |
| `web_search` | `web_search`, `fetch_webpage`, `deep_research` |
| `file_ops` | `read_workspace_file`, `write_workspace_file`, `edit_workspace_file`, `list_workspace_files`, `delete_workspace_file`, `download_to_workspace`, `upload_from_workspace` |
| `data_viz` | `create_docx`, `create_xlsx`, `create_pptx`, `create_pdf`, `notebook_run`, `notebook_reset`, `notebook_vars`, `read_ipynb`, `write_ipynb`, `export_ipynb_html`, `render_interactive_block` |
| `productivity` | `todo_add`, `todo_list`, `todo_complete`, `list_skills`, `invoke_skill`, `render_interactive_block` |
| `study` | `course_register`, `course_list`, `course_get`, `study_note_save`, `study_note_search`, `flashcard_deck_create`, `flashcard_review`, `quiz_session_start`, `quiz_session_answer`, `mastery_record`, `export_study_sheet` |
| `memory` | `recall_memories`, `recall_all_memories`, `forget_memory`, `search_workspace_docs` |

### Sensitive Tools (require HITL approval)

`write_workspace_file`, `edit_workspace_file`, `delete_workspace_file`, `notebook_run`

### Adding a New Tool

1. Create `@tool` function in `src/tools/<module>.py`
2. Register in `src/agent/tool_sets.py` (`ToolboxRegistry`)
3. Add to appropriate toolbox category
4. If sensitive, add to `SENSITIVE_TOOLS` in `src/agent/nodes/security_proxy.py`

---

## HITL (Human-in-the-Loop)

### Four HITL Gates

| Gate | File | Trigger |
|------|------|---------|
| Router HITL | `src/agent/routing/router.py` | LLM confidence < 60% or ambiguous skill match |
| Scope Clarify | `src/agent/nodes/scope_clarify.py` | Underspecified build/create requests |
| Plan Review | `src/agent/nodes/plan_review.py` | Sensitive tool plan before execution |
| Security Proxy | `src/agent/nodes/security_proxy.py` | Destructive/network tool calls |

### API Mode Behavior

- Interrupts disabled when `mode == "api"` or `execution_policy == "auto_approve"`
- Sensitive tools denied by default unless `auto_approve_sensitive: true`

### Known Issues

- **Confidence uncalibrated**: Always ~95%, does not reflect actual quality.
- **Refactoring false positive**: "write an improved version" triggers scope_clarify. Mitigated by `_REFACTOR_SIGNALS` in `src/agent/hitl/scope_heuristics.py`.

---

## Logging & Traces

Owlynn has a two-tier logging system.

### Tier 1: Audit Log (Metadata)

Structured JSON-lines capturing system-wide metadata — routing, model selection, HITL, memory, tools, timing. No user content.

**Output:** `~/.owlynn/logs/audit.jsonl` (5 × 10 MB rotating) and `audit-errors.jsonl` (3 × 5 MB rotating).

**CLI tool:**
```bash
python scripts/logcat.py --channel agent.model              # Model selection
python scripts/logcat.py --channel agent.hitl --level WARN   # HITL decisions
python scripts/logcat.py --channel memory.cache              # Cache hits/misses
python scripts/logcat.py --thread-id abc-123                 # Filter by thread
python scripts/logcat.py --follow                            # Live tail
python scripts/logcat.py --channel agent.model --follow      # Live model activity
```

**15 channels:** `agent.lifecycle`, `agent.model`, `agent.hitl`, `agent.tool`, `agent.token`, `agent.cloud`, `agent.coherence`, `memory.inject`, `memory.write`, `memory.cache`, `memory.ltm`, `memory.stm`, `memory.summarize`, `memory.topics`, `api.ws`, `api.file`, `system`

### Tier 2: Conversation Trace (Content)

Per-thread JSONL files capturing what happened in a conversation — user messages, router decisions, LLM responses, tool calls with I/O, errors, timing.

**Output:** `~/.owlynn/traces/{thread_id}.jsonl`

**CLI tool:**
```bash
python scripts/trace_view.py --list                          # List all traces
python scripts/trace_view.py --latest                        # View latest
python scripts/trace_view.py <thread_id>                     # View specific thread
python scripts/trace_view.py <thread_id> --json              # JSON output
python scripts/trace_view.py <thread_id> --follow            # Live tail
python scripts/trace_view.py <thread_id> --type router_decision,llm_response  # Filter
```

### Trace Event Types

| Type | When | Key Fields |
|------|------|------------|
| `turn_start` | Graph run begins | `ts` |
| `user_message` | User sends message | `content` (truncated 2000 chars) |
| `router_decision` | Router completes | `route`, `confidence`, `source`, `task_category`, `toolbox` |
| `llm_response` | LLM node completes | `node`, `model`, `content_preview`, `token_usage`, `fallback_chain` |
| `tool_call` | Tool completes | `tool_name`, `input`, `output`, `error`, `duration_s` |
| `coherence_check` | Coherence check | `coherent`, `confidence`, `reason`, `duration_ms` |
| `hitl_interrupt` | HITL fires | `interrupt_count` |
| `error` | Graph error | `message` |
| `turn_end` | Graph run ends | `ts` |

### IDE Agent Trace Patterns

```python
import json

with open("~/.owlynn/traces/{thread_id}.jsonl") as f:
    events = [json.loads(line) for line in f]

# Full timeline
for e in events:
    print(f"{e['ts']} [{e['type']}]")

# Routing decisions
[e for e in events if e["type"] == "router_decision"]

# What did the user ask?
[e for e in events if e["type"] == "user_message"]

# What did the LLM respond?
[e for e in events if e["type"] == "llm_response"]

# What tools failed?
[e for e in events if e["type"] == "tool_call" and e.get("error")]

# Errors
[e for e in events if e["type"] == "error"]
```

### Emitting Audit Events in Code

```python
from src.config.audit_log import audit_info, audit_debug, audit_warn

audit_info("agent.hitl", "tool_classified", tool="write_workspace_file", decision="sensitive")
audit_debug("memory.cache", "cache_hit", age_seconds=12)
audit_warn("agent.model", "swap_load_failed", variant="vision", error=str(e))
```

### Using @log_node Decorator

```python
from src.config.log_middleware import log_node

@log_node("complex_llm")
async def complex_llm_node(state: AgentState) -> AgentState:
    ...
```

---

## Debugging Recipes

### Wrong route (simple vs complex)

```bash
# Check what the router decided
python scripts/trace_view.py <thread_id> --type router_decision

# Check audit log for routing details
python scripts/logcat.py --channel agent.model --thread-id <thread_id>

# Look at classification_source in router_info WS event
# Source types: keyword_bypass, deterministic, llm_classifier, hitl
```

**Fix:** Check `src/agent/routing/router.py` for keyword bypass rules, or `defaults.yaml` `routing.confidence_threshold`.

### LM Studio not reachable

```bash
# Check if LM Studio is running
curl -s http://127.0.0.1:1234/v1/models | head -c 200

# Check model name matches exactly
python scripts/logcat.py --channel agent.model --level WARN
```

**Fix:** Open LM Studio, load the model. Model name in `defaults.yaml` must match what LM Studio reports at `/v1/models`.

### DeepSeek 401/403/429

```bash
# Check API key
python scripts/logcat.py --channel agent.model --level WARN

# Check circuit breaker
python scripts/logcat.py --channel agent.cloud
```

**Fix:** Set `DEEPSEEK_API_KEY` in `.env.local`. Circuit breaker triggers after 3 failures (60s cooldown). Config: `cloud.circuit_breaker`.

### Tool execution fails

```bash
# See tool calls and errors
python scripts/trace_view.py <thread_id> --type tool_call

# See tool classification (safe/sensitive)
python scripts/logcat.py --channel agent.hitl
```

**Fix:** Check tool implementation in `src/tools/`. Check `_tool_status_from_content` in `handler.py` for false error detection.

### HITL approval missing

```bash
# Check HITL decisions
python scripts/logcat.py --channel agent.hitl --thread-id <thread_id>

# Check if auto_approve is set
python scripts/logcat.py --channel agent.hitl --level WARN
```

**Fix:** If `execution_policy: auto_approve` in `data/user_profile.json`, all HITL is skipped. Check `src/agent/nodes/security_proxy.py` `SENSITIVE_TOOLS` list.

### Context overflow / summarization

```bash
# Check summarization triggers
python scripts/logcat.py --channel memory.summarize

# Check token usage in trace
python scripts/trace_view.py <thread_id> --type llm_response --json | \
  python -c "import sys,json; [print(e.get('token_usage',{})) for e in [json.loads(l) for l in sys.stdin]]"
```

**Fix:** Summarization triggers at 85% of context window (`summarization.threshold_ratio`). Config in `defaults.yaml`.

### Memory not injected

```bash
# Check memory injection
python scripts/logcat.py --channel memory.inject --thread-id <thread_id>

# Check cache
python scripts/logcat.py --channel memory.cache

# Check extraction
python scripts/logcat.py --channel memory.stm
```

**Fix:** Memory injection gated by router (`needs_memory_retrieval`). Cache TTL is 5 min. Check Redis/Qdrant are running.

### Slow responses

```bash
# Check model fallbacks
python scripts/logcat.py --channel agent.model --level WARN

# Check tool durations
python scripts/trace_view.py <thread_id> --type tool_call --json | \
  python -c "import sys,json; [print(f\"{e['tool_name']}: {e.get('duration_s','?')}s\") for e in [json.loads(l) for l in sys.stdin]]"

# Check coherence retries
python scripts/logcat.py --channel agent.coherence
```

**Fix:** Cloud fallback adds latency. Coherence retries add extra LLM calls. Check `defaults.yaml` timeouts.

### Infinite agent loop

```bash
# Check recursion
python scripts/logcat.py --channel agent.lifecycle --thread-id <thread_id>
```

**Fix:** `complex.recursion_limit` defaults to 100 in `defaults.yaml`. Tool-calling cycles can hit this. Check edge conditions in `src/agent/core/graph.py`.

### Frontend blank / WS desync

```bash
# Check WS connection
python scripts/logcat.py --channel api.ws

# Check for WS errors
python scripts/logcat.py --channel api.ws --level WARN
```

**Fix:** Check `frontend-v2/src/lib/wsClient.ts` for reconnection logic. Check `frontend-v2/src/App.tsx` for error boundaries.

### Cloud fallback triggered unexpectedly

```bash
# Check cloud availability
python scripts/logcat.py --channel agent.model | grep -i cloud

# Check circuit breaker
python scripts/logcat.py --channel agent.cloud
```

**Fix:** `_check_cloud_available()` checks: `cloud_escalation_enabled` in profile, circuit breaker state, API key presence. Check `data/user_profile.json` `cloud_escalation_enabled`.

### WebSocket crash (transfer_data_task)

**Symptom:** `AttributeError: 'WebSocketProtocol' object has no attribute 'transfer_data_task'`

**Cause:** websockets 15+ / uvicorn race condition. Client disconnects before `connection_open()` sets `transfer_data_task`.

**Fix:** Already fixed in `src/api/ws/handler.py` — catches `AttributeError` alongside `RuntimeError` in WebSocket close handler.

---

## Known Gotchas

1. **Model name must match exactly** — `defaults.yaml` / `.env` must be identical to what LM Studio reports at `/v1/models`.

2. **Redis unavailable = in-memory fallback** — LangGraph falls back to `MemorySaver`; session persistence lost.

3. **Port conflicts** — Kill stale: `lsof -ti:8000 | xargs kill -9` and `lsof -ti:5173 | xargs kill -9`.

4. **PYTHONPATH must be set** — `start.sh` does this. Manual: `export PYTHONPATH="$(pwd):$PYTHONPATH"`.

5. **Confidence uncalibrated** — Router confidence always ~95%, does not reflect actual quality.

6. **No self-awareness** — System never detects wrong answers.

7. **Memory context cap** — Injected memory text capped at 12,000 chars in `format_memory_context`.

8. **StirlingPDF needs 2GB RAM** — 1GB causes Metaspace OOM. Falls back to PyMuPDF automatically.

9. **Background extraction defers** — LTM atom extraction waits 8s idle cooldown to avoid GPU contention on Apple Silicon.

10. **Cloud circuit breaker** — 3 failures triggers 60s cooldown.

11. **Security proxy danger patterns** — Scans for `rm -rf`, `sudo`, `curl`, `ssh`; legitimate commands may match.

12. **API mode HITL skip** — When `mode == "api"`, all interrupts disabled.

13. **Recursion limit** — Default 100. Tool-calling cycles can hit this.

14. **Mem0 requires NLP deps** — `pip install mem0ai[nlp]` for spaCy/fastembed.

15. **E2B model leak** — Backend warmup auto-loads E2B if it's the default in LM Studio. Workaround: unload E2B before starting backend.

---

## Commands Reference

### CI & Testing

```bash
./scripts/ci.sh --quick                    # Ruff, mypy, pytest, vitest
./scripts/ci.sh                            # Above + frontend build
./scripts/ci.sh --network                  # Live DeepSeek tests
./scripts/ci.sh --benchmarks               # Router/complex/memory benchmarks
```

### Key Test Suites

```bash
pytest tests/test_router_properties.py tests/test_router_web_intent.py -q
pytest tests/test_toolbox_registry.py -q
pytest tests/test_websocket_event_contract.py -q
pytest tests/test_memory_nodes.py tests/test_crud_operations.py -q
pytest tests/test_llm_pool.py -q
pytest tests/test_graph.py -q
pytest tests/test_audit_log.py -q
```

### Evaluations

```bash
python scripts/run_local_frontier_eval.py  # ~19-turn mechanical eval
python scripts/run_educator_eval.py        # 8-turn educator eval
python scripts/run_browser_eval.py         # 12-turn conversation eval
```

### Format & Lint

```bash
ruff check .                # Python lint
ruff format .               # Python format
cd frontend-v2 && npm run lint    # TS/JS lint
cd frontend-v2 && npm run format  # TS/JS format
```

### Logs & Traces

```bash
python scripts/logcat.py --channel agent.model --follow
python scripts/trace_view.py --latest
python scripts/trace_view.py <thread_id> --json
```

### Config Validation

```bash
python3 -c "from src.config.config_loader import validate_config; print(validate_config())"
```

---

## File Map

### By Task

| I want to… | File(s) |
|------------|---------|
| Change routing / model selection | `src/config/defaults.yaml` (models section), `src/agent/routing/router.py`, `src/agent/routing/classifier.py` |
| Add or change a tool | `src/tools/`, `src/agent/tool_sets.py` |
| Fix memory / context injection | `src/agent/nodes/memory.py`, `src/memory/` |
| Change HITL / approvals | `src/agent/hitl/`, `src/agent/nodes/security_proxy.py`, `src/agent/nodes/scope_clarify.py`, `src/agent/nodes/plan_review.py` |
| Debug a symptom | `docs/debugging/README.md` → symptom table |
| Change cloud / anonymization | `src/agent/core/complex.py`, `src/agent/core/complex_utils/` |
| Run the app | `start.sh`, `setup.sh`, `.env` |
| Run CI / tests / evals | `scripts/ci.sh`, `scripts/run_*_eval.py` |
| View logs | `scripts/logcat.py`, `scripts/trace_view.py` |
| Change config | `src/config/defaults.yaml` (single source of truth) |
| Change WebSocket events | `src/api/ws/handler.py`, `src/api/ws/schemas.py`, `frontend-v2/src/` |
