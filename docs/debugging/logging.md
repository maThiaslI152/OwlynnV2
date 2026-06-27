---
status: active
category: debugging
last_updated: 2026-05-31
owner: human
---

# Owlynn Structured Debug Logging

> **Purpose:** Debugging guide for the audit logging system.


## Architecture Overview

Owlynn uses a **channel-based structured audit logging** system that emits
JSON-lines to both stdout (human-readable) and rotating files (machine-readable).

### Core Components

| Module | Purpose |
|---|---|
| `src/config/audit_log.py` | Structured JSON-line logging with context propagation |
| `src/config/logging_config.py` | Startup wiring: stdout handler + rotating file output |
| `src/config/log_middleware.py` | Decorators (`@log_node`), helpers (`log_model_attempt`, `log_hitl_event`), ASGI middleware |
| `scripts/logcat.py` | CLI tail/filter tool for audit logs |
| `src/memory/user_profile.py` | Profile settings: `audit_log_enabled`, `audit_log_levels`, `audit_log_dir` |

### Dual Output

- **stdout**: Compact JSON lines visible in the terminal alongside application logs
- **Rotating files** in `~/.owlynn/logs/`:
  - `audit.jsonl` — all channel events (5 x 10 MB rotation)
  - `audit-errors.jsonl` — ERROR+ only (3 x 5 MB rotation)

### Context Propagation

Enrichment context (thread_id, node, route, model) propagates automatically via
`contextvars.ContextVar`, set at the top of graph execution and ASGI requests.
All `audit_event()` calls auto-read the current context — no manual threading
needed.

---

## Channel Reference

| Channel | Description | Default Level | Sample Events |
|---|---|---|---|
| `agent.lifecycle` | Node entry/exit, graph routing edges | DEBUG | `node_entry`, `node_exit`, `node_error`, `edge_traversal` |
| `agent.model` | Model selection, fallback, swap, load/unload | INFO | `model_attempt`, `pool_instance_created`, `pool_cache_hit`, `swap_begin`, `swap_complete` |
| `agent.hitl` | Security proxy, plan review, scope clarification | INFO | `tool_classified`, `hitl_interrupt`, `hitl_approved`, `hitl_denied`, `plan_reviewed`, `scope_clarified` |
| `agent.tool` | Tool invocation, duration, success/error | INFO | `tool_start`, `tool_end` |
| `agent.token` | Budget allocation, summarization, tracking | DEBUG | `budget_computed` |
| `memory.inject` | Mem0 search, context assembly, cache hits | DEBUG | `context_from_cache`, `context_assembled` |
| `memory.write` | Fact extraction, dedup, save to Mem0/STM | INFO | `gate_skipped`, `dedup_skip`, `mem0_saved` |
| `memory.cache` | TTL cache hit/miss/invalidate | DEBUG | `cache_hit`, `cache_miss`, `cache_invalidated` |
| `memory.ltm` | Mem0/Qdrant add/search/delete/clear, init | INFO | `mem0_init`, `mem0_init_failed` |
| `memory.stm` | STM (memories.json) save/load/delete/cap | INFO | `saved`, `searched`, `deleted`, `cleared` |
| `memory.summarize` | Summarization trigger, tokens freed, fallback | INFO | `triggered`, `split_result`, `compression_complete`, `llm_failed` |
| `memory.topics` | Topic extraction, interest tracking, decay | DEBUG | `topic_extracted`, `topic_updated`, `interest_extracted`, `interest_updated`, `conversation_recorded` |
| `api.ws` | WebSocket connect/disconnect/events | INFO | `ws_connected`, `ws_disconnected`, `http_request` |
| `api.file` | File upload, watcher, processing | INFO | `file_uploaded`, `file_upload_failed` |
| `system` | Startup, shutdown, config changes | INFO | _(reserved for future use)_ |

---

## Usage Patterns

### Emitting Events in Nodes

```python
from src.config.audit_log import audit_event, audit_debug, audit_info, audit_warn

# Simple info event
audit_info("agent.hitl", "tool_classified", tool="write_workspace_file", decision="sensitive")

# Debug event (only emitted when channel level is DEBUG)
audit_debug("memory.cache", "cache_hit", age_seconds=12)

# Warning event
audit_warn("agent.model", "swap_load_failed", variant="vision", error=str(e))

# Generic event with explicit level
audit_event("agent.tool", "tool_end", level=logging.INFO, duration_ms=334, status="success")
```

### Using the @log_node Decorator

Wraps a LangGraph node function (sync or async), auto-logging entry/exit:

```python
from src.config.log_middleware import log_node

@log_node("complex_llm")
async def complex_llm_node(state: AgentState) -> AgentState:
    ...
```

### Using Model Attempt Logging

```python
from src.config.log_middleware import log_model_attempt

log_model_attempt("large-cloud", "success", reason="initial_route")
log_model_attempt("complex-cloud", "failed", reason="auth_error_401_403")
```

### Using HITL Logging

```python
from src.config.log_middleware import log_hitl_event

log_hitl_event("tool_classified", tool="write_workspace_file", decision="sensitive")
log_hitl_event("hitl_approved", decision="approved", tools=["write_workspace_file"])
log_hitl_event("scope_clarified", decision="answered", dimensions=["language", "ui_surface"])
```

### Injection Context

```python
from src.config.audit_log import audit_context

with audit_context(thread_id="abc-123", node="router"):
    audit_event("agent.lifecycle", "decision", route="complex-default")
```

---

## Profile Settings

Configured in `data/user_profile.json` or via the settings UI:

```json
{
  "audit_log_enabled": true,
  "audit_log_levels": {
    "agent.lifecycle": "DEBUG",
    "agent.model": "INFO",
    "agent.hitl": "INFO",
    "agent.tool": "INFO",
    "agent.token": "DEBUG",
    "memory.inject": "DEBUG",
    "memory.write": "INFO",
    "memory.cache": "DEBUG",
    "memory.ltm": "INFO",
    "memory.stm": "INFO",
    "memory.summarize": "INFO",
    "memory.topics": "DEBUG",
    "api.ws": "INFO",
    "api.file": "INFO",
    "system": "INFO"
  },
  "audit_log_dir": "~/.owlynn/logs/"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `audit_log_enabled` | bool | `true` | Enable/disable audit file logging |
| `audit_log_levels` | dict | _(all INFO)_ | Per-channel log levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `audit_log_dir` | str | `~/.owlynn/logs/` | Directory for rotating log files |

### Environment Variable Overrides

- `OWLYNN_AUDIT_LOG_ENABLED=0` — disable audit file logging (useful in CI/tests)
- `OWLYNN_AUDIT_LOG_DIR=""` — disable file output entirely
- `OWLYNN_AUDIT_LOG_DIR=/custom/path` — override log directory

---

## Logcat CLI Reference

```bash
# Filter by channel (exact match)
python scripts/logcat.py --channel agent.model

# Filter by channel prefix (matches all memory sub-channels)
python scripts/logcat.py --channel memory

# Multi-channel filter
python scripts/logcat.py --channel memory.cache,memory.ltm

# Filter by log level
python scripts/logcat.py --channel agent.hitl --level WARN

# Filter by thread ID
python scripts/logcat.py --thread-id abc-123

# Live tailing (like tail -f)
python scripts/logcat.py --follow

# Combine filters with live tailing
python scripts/logcat.py --channel agent.model --level INFO --follow

# Custom log directory
python scripts/logcat.py --log-dir /tmp/owlynn-logs

# Disable colour output
python scripts/logcat.py --no-color
```

---

## Common Debugging Recipes

### Finding Model Fallback Chains

```bash
# See all model selection and fallback activity
python scripts/logcat.py --channel agent.model

# Watch for model failures in real-time
python scripts/logcat.py --channel agent.model --level WARN --follow
```

### Tracing HITL Decisions

```bash
# See all security proxy and plan review activity
python scripts/logcat.py --channel agent.hitl

# Track a specific thread's HITL path
python scripts/logcat.py --channel agent.hitl --thread-id abc-123
```

### Debugging Memory Cache Misses

```bash
# See cache hit/miss/invalidation
python scripts/logcat.py --channel memory.cache

# See full memory injection pipeline
python scripts/logcat.py --channel memory.inject --channel memory.cache --follow
```

### Auditing Tool Execution

```bash
# See tool lifecycle events
python scripts/logcat.py --channel agent.tool --follow
```

### Monitoring STM Operations

```bash
# See saves, searches, deletes
python scripts/logcat.py --channel memory.stm
```

---

## File Rotation

- **audit.jsonl**: 5 backup files x 10 MB each = 60 MB max
- **audit-errors.jsonl**: 3 backup files x 5 MB each = 20 MB max
- Files rotate automatically when they reach the size limit
- Old files are named `audit.jsonl.1`, `audit.jsonl.2`, etc.

---

## Adding New Channels

1. Add the channel string to `CHANNELS` in `src/config/audit_log.py`
2. Add a default level in `_DEFAULT_CHANNEL_LEVELS`
3. Add the setting to `audit_log_levels` in `_DEFAULTS` in `src/memory/user_profile.py`
4. Add the field type to `VALID_FIELDS` (already present if pattern matches)
5. Document in this file's channel reference table
6. Add a sample log line to the plan reference if applicable

## Related

- [`docs/debugging/README.md`](README.md) — debugging index

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
