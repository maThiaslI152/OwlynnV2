---
status: active
category: standards
last_updated: 2026-08-26
owner: human
---

# Performance & Memory SLOs

> **Purpose:** Performance and memory SLOs for the Owlynn project on target hardware.

Target hardware: **Mac Air M4 (24 GB unified memory)**. These SLOs define the expected resource envelope for a healthy Owlynn session.

## Overview

Measured periodically and checked before major releases. SLOs cover response latency, memory budget, storage, CPU/thermal, throughput, and availability.

**Local-first envelope (2026-08-25/26):** Default `cloud_routing_mode=local_only`. Preload **main + embedding only** (vision/Stirling on-demand). Core health = Postgres + LM Studio (+ optional Stirling). Redis/Qdrant are not on the live path. Pentest/Kali stays off until `features.pentest_enabled`. Podman machine **4 GB** recommended; Postgres container `mem_limit: 768m` (`docker-compose.mvp.yml`).

**Usable multi-turn gate:** Run `scripts/manual/e2e_topic_drift_ws.py --profile usable|full` after latency/tool changes. Functional pass (idle + correct tools) is required. UI `usable_gate` is still `False` while any turn is SLO `unacceptable` (warm T1 simple often &gt;8s on 12B). See `docs/changes/usable-multiturn-chat/CHANGELOG.md`.

## Entry Points

```text
docs/PERFORMANCE_SLOS.md          # This file
tests/test_websocket_event_contract.py
tests/test_verify_report_fixture.py
tests/test_frontend_cutover_serving.py
```

## Architecture

### Degradation Ladder (Memory Approaches Limit at 14/16 GB)

1. Keep vision VLM unloaded (already on-demand)
2. Stop StirlingPDF container (idle_shutdown default on)
3. Reduce context window / trigger auto-summarize earlier
4. If below 1 GB free, unload main LLM via idle manager
5. Optionally stop SearXNG manually — not automated in application code

## API

### Response Latency

| Metric | Target | Degraded | Unacceptable |
|--------|--------|----------|--------------|
| **Semantic cache hit (repeated question)** | **< 100ms** | **100-500ms** | **> 500ms** |
| Simple / trivia (deterministic → simple, no coherence LLM) | < 3s | 3-6s | > 8s |
| Web tool-first (search then one synthesis) | < 8s | 8-15s | > 25s |
| Complex local (bind_tools rounds) | < 20s | 20-40s | > 60s |
| Complex cloud (DeepSeek, when flipped) | < 15s | 15-30s | > 30s |
| Streaming first token (simple) | < 2s | 2-5s | > 8s |
| Tool execution (single call) | < 5s | 5-15s | > 15s |
| WebSocket connect | < 1s | 1-3s | > 3s |

Measured from: user sends message → assistant first token received (streaming), or final message received (non-streaming).

**Instrumentation:** Audit `api.ws` / `ttft` (`ttft_ms`) and `turn_complete` (`ttft_ms` + `turn_duration_ms`). E2E/frontier JSON include `ttft_ms`.

**12B call budget (warm, local_only):** simple ≈ 1 generate (`simple.max_tokens` default **128**); web tool-first ≈ inject search + extractive answer when `complex.tool_first_extractive_synth=true` (else unbound synth capped at `complex.tool_first_synth_token_budget` **384**, no synth retry); list/read tool-first + post-read short-circuit skip a second LLM; avoid always-on coherence.

**Heavy prefill (web synth):** Not routing — system prompt + memory volatile suffix + thread + `web_search` ToolMessage. Prefer extractive synth after tool-first search; trim prior-turn tool blobs (`tool_output.prior_turn_max_chars`).

### Memory Budget

| Component | Budget | Notes |
|-----------|--------|-------|
| Python agent (langgraph + LLM pool) | 2 GB | Peak during complex reasoning + tool execution |
| Local Main LLM (`gemma-4-12b-agentic-…@q4_k_m`, LM Studio) | ~7.5 GB | Unified engine: simple, complex-default, extraction |
| MXBAI embedding (`text-embedding-mxbai-embed-large-v1`) | 670 MB | Preloaded with main |
| Vision OCR (`baidu.unlimited-ocr`) | 1.5 GB | On-demand only (not in startup.preload) |
| PostgreSQL + pgvector | 768 MB | Container `mem_limit` in mvp compose; needs Podman VM ≥4 GB |
| StirlingPDF | ~250 MB | On-demand; idle_shutdown default true |
| Frontend (Electron + React) | 256 MB | Desktop shell + rendered UI |
| **Total sustained (lite)** | **~11 GB** | main + embed + Postgres + UI |
| **Total peak** | **~13 GB** | + vision/Stirling/web during PDF/vision turns |

### Storage

| Resource | Budget | Notes |
|----------|--------|-------|
| Codebase + build artifacts | ~500 MB | Python venv, node_modules, dist |
| Postgres vectors | ~200 MB | Per ~50K memory entries |
| Audit logs | ~50 MB | JSONL audit bundles |
| **Total** | **~750 MB** | |

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
| Streaming tokens/second (main 12B local) | > 40 tok/s |
| Streaming tokens/second (cloud when enabled) | > 30 tok/s |
| WebSocket reconnect | < 2s |
| Project switch latency | < 500ms |

### Availability

| Metric | Target |
|--------|--------|
| Core services (Postgres, LM Studio) | Required for healthy session |
| StirlingPDF | Optional / on-demand |
| Redis / Qdrant | Not used (Postgres/pgvector only) |
| Graph execution error rate | < 0.5% of queries |
| WS disconnect rate | < 1 per 100 queries |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Hard memory budget at 14 GB (2 GB headroom) | Prevents swap thrashing on 24 GB system | Reduces model size or disables features when budget exceeded |
| Latency regressions > 20% block next phase | Maintains UX quality during development | Slows feature velocity |
| Thermal throttling during idle is a release blocker | Indicates resource leak or misconfiguration | Requires investigation before release |
| local_only + lite preload | Fit Normal/Study on M4 Air beside Cursor | Cloud/Eco and Pentest are explicit opt-in |

## Testing

### Quick Check (Before Commit)

```bash
ps -o rss,pid -p $(pgrep -f "python.*uvicorn" | head -1)
ps -o rss,pid -p $(pgrep -f "LM Studio" | head -1) 2>/dev/null || echo "LM Studio not running"
./scripts/ci.sh --quick
```

### Full SLO Check (Pre-Release)

```bash
cd frontend-v2 && npm run build
cd .. && python3 -m pytest tests/test_websocket_event_contract.py tests/test_verify_report_fixture.py tests/test_frontend_cutover_serving.py --tb=short
```
