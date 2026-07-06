---
status: active
category: standards
last_updated: 2026-07-07
owner: human
---

# Performance & Memory SLOs

> **Purpose:** Performance and memory SLOs for the Owlynn project on target hardware.

Target hardware: **Mac Air M4 (24 GB unified memory)**. These SLOs define the expected resource envelope for a healthy Owlynn session.

## Overview

Measured periodically and checked before major releases. SLOs cover response latency, memory budget, storage, CPU/thermal, throughput, and availability.

## Entry Points

```text
docs/PERFORMANCE_SLOS.md          # This file
tests/test_websocket_event_contract.py
tests/test_verify_report_fixture.py
tests/test_frontend_cutover_serving.py
```

## Architecture

### Degradation Ladder (Memory Approaches Limit at 14/16 GB)

1. Unload vision VLM from LM Studio (Qwen3-VL-4B, ~3 GB — largest model)
2. Unload extraction model from LM Studio (Qwen3-VL-4B, ~5 GB)
3. Reduce context window to 50K tokens
4. Disable auto-summarize (keep full context at reduced window)
5. If below 1 GB free, optionally stop SearXNG manually (`podman stop owlynn_searxng`) — not automated in application code

## API

### Response Latency

| Metric | Target | Degraded | Unacceptable |
|--------|--------|----------|--------------|
| **Semantic cache hit (repeated question)** | **< 100ms** | **100-500ms** | **> 500ms** |
| Simple query (keyword-matched) | < 2s | 2-5s | > 5s |
| Complex query (cloud DeepSeek V4) | < 15s | 15-30s | > 30s |
| Streaming first token | < 3s | 3-8s | > 8s |
| Tool execution (single call) | < 5s | 5-15s | > 15s |
| WebSocket connect | < 1s | 1-3s | > 3s |

Measured from: user sends message → assistant first token received (streaming), or final message received (non-streaming).

### Memory Budget

| Component | Budget | Notes |
|-----------|--------|-------|
| Python agent (langgraph + LLM pool) | 2 GB | Peak during complex reasoning + tool execution |
| Local Unified LLM (`qwen3-vl-4b-instruct-c_abliterated-v2-mlx`, LM Studio) | 5 GB | Router, vision proxy, memory extraction |
| nomic embedding (LM Studio) | 140 MB | Memory/RAG/web-rank embeddings |
| Qdrant (Docker) | 512 MB | Vector store for memory |
| Redis (Docker) | 128 MB | Session state + LangGraph checkpoints |
| SearxNG (Docker) | 256 MB | Local web search |
| Frontend (Tauri + React) | 256 MB | Desktop shell + rendered UI |
| **Total sustained** | **~8.3 GB** | All models loaded, all services running |
| **Total peak** | **~9.3 GB** | During complex reasoning + web search + memory save |

### Storage

| Resource | Budget | Notes |
|----------|--------|-------|
| Codebase + build artifacts | ~500 MB | Python venv, node_modules, dist |
| Qdrant vectors | ~200 MB | Per ~50K memory entries |
| Redis RDB snapshots | ~100 MB | Session checkpoints |
| Audit logs | ~50 MB | JSONL audit bundles |
| **Total** | **~850 MB** | |

### CPU / Thermal

| Metric | Target | Degraded | Unacceptable |
|--------|--------|----------|--------------|
| Idle CPU (no active query) | < 10% | 10-30% | > 30% |
| Query CPU (streaming response) | < 80% | 80-95% | > 95% sustained |
| Fan noise during normal use | silent | audible | loud |
| Thermal throttle events | 0 per session | 1-2 per session | > 2 per session |

### Throughput

| Metric | Target |
|--------|--------|
| Concurrent sessions | 1 (active) + unlimited (idle, checkpointed) |
| Streaming tokens/second (cloud model) | > 30 tok/s |
| Streaming tokens/second (router model) | > 80 tok/s |
| WebSocket reconnect | < 2s |
| Project switch latency | < 500ms |

### Availability

| Metric | Target |
|--------|--------|
| Services uptime (Qdrant, Redis, SearxNG) | 99.9% per session |
| Non-graceful degradation rate | < 1% of queries |
| Graph execution error rate | < 0.5% of queries |
| WS disconnect rate | < 1 per 100 queries |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Hard memory budget at 14 GB (2 GB headroom) | Prevents swap thrashing on 24 GB system | Reduces model size or disables features when budget exceeded |
| Latency regressions > 20% block next phase | Maintains UX quality during development | Slows feature velocity |
| Thermal throttling during idle is a release blocker | Indicates resource leak or misconfiguration | Requires investigation before release |

## Testing

### Quick Check (Before Commit)

```bash
ps -o rss,pid -p $(pgrep -f "python.*uvicorn" | head -1)
ps -o rss,pid -p $(pgrep -f "LM Studio" | head -1) 2>/dev/null || echo "LM Studio not running"
docker stats --no-stream qdrant redis searxng 2>/dev/null
ls -lh frontend-v2/dist/assets/index-*.js frontend-v2/dist/assets/index-*.css
```

### Full SLO Check (Pre-Release)

```bash
cd frontend-v2 && npm run build
cd .. && python3 -m pytest tests/test_websocket_event_contract.py tests/test_verify_report_fixture.py tests/test_frontend_cutover_serving.py --tb=short
```

Manual latency check (requires LM Studio + containers running):

```bash
time python3 -c "
import asyncio
from src.agent.llm import get_small_llm
loop = asyncio.get_event_loop()
llm = loop.run_until_complete(get_small_llm())
result = loop.run_until_complete(llm.ainvoke(['hello']))
print(result.content[:100])
"
```

## Configuration

No specific env vars for SLOs. Enforced via policy rules:

1. Memory budget is hard — if sum of all services exceeds 14 GB (2 GB headroom), reduce model size or disable features before releasing
2. Latency regressions > 20% require investigation and documentation before proceeding
3. Thermal throttling during normal use (non-query idle) is a blocker
4. SLOs checked manually before phase transitions (no automated SLO gate yet)

## Related

- [`docs/standards/documentation.md`](standards/documentation.md) — doc structure rules
- [`docs/standards/coding-style.md`](standards/coding-style.md) — coding conventions
- [`docs/features/SEMANTIC_CACHE.md`](features/SEMANTIC_CACHE.md) — semantic cache (< 100ms TTFT for cache hits)
- [`docs/architecture/REDIS_LIFECYCLE.md`](architecture/REDIS_LIFECYCLE.md) — Redis memory management

## Last updated

2026-07-07 — Added semantic cache hit SLO (< 100ms). Redis budget note updated.
2026-05-31 — `docs-standards-timeline` added frontmatter, purpose blockquote
