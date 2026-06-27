---
status: active
category: debugging
last_updated: 2026-06-27
owner: human
---

# Owlynn Logging & Observability

> **Purpose:** Complete reference for Owlynn's two-tier logging system — structured audit logs (metadata) and per-conversation traces (content).

## Quick Reference

| What you need | Tool | Command |
|---|---|---|
| See model routing decisions | `logcat.py` | `python scripts/logcat.py --channel agent.model` |
| See what happened in a conversation | `trace_view.py` | `python scripts/trace_view.py --latest` |
| Live tail all audit events | `logcat.py` | `python scripts/logcat.py --follow` |
| Live tail a specific conversation | `trace_view.py` | `python scripts/trace_view.py <thread_id> --follow` |
| Get machine-readable output for IDE | `trace_view.py` | `python scripts/trace_view.py <thread_id> --json` |

---

## Architecture Overview

Owlynn has a two-tier logging architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                     Owlynn Backend                          │
│                                                             │
│  GraphSession._execute()                                    │
│      │                                                      │
│      ├─→ astream_events ──→ WS forwarder ──→ frontend       │
│      │                                                      │
│      ├─→ audit_log ──→ stdout + ~/.owlynn/logs/audit.jsonl  │
│      │                                                      │
│      └─→ trace_listener ──→ ~/.owlynn/traces/{thread}.jsonl │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Tier 1: Audit Log (Metadata)

Structured JSON-lines capturing **what the system did** — routing decisions, model selections, HITL triggers, memory operations, tool classifications, timing. No user content or LLM responses.

### Tier 2: Conversation Trace (Content)

Per-thread JSONL files capturing **what happened in a conversation** — user messages, router decisions, LLM responses (previews), tool calls with I/O, errors, timing. Designed for IDE agent diagnosis.

### Why Two Tiers?

| | Audit Log | Conversation Trace |
|---|---|---|
| **Granularity** | System-wide | Per-thread |
| **Content** | Metadata only | User input + LLM output + tool I/O |
| **Format** | Single rotating file | Per-thread JSONL |
| **Audience** | Operators, monitoring | IDE agents, debugging |
| **Retention** | 5 × 10 MB rotating | Per-thread (manual cleanup) |
| **Query** | `logcat.py --channel` | `trace_view.py <thread_id>` |

---

## Tier 1: Audit Log

### Core Modules

| Module | Purpose |
|---|---|
| `src/config/audit_log.py` | Structured JSON-line logging with context propagation |
| `src/config/logging_config.py` | Startup wiring: stdout handler + rotating file output |
| `src/config/log_middleware.py` | `@log_node` decorator, `log_model_attempt()`, `log_hitl_event()`, `AuditLogMiddleware` |
| `scripts/logcat.py` | CLI tail/filter tool |

### Output Locations

- **stdout**: Compact JSON lines in the terminal (alongside app logs)
- **Rotating files** in `~/.owlynn/logs/`:
  - `audit.jsonl` — all events (5 × 10 MB rotation, ~60 MB max)
  - `audit-errors.jsonl` — WARNING+ only (3 × 5 MB rotation, ~20 MB max)

### Context Propagation

Enrichment context (`thread_id`, `node`, `route`, `model`) propagates automatically via `contextvars.ContextVar`. Set at graph entry and ASGI request start. All `audit_event()` calls auto-inject the current context.

### Channel Reference

| Channel | Description | Default Level | Key Events |
|---|---|---|---|
| `agent.lifecycle` | Node entry/exit, graph edges | DEBUG | `node_entry`, `node_exit`, `node_error`, `edge_traversal` |
| `agent.model` | Model selection, fallback, swap | INFO | `model_attempt`, `pool_instance_created`, `pool_cache_hit`, `swap_begin` |
| `agent.hitl` | Security proxy, plan review, scope clarify | INFO | `tool_classified`, `hitl_interrupt`, `hitl_approved`, `hitl_denied`, `plan_reviewed` |
| `agent.tool` | Tool invocation | INFO | `tool_start`, `tool_end` |
| `agent.token` | Budget allocation | DEBUG | `budget_computed` |
| `agent.cloud` | Cloud payload, cost tracking | DEBUG | `brief_applied`, `cache_usage` |
| `agent.coherence` | Coherence retry | INFO | `retry_failed`, `retry_completed` |
| `memory.inject` | Context assembly | DEBUG | `lite_context_assembled`, `context_assembled` |
| `memory.write` | Fact extraction, dedup | INFO | `gate_skipped`, `extract_queued`, `mem0_saved` |
| `memory.cache` | TTL cache | DEBUG | `cache_hit`, `cache_miss`, `cache_invalidated` |
| `memory.ltm` | Mem0/Qdrant operations | INFO | `mem0_init`, `mem0_init_failed` |
| `memory.stm` | Short-term memory | INFO | `saved`, `searched`, `deleted`, `cleared` |
| `memory.summarize` | Auto-summarization | INFO | `triggered`, `split_result`, `compression_complete` |
| `memory.topics` | Topic extraction | DEBUG | `topic_extracted`, `topic_updated`, `interest_extracted` |
| `api.ws` | WebSocket + HTTP | INFO | `ws_connected`, `ws_disconnected`, `http_request` |
| `api.file` | File upload | INFO | `file_uploaded`, `file_upload_failed` |
| `system` | Startup/shutdown | INFO | _(reserved)_ |

### Logcat CLI

```bash
# Filter by channel
python scripts/logcat.py --channel agent.model
python scripts/logcat.py --channel memory          # prefix match (all memory.*)

# Multi-channel
python scripts/logcat.py --channel memory.cache,memory.ltm

# Filter by level
python scripts/logcat.py --channel agent.hitl --level WARN

# Filter by thread
python scripts/logcat.py --thread-id abc-123

# Live tail
python scripts/logcat.py --follow
python scripts/logcat.py --channel agent.model --level INFO --follow

# Custom directory
python scripts/logcat.py --log-dir /tmp/owlynn-logs

# Disable color
python scripts/logcat.py --no-color
```

### Profile Settings

In `data/user_profile.json`:

```json
{
  "audit_log_enabled": true,
  "audit_log_levels": {
    "agent.lifecycle": "DEBUG",
    "agent.model": "INFO",
    "memory.cache": "DEBUG"
  },
  "audit_log_dir": "~/.owlynn/logs/"
}
```

### Environment Variables

| Variable | Effect |
|---|---|
| `OWLYNN_DEBUG=1` | Set app logger to DEBUG (via `start.sh --debug`) |
| `OWLYNN_AUDIT_LOG_ENABLED=0` | Disable audit file output |
| `OWLYNN_AUDIT_LOG_DIR=""` | Disable file output (empty string) |
| `OWLYNN_AUDIT_LOG_DIR=/path` | Custom log directory |

### Config (defaults.yaml)

```yaml
audit:
  max_bytes: 10485760          # 10 MB per audit.jsonl rotation
  backup_count: 5              # Keep 5 rotated files
  error_max_bytes: 5242880     # 5 MB per audit-errors.jsonl rotation
  error_backup_count: 3        # Keep 3 rotated files
  sanitize_max_len: 500        # Truncate strings > 500 chars in JSON
```

### Adding New Channels

1. Add channel string to `CHANNELS` in `src/config/audit_log.py`
2. Add default level in `_DEFAULT_CHANNEL_LEVELS`
3. Add to `audit_log_levels` in `_DEFAULTS` in `src/memory/user_profile.py`
4. Document in this file's channel reference table

---

## Tier 2: Conversation Trace

### Core Modules

| Module | Purpose |
|---|---|
| `src/config/trace_writer.py` | `TraceWriter` class + `trace_listener` coroutine |
| `src/api/ws/handler.py` | Registers trace listener, writes user messages |
| `scripts/trace_view.py` | CLI viewer for trace files |

### How It Works

The `TraceWriter` subscribes to the same `astream_events` queue as the WebSocket forwarder. It interprets raw LangGraph events into structured trace records and writes them to per-thread JSONL files.

```
GraphSession._execute()
    │
    ├─ astream_events() ──→ WS forwarder → frontend
    │
    └─ astream_events() ──→ trace_listener → ~/.owlynn/traces/{thread_id}.jsonl
```

### Output Location

`~/.owlynn/traces/{thread_id}.jsonl` — one file per conversation thread.

### Trace Event Types

| Type | When | Key Fields |
|---|---|---|
| `turn_start` | Graph run begins | `ts` |
| `user_message` | User sends a message | `content` (truncated to 2000 chars) |
| `router_decision` | Router node completes | `route`, `confidence`, `source`, `task_category`, `toolbox` |
| `llm_response` | LLM node completes | `node`, `model`, `content_preview`, `has_tool_calls`, `tool_call_count`, `token_usage`, `fallback_chain` |
| `tool_call` | Tool execution completes | `tool_name`, `input`, `output`, `error`, `duration_s` |
| `coherence_check` | Coherence check completes | `coherent`, `confidence`, `reason`, `duration_ms` |
| `hitl_interrupt` | HITL interrupt fires | `interrupt_count` |
| `error` | Graph execution error | `message` |
| `turn_end` | Graph run completes | `ts` |
| `trace_session_end` | WS disconnects | `ts` |

### Trace Record Format

Each line is a JSON object:

```json
{
  "ts": "2026-06-27T15:22:34.106+00:00",
  "thread_id": "thread-abc-123",
  "type": "router_decision",
  "route": "complex-cloud",
  "confidence": 0.95,
  "source": "llm_classifier",
  "task_category": "web_search",
  "toolbox": "web_search"
}
```

### Trace View CLI

```bash
# List all traces
python scripts/trace_view.py --list

# View the latest trace
python scripts/trace_view.py --latest

# View a specific thread
python scripts/trace_view.py thread-abc-123

# Filter by event type
python scripts/trace_view.py thread-abc-123 --type router_decision,llm_response

# JSON output (for IDE agents)
python scripts/trace_view.py thread-abc-123 --json

# Live tail
python scripts/trace_view.py thread-abc-123 --follow

# Custom trace directory
python scripts/trace_view.py --trace-dir /tmp/traces --list

# Disable color
python scripts/trace_view.py --latest --no-color
```

### IDE Agent Usage

```python
import json

# Read a conversation trace
with open("~/.owlynn/traces/{thread_id}.jsonl") as f:
    events = [json.loads(line) for line in f]

# Full timeline
for e in events:
    print(f"{e['ts']} [{e['type']}]")

# Routing decisions
router_events = [e for e in events if e["type"] == "router_decision"]

# What did the user ask?
user_msgs = [e for e in events if e["type"] == "user_message"]

# What did the LLM respond?
llm_responses = [e for e in events if e["type"] == "llm_response"]

# What tools failed?
tool_errors = [e for e in events if e["type"] == "tool_call" and e.get("error")]

# Full tool I/O
tool_calls = [e for e in events if e["type"] == "tool_call"]

# Errors
errors = [e for e in events if e["type"] == "error"]

# Turn timing
turns = [e for e in events if e["type"] in ("turn_start", "turn_end")]
```

### Config (defaults.yaml)

```yaml
trace:
  output_dir: "~/.owlynn/traces"
```

---

## Common Debugging Recipes

### "What happened in the last conversation?"

```bash
python scripts/trace_view.py --latest
```

### "Why did the router choose complex-cloud?"

```bash
# From audit log (system-wide)
python scripts/logcat.py --channel agent.model

# From trace (specific conversation)
python scripts/trace_view.py <thread_id> --type router_decision
```

### "What tools were called and what did they return?"

```bash
python scripts/trace_view.py <thread_id> --type tool_call
```

### "What did the LLM see?"

```bash
python scripts/trace_view.py <thread_id> --type user_message,llm_response
```

### "Why did the response take 30 seconds?"

```bash
# Check model fallbacks
python scripts/logcat.py --channel agent.model --level WARN

# Check tool durations in trace
python scripts/trace_view.py <thread_id> --type tool_call --json | \
  python -c "import sys,json; [print(f\"{e['tool_name']}: {e.get('duration_s','?')}s\") for e in [json.loads(l) for l in sys.stdin]]"
```

### "What HITL decisions were made?"

```bash
python scripts/logcat.py --channel agent.hitl --thread-id <thread_id>
python scripts/trace_view.py <thread_id> --type hitl_interrupt
```

### "Memory cache misses?"

```bash
python scripts/logcat.py --channel memory.cache
python scripts/logcat.py --channel memory.inject --channel memory.cache --follow
```

### "Cloud cost tracking?"

```bash
python scripts/logcat.py --channel agent.cloud
```

---

## Logcat vs Trace View

| | `logcat.py` | `trace_view.py` |
|---|---|---|
| **Data source** | `~/.owlynn/logs/audit.jsonl` | `~/.owlynn/traces/{thread}.jsonl` |
| **Scope** | System-wide, all threads | Single conversation thread |
| **Content** | Metadata (no user/LLM text) | User input + LLM output + tool I/O |
| **Filter** | `--channel`, `--level`, `--thread-id` | `--type`, `--json` |
| **Use case** | Monitor system behavior | Debug a specific conversation |
| **Audience** | Operators, CI | IDE agents, developers |

---

## File Rotation

### Audit Log

- `audit.jsonl`: 5 × 10 MB = ~60 MB max
- `audit-errors.jsonl`: 3 × 5 MB = ~20 MB max
- Old files: `audit.jsonl.1`, `audit.jsonl.2`, etc.

### Conversation Traces

- One file per thread, no automatic rotation
- Manual cleanup: `rm ~/.owlynn/traces/old-thread-*.jsonl`
- Consider periodic archival for long-running deployments

---

## Related

- [`docs/debugging/README.md`](README.md) — symptom-to-file debugging index
- [`docs/debugging/agent-graph.md`](agent-graph.md) — LangGraph node flow
- [`docs/CHAT_PROTOCOL.md`](../CHAT_PROTOCOL.md) — WebSocket event types

## Last updated

2026-06-27 — Added conversation trace system (Tier 2)
