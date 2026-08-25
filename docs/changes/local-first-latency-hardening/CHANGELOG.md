# Local-first latency hardening

## 2026-08-25 — Match Normal/Study speed on M4 Air; measure TTFT

### What
- Default `cloud_routing_mode=local_only`; hide Pentest (`features.pentest_enabled=false`); lite preload (main+embed).
- Deterministic widen (simple trivia / web intent including GDP); tool-first web (inject search, one unbound synth).
- Coherence LLM skipped on simple/short/successful-web turns; `simple.max_tokens` 512; tool-first synth budget 1024.
- TTFT audit on first WS chunk + turn_complete; refuse poisoned semantic-cache tool leaks.
- Vision images honor `local_only`; crash.log open failures no longer break startup.
- Eval: GDP E2E cache-bust; frontier local routes + HITL stall abort; ask_user guards for code-review-without-code.

### Why
Unified 12B made simple/web turns feel slow. Routing was already cheap; planning `bind_tools` prefill and coherence tax were avoidable. Heavy remaining cost is 12B synth prefill (system+memory+ToolMessage) + decode.

### Files
- `src/agent/core/tool_first_web.py`, `ask_user_guards.py`, `complex.py`, `simple.py`, `coherence.py`
- `src/agent/routing/deterministic.py`, `src/api/ws/handler.py`, `src/memory/semantic_cache.py`
- `src/config/defaults.yaml`, `scripts/manual/e2e_gdp_followup_ws.py`, `scripts/run_local_frontier_eval.py`
- Docs: `AGENT_FLOW.md`, `PERFORMANCE_SLOS.md`, `SEMANTIC_CACHE.md`, `EVALUATION.md`, `CHAT_PROTOCOL.md`
