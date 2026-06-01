---
status: active
category: debugging
last_updated: 2026-05-31
owner: human
---

# System Integration Test — 2026-05-27

> **Purpose:** System integration test results from 2026-05-27.


## Test Prompt Used

```
Compare Python FastAPI vs Express.js for building REST APIs with the following criteria:
- Performance under 1000+ concurrent users
- Type safety and developer experience
- Ecosystem and middleware support
- Learning curve

Please:
1. Create a structured comparison table
2. Visualize the comparison as a mermaid diagram (bar chart or decision tree)
3. Write the full comparison results to a file called `comparison.md` in the workspace
4. Note which one you'd recommend for a project with 1000+ concurrent users that prioritizes type safety
5. Search the web for any recent benchmarks that support your recommendation
6. Remember that I strongly prefer type-safe languages and frameworks

Be thorough and provide concrete data points where possible.
```

## Server Configuration

- Backend already running on `127.0.0.1:8000` (pid 14497)
- `OWLYNN_DEV=1` mode: **not enabled** during test (server was started without it)
- Logging: wired via `setup_logging()` in FastAPI lifespan
- AuditLogMiddleware: attached
- Thread ID: `integration-test-2026-05-27`

## Observed Flow

### Node Execution Path (from audit log)

```
router
  → scope_clarify (heuristic_passed — skipped, 0.23ms)
    → complex_llm (LLM generation with tool_calls, 33741ms)
      → security_proxy (web_search classified "safe", 0.52ms)
        → tool_action (web_search executed, 3509ms)
          → complex_llm (second pass — NO tool_calls emitted, 70618ms)
            → security_proxy (no tools to classify, execution_approved=false, 0.04ms)
              → memory_write (fact extraction + Mem0 save, 349ms)
```

### Router Decision

```json
{
  "route": "complex-default",
  "confidence": 0.9,
  "reasoning": "web_intent_detected",
  "swap_decision": "not_needed",
  "classification_source": "deterministic",
  "token_budget": 1536,
  "cloud_available": false
}
```

### Tools Used

| # | Tool | Status | Duration |
|---|------|--------|----------|
| 1 | `web_search` | success | 3509ms |

**Total unique tools: 1** — only `web_search` was called.

### HITL Gates Triggered

| Gate | Triggered? | Decision |
|------|-----------|----------|
| Router clarification | No | confidence 0.9 (above threshold) |
| Scope clarification | No | heuristic_passed (skipped) |
| Security proxy (1st pass) | No | web_search classified "safe" |
| Security proxy (2nd pass) | No | no tools to classify |
| Plan review | No | not triggered |

**HITL interrupts: 0**

### Model Info

| Occurrence | Model | Swap |
|-----------|-------|------|
| 1st complex_llm | `medium-default` (qwen3.5-9b-mlx) | not_needed |
| 2nd complex_llm | `medium-default` (qwen3.5-9b-mlx) | not_needed |

### Memory Operations

| Operation | Detail |
|-----------|--------|
| Topics extracted | javascript, js, python (61 occur), typescript, express, fastapi, html, ui, api, backend, concurrency, performance, rest, data, https, security |
| Interests updated | learning (26), debugging (24), optimization (33), architecture (10), testing (35), documentation (11) |
| Mem0 save | 5500 chars, 5 topics, `user_id=owner` |
| Cache invalidated | `reason=memory_updated` |
| Conversation recorded | session_id=integration-test-2026-05-27, 5 messages |
| STM (memories.json) | empty — no short-term facts stored |

## Memory / Workspace Verification

- [x] No duplicate embeddings — single `mem0_saved` event with 5 topics
- [x] Thread history clean — 5 messages (human → ai → tool → human → ai), no orphaned entries
- [x] No state leaks detected — session cleaned up after disconnect
- [ ] Mem0 search API has a bug — `user_id` passed as top-level param to `mem0_memory.search()` but Mem0 library expects it in `filters` dict. All `/api/mem0/search` calls return error.
- [ ] STM store returned empty — agent didn't save short-term memory facts, only LTM via Mem0

## What Works

1. **Router** correctly detects web search intent and routes to `complex-default` with high confidence (0.9)
2. **Security proxy** correctly classifies `web_search` as "safe" — no spurious HITL interruption
3. **Tool execution** — `web_search` completes successfully with relevant benchmark results
4. **Agent reasoning** — produces thorough comparison with table, mermaid diagram, and recommendation
5. **Memory write** — correctly extracts topics, updates interests, saves to Mem0, invalidates cache
6. **Audit logging** — captures full node lifecycle with timestamps, durations, channel-level detail
7. **Thread history** — properly persisted with 5 messages, retrievable via REST API
8. **AuditLogMiddleware** — HTTP requests logged correctly

## What Needs Tweaks

1. **File write not triggered**: Agent's second LLM pass described writing `comparison.md` but never emitted a `write_workspace_file` tool call. The model output text about writing the file but the actual tool invocation was missing. Root cause: model hallucination/omission — the agent "talked about" writing but didn't invoke the tool.

2. **Only 1 tool type used**: The prompt asked for web search AND file write, but only web search was executed. The agent needs better tool-use compliance for multi-step plans.

3. **Mem0 search API bug**: `/api/mem0/search` in `server.py` passes `user_id` as a top-level parameter to `mem0_memory.search()` but the Mem0 library rejects it with: `"Top-level entity parameters frozenset({'user_id'}) are not supported in search(). Use filters={'user_id': '...'} instead."`

4. **Token budget capped at 1536**: For a complex comparison task, 1536 tokens is low. The second LLM pass took 70s with a small budget.

5. **STM not populated**: Short-term memory (`memories.json`) remained empty. Agent only wrote to Mem0 LTM. Expected both STM and LTM writes for fact retention.

## Audit Log Statistics

Total events in `~/.owlynn/logs/audit.jsonl`: **205 events** across this test run

| Channel | Count |
|---------|-------|
| `agent.lifecycle` | 98 |
| `memory.topics` | 36 |
| `api.ws` | 24 |
| `agent.model` | 14 |
| `agent.hitl` | 13 |
| `agent.token` | 8 |
| `memory.cache` | 6 |
| `memory.inject` | 4 |
| `memory.write` | 2 |

## Logging System Status

- **Wired up?**: Yes
- `setup_logging()` called in lifespan: Yes
- `AuditLogMiddleware` attached: Yes
- Audit file output: Yes — `~/.owlynn/logs/audit.jsonl` (42KB)
- Audit error file: Yes — `~/.owlynn/logs/audit-errors.jsonl` (598B)
- Issues found:
  - No `@log_node` decorator usage observed in the graph nodes — none of the `agent.lifecycle` events carried `method`/`function` enrichment beyond `node` name. The node entry/exit events come from somewhere else (likely inline audit calls in the graph runner), not from the `@log_node` decorator in `log_middleware.py`.

## Search for Logging Plan Files

- `**/*.plan.md`: **0 files found**
- `**/*logging*plan*`: **0 files found**
- `**/*e999dbc9*`: **0 files found**

No logging plan files exist in the repository.

## Test Artifacts

- Raw event log: `/tmp/integration_test_events.json` (1818 events)
- Test script: `scripts/ws_integration_test.py`

## Recommendations

1. **Fix Mem0 search API** — change `user_id=user_id` to `filters={"user_id": user_id}` in `server.py` line 483
2. **Investigate tool-call omission** — second LLM pass should have emitted `write_workspace_file`. Consider adding a post-generation validation step or stronger system prompt nudging for file-write obligations.
3. **Increase token budget** for complex multi-step tasks to at least 4096
4. **Add STM write** in memory_write node alongside Mem0 LTM write for shorter-lived facts
5. **Wire @log_node decorator** into graph nodes for richer lifecycle telemetry

## Related

- [`docs/debugging/README.md`](README.md) — debugging index

## Last updated

2026-05-31 — `docs-standards-timeline` added frontmatter
