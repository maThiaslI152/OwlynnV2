---
last_verified: 2026-05-26
auto_generated: false
purpose: "Cloud LLM connection architecture: key resolution chain, security improvements, circuit breaker, cost tracking, retry/fallback, and new API endpoints."
---
# Cloud LLM Connection Architecture (2026-05-26)

### Overview

The system uses a three-tier LLM pool (`small` / `medium` / `cloud`) managed by `LLMPool` in [`src/agent/llm.py`](src/agent/llm.py). The cloud tier connects to DeepSeek V4 via the OpenAI-compatible API at `https://api.deepseek.com/v1`.

### Key Resolution Chain

```
macOS Keychain → DEEPSEEK_API_KEY env var → deepseek_api_key in user_profile.json (deprecated)
```

See [`src/config/secret_store.py`](src/config/secret_store.py) for the implementation.

### Security Improvements

| Before | After |
|--------|-------|
| API key in plaintext `data/user_profile.json` | API key in macOS Keychain via `keyring` |
| No request timeout (hang risk) | 180s `request_timeout` on all cloud calls |
| Single 429 retry (2s) | Exponential backoff (1s/2s/4s) for 429 + 5xx |
| No circuit breaker | `CloudCircuitBreaker` disables cloud for 60s after 3 consecutive failures |
| Silent auth failures | User-visible warning with fix instructions |
| No cost tracking | `SessionCostTracker` with per-session token/cost summary |
| DeepSeek V3 (`deepseek-chat`) | DeepSeek V4 (`deepseek-v4`) |

### New Files

| File | Purpose |
|------|---------|
| [`src/config/secret_store.py`](src/config/secret_store.py) | Keychain-backed API key storage, key verify, key rotation |
| [`src/agent/cloud_circuit_breaker.py`](src/agent/cloud_circuit_breaker.py) | Tracks consecutive failures; auto-disables cloud |
| [`src/agent/cloud_cost_tracker.py`](src/agent/cloud_cost_tracker.py) | Per-session token/cost tracking |

### New API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/cloud-status` | Returns `{available, key_valid, model, error}` |
| `POST /api/cloud-verify-key` | Tests a key without persisting (returns `{valid, message}`) |
| `GET /api/usage` (updated) | Now includes cost tracker summary |

### Frontend

- Cloud status dot shown alongside WebSocket connection status in topbar
- Status fetched from `/api/cloud-status` on connect
- Green dot = cloud reachable + key valid; Red dot = unavailable

### Startup Health Check

`init_agent()` resets circuit breaker and cost tracker, then runs a non-blocking cloud connectivity check that logs the result.

### Retry & Fallback

Cloud LLM calls use `_invoke_with_cloud_retry()` in [`src/agent/nodes/complex.py`](src/agent/nodes/complex.py):
- Retries on 429, 500, 502, 503, 504 with jittered exponential backoff
- No retry on 401/403 (immediate fallback to local with auth warning)
- Circuit breaker skips cloud after 3 consecutive failures for 60s
- Fallback always goes to `medium-default` with appropriate user notification

---

## Recommended Priority Actions

1. **Fix BUG-1 (Persona Leak)** — Critical, affects every new conversation
2. **Fix BUG-2 (Orchestration Panel)** — Core observability feature, needed for debugging
3. **Fix BUG-3 (Memory Loading)** — Core feature, needed for personalization
4. **Fix BUG-5 (Tauri Fallback)** — Blocks Safe Mode in browser deployments
5. **Fix BUG-4 (Chat Titling)** — Quality of life, auto-generated titles improve navigation
6. **Fix BUG-6 (Mock Data)** — Remove demo entries for clean production UI
7. **Fix BUG-7 (Operator Note)** — Correct the delete message text
8. **Fix BUG-8 (Audit Expand)** — Enable the audit verification features
