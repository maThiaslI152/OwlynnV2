---
last_verified: 2026-06-07
auto_generated: false
purpose: "Cloud LLM connection architecture: key resolution, security, circuit breaker, cost/cache tracking, DeepSeek V4 payload path, and deferred output cache."
---
# Cloud LLM Connection Architecture

### Overview

The system uses a three-tier LLM pool (`small` / `medium` / `cloud`) managed by `LLMPool` in [`src/agent/llm.py`](src/agent/llm.py). The cloud tier connects to **DeepSeek V4** (`deepseek-v4-flash` default, `deepseek-v4-pro` optional) via the OpenAI-compatible API at `https://api.deepseek.com/v1`.

Routes: **`simple | complex-default | complex-cloud`** only. Legacy `complex-vision` / `complex-longctx` routes were removed (2026-06).

**DeepSeek API behavior (thinking mode, KV prefix cache, tool loops, payload structure):** see [`docs/architecture/DEEPSEEK_V4_INTEGRATION.md`](architecture/DEEPSEEK_V4_INTEGRATION.md).

**Implementation status (2026-06-07):** Phases 0–4 **implemented** — cache-friendly prompt layers, cloud brief gate, flash/pro tier, thinking policy, `reasoning_content` replay, prefix-cache observability, vision transcription cache, brief invalidation on memory write. **Phase 5 exact-match output cache deferred** (see DEEPSEEK doc Part V).

### Key Resolution Chain

```
macOS Keychain → DEEPSEEK_API_KEY env var → .env.local (dev) → deepseek_api_key in user_profile.json (deprecated)
```

Load order for dev/CLI: `.env` then `.env.local` (see [`start.sh`](../start.sh), [`.env.local.example`](../.env.local.example)).

See [`src/config/secret_store.py`](src/config/secret_store.py) for Keychain implementation.

### Cloud Payload Path (complex-cloud)

```
complex_llm_node
  └─ prepare_cloud_payload()     # cloud_payload.py — anonymize, brief gate, vision proxy
       └─ _invoke_cloud_path()   # cloud_invoke.py — strict tools, reasoning replay
            └─ SessionCostTracker # prompt_cache_hit_tokens, cost estimate
                 └─ WS model_info.token_usage
```

| Module | Purpose |
|--------|---------|
| [`cloud_payload.py`](src/agent/nodes/complex_utils/cloud_payload.py) | Stable/volatile prompt layers, brief cache (300s TTL), thinking config, cache metrics extraction |
| [`cloud_invoke.py`](src/agent/nodes/complex_utils/cloud_invoke.py) | Raw OpenAI client, `/v1` + `/beta` fallback, `reasoning_content` on tool loops |
| [`vision_proxy.py`](src/agent/nodes/complex_utils/vision_proxy.py) | Local Qwen vision → text for DeepSeek; hash cache (3600s TTL) |
| [`cloud_cost_tracker.py`](src/agent/cloud_cost_tracker.py) | Per-session tokens, cache hit ratio, USD estimate |

### Cache Layers (current)

| Layer | What | Where | Skips API? |
|-------|------|-------|------------|
| DeepSeek KV prefix cache | Identical input prefix tokens | DeepSeek server | No — discounts input billing only |
| Cloud brief cache | Built brief string | Process-local dict | No |
| Vision transcription cache | VLM output by image hash | Process-local dict | No |
| Memory context cache | Formatted memory/knowledge | `MemoryContextCache` | No |
| **Output response cache** | Full assistant reply | — | **Not implemented (deferred)** |

Prefix cache proof: [`tests/test_deepseek_cache_network.py`](../tests/test_deepseek_cache_network.py) (`@pytest.mark.network`, requires `DEEPSEEK_API_KEY`).

### Security & Reliability

| Concern | Implementation |
|---------|----------------|
| API key storage | macOS Keychain via `keyring` (not plaintext profile) |
| Request timeout | 180s `request_timeout` on cloud calls |
| Retry | Exponential backoff (1s/2s/4s) for 429 + 5xx |
| Circuit breaker | `CloudCircuitBreaker` — disables cloud 60s after 3 consecutive failures |
| PII | Anonymize → cloud → deanonymize in `prepare_cloud_payload()` |
| Cost tracking | `SessionCostTracker` with cache-aware pricing (`cache_hit_per_1m_usd`) |
| Model IDs | `deepseek-v4-flash` / `deepseek-v4-pro` (legacy `deepseek-chat` deprecated) |

Supporting modules: [`secret_store.py`](src/config/secret_store.py), [`cloud_circuit_breaker.py`](src/agent/cloud_circuit_breaker.py).

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/cloud-status` | `{available, key_valid, model, error}` |
| `POST /api/cloud-verify-key` | Test key without persisting |
| `GET /api/usage` | Session cost + `prompt_cache_hit_tokens` summary |

### Frontend

- Cloud status dot in topbar (from `/api/cloud-status`)
- [`CloudSettingsPanel.tsx`](../frontend-v2/src/components/CloudSettingsPanel.tsx) — tier (flash/pro), thinking mode, reasoning effort
- `model_info.token_usage` may include `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens` on cloud turns

### Retry & Fallback

Cloud LLM calls use `_invoke_with_cloud_retry()` in [`complex.py`](src/agent/nodes/complex.py):

- Retries on 429, 500, 502, 503, 504 with jittered exponential backoff
- No retry on 401/403 — immediate fallback to local with auth warning
- Circuit breaker skips cloud after 3 consecutive failures for 60s
- Fallback to `complex-default` (medium local model)

### Related

- [`DEEPSEEK_V4_INTEGRATION.md`](architecture/DEEPSEEK_V4_INTEGRATION.md) — full API + optimization reference
- [`CHAT_PROTOCOL.md`](CHAT_PROTOCOL.md) — WebSocket `model_info` / `router_info` events
- [`guides/dev-startup.md`](guides/dev-startup.md) — `.env.local` workflow

### Last updated

2026-06-07 — Phases 0–4 sync; Phase 5 output cache deferral; `.env.local` secrets workflow
