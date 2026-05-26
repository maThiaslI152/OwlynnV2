# Audit Logging System — Implementation Summary

**Completed**: 2026-05-27
**Plan**: `owlynn-logging-system` (`.cursor/plans/owlynn-logging-system_e999dbc9.plan.md`)

## What Was Built

A **channel-based structured audit logging system** that replaces ad-hoc `logger.info/warning/error` calls across the Owlynn codebase with a unified, machine-readable JSON-lines format. The system covers agent lifecycles, model selection, HITL approvals, tool execution, memory operations, and API events.

## Files Created

| File | Purpose |
|------|---------|
| `src/config/audit_log.py` | Core structured JSON-line logging with 15 channels, context propagation via `contextvars`, per-channel level filtering, rotating file output |
| `src/config/log_middleware.py` | `@log_node` decorator (sync/async), `log_model_attempt()`, `log_hitl_event()`, `AuditLogMiddleware` ASGI middleware |
| `scripts/logcat.py` | CLI for tailing/filtering audit logs by channel, thread ID, and level |
| `docs/debugging/logging.md` | Full developer reference: architecture, channel table, usage patterns, profile settings, logcat CLI, debugging recipes |
| `tests/test_audit_log.py` | 33 unit tests covering emission, level gating, context enrichment, sanitization, decorators, helpers |
| `tests/conftest.py` | Global fixture disabling audit file output for all tests |

## Files Modified

All 10 LangGraph nodes decorated with `@log_node` (entry/exit/duration/error events):

| Node | File |
|------|------|
| `memory_inject` | `src/agent/nodes/memory.py` |
| `auto_summarize` | `src/agent/nodes/summarize.py` |
| `router` | `src/agent/nodes/router.py` |
| `simple` | `src/agent/nodes/simple.py` |
| `scope_clarify` | `src/agent/nodes/scope_clarify.py` |
| `complex_llm` | `src/agent/nodes/complex.py` |
| `plan_review` | `src/agent/nodes/plan_review.py` |
| `security_proxy` | `src/agent/nodes/security_proxy.py` |
| `tool_action` | `src/agent/nodes/complex.py` |
| `memory_write` | `src/agent/nodes/memory.py` |

Subsystem audit logging added to:

| Subsystem | File | Key Events |
|-----------|------|------------|
| Graph edges | `src/agent/graph.py` | `edge_traversal` for all conditional edges |
| Router | `src/agent/nodes/router.py` | `router_decision`, `router_hitl_interrupt`, `router_hitl_resolved`, `router_cloud_downgrade`, `router_skill_toolbox_override` |
| Model pool | `src/agent/llm.py` | `pool_instance_created`, `pool_cache_hit`, `pool_test_override`, `pool_no_api_key` |
| Swap manager | `src/agent/swap_manager.py` | `swap_begin`, `swap_complete`, `swap_load_failed`, `swap_poll_timeout`, `swap_unloaded` |
| STM (memories.json) | `src/memory/memory_manager.py` | `saved`, `searched`, `deleted`, `cleared`, `save_skipped_duplicate` |
| Personal assistant | `src/memory/personal_assistant.py` | `topic_extracted`, `topic_updated`, `interest_extracted`, `interest_updated`, `conversation_recorded` |
| API server | `src/api/server.py` | `ws_connected`, `ws_disconnected`, `file_uploaded`, `file_upload_failed`, ASGI HTTP request logging |

## Audit Channels (15 Total)

| Channel | Description | Default Level |
|---------|-------------|:---:|
| `agent.lifecycle` | Node entry/exit, graph routing edges | DEBUG |
| `agent.model` | Model selection, fallback, swap | INFO |
| `agent.hitl` | Security proxy, plan review, scope clarification | INFO |
| `agent.tool` | Tool invocation, duration, success/error | INFO |
| `agent.token` | Budget allocation, summarization, tracking | DEBUG |
| `memory.inject` | Mem0 search, context assembly, cache hits | DEBUG |
| `memory.write` | Fact extraction, dedup, save to Mem0/STM | INFO |
| `memory.cache` | TTL cache hit/miss/invalidate | DEBUG |
| `memory.ltm` | Mem0/Qdrant init, add/search/delete/clear | INFO |
| `memory.stm` | STM (memories.json) save/load/delete/cap | INFO |
| `memory.summarize` | Summarization trigger, tokens freed, fallback | INFO |
| `memory.topics` | Topic extraction, interest tracking, decay | DEBUG |
| `api.ws` | WebSocket connect/disconnect/events | INFO |
| `api.file` | File upload, processing | INFO |
| `system` | Startup, shutdown, config changes | INFO |

## Configuration

Per-channel levels are runtime-configurable via user profile (`data/user_profile.json`):

```json
{
  "audit_log_enabled": true,
  "audit_log_levels": { "agent.model": "INFO", ... },
  "audit_log_dir": "~/.owlynn/logs/"
}
```

Environment variable overrides: `OWLYNN_AUDIT_LOG_ENABLED=0`, `OWLYNN_AUDIT_LOG_DIR=""`.

## Test Results

- **33/33** new audit log unit tests pass
- **234/234** existing tests pass across all affected subsystems
- **Zero regressions** in graph, routing, HITL, memory, summarization, swap, LLM pool, and properties tests

## Usage Quick Start

```bash
# Tail all model-related events
python scripts/logcat.py --channel agent.model --follow

# Filter HITL warnings
python scripts/logcat.py --channel agent.hitl --level WARN

# Trace a specific conversation thread
python scripts/logcat.py --thread-id abc-123 --follow

# Monitor memory subsystem
python scripts/logcat.py --channel memory --follow
```
