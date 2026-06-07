---
status: active
category: guide
last_updated: 2026-06-07
owner: ai-agent
---

# DeepSeek V4 Testing Guide

How to verify cloud chat quality across **flash/pro**, **thinking on/off**, routing, brief assembly, and usage tracking.

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| `DEEPSEEK_API_KEY` | In `.env` or `.env.local` (see [dev-startup.md](./dev-startup.md)) |
| Network | Live tests call `https://api.deepseek.com/v1` |
| Local stack (optional) | `./start.sh` for full UI verification at http://127.0.0.1:5173 |

Load secrets before network tests:

```bash
set -a && source .env && [ -f .env.local ] && source .env.local; set +a
```

## Test layers

| Layer | Marker | When to run | What it proves |
|-------|--------|-------------|----------------|
| Unit | (default) | Every `./scripts/ci.sh` | Brief assembly, routing logic, payload helpers, cost tracker |
| Contract | audit tests in CI | Every CI | WebSocket event shapes, cutover |
| Network | `@pytest.mark.network` | Manual or `./scripts/ci.sh --network` | Live DeepSeek V4 API behavior |
| Browser | Manual | After `./start.sh` | UI usage panel, orchestration badges |

Default CI **excludes** `@pytest.mark.network` (no API key burn on every push).

## Unit tests (no API key)

```bash
PYTHONPATH=$(pwd) python -m pytest -q \
  tests/test_cloud_brief.py \
  tests/test_cloud_payload_integration.py \
  tests/test_cloud_cost_tracker.py \
  tests/test_router_properties.py \
  tests/test_router_hitl_choices.py \
  -m "not network"
```

### Key regressions covered

| Test file | What it guards |
|-----------|----------------|
| `tests/test_cloud_brief.py` | **`test_brief_preserves_user_task_after_assistant_turn`** — multi-turn brief must not overwrite the user task with the prior assistant greeting (fixed 2026-06-07) |
| `tests/test_cloud_payload_integration.py` | Brief gate skipped on tool loops; `finalize_cloud_visible_content` empty-content fallback |
| `tests/test_router_properties.py` | Cloud-first default when cloud available; local fallback when off |
| `tests/test_router_hitl_choices.py` | HITL choice routes follow cloud availability |
| `tests/test_sentence_routing_and_response.py` | End-to-end graph with cloud **mocked off** for local medium path |

## Live network tests (requires API key)

```bash
./scripts/ci.sh --network
# or directly:
PYTHONPATH=$(pwd) python -m pytest -m network -v \
  tests/test_deepseek_v4_chat_matrix_network.py \
  tests/test_deepseek_cache_network.py
```

### Matrix: `test_deepseek_v4_chat_matrix_network.py`

| Test | Tier | Thinking | Assertion |
|------|------|----------|-----------|
| `test_deepseek_v4_chat_matrix[flash-False]` | flash | off | ≥80 chars, mentions REST or GraphQL |
| `test_deepseek_v4_chat_matrix[flash-True]` | flash | on | Same (content field; reasoning may be separate) |
| `test_deepseek_v4_chat_matrix[pro-False]` | pro | off | Same |
| `test_deepseek_v4_chat_matrix[pro-True]` | pro | on | Same |
| `test_cloud_brief_multiturn_produces_substantive_reply` | flash | on | Brief with prior greeting + new task → substantive answer, not generic greeting |

Uses `COMPLEX_PROMPT_STABLE` + `finalize_cloud_visible_content()` — same helpers as production.

### Prefix cache: `test_deepseek_cache_network.py`

Second identical-prefix call should report `prompt_cache_hit_tokens > 0`.

## Manual UI checklist

After `./start.sh`:

1. **Greeting** — `Hi` → route `simple`, 0 cloud calls in usage panel
2. **Complex** — `Compare REST vs GraphQL for a mobile backend` → Orchestration shows `complex-cloud` / `large-cloud`
3. **Usage** — Inspector → Cloud & Usage shows cost, tokens, daily budget bar; topbar `$` chip updates
4. **Flash vs Pro** — toggle tier in Cloud & Usage, send another complex prompt; last call shows tier
5. **Thinking** — set Auto / Always / Never; verify complex answers remain substantive (Never may still force thinking when tools are bound)

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Generic greeting on complex question | Stale backend without brief fix; restart with `./start.sh` |
| `cloud unavailable` in UI | Backend started without `.env` — use `./start.sh` or `source .env` before uvicorn |
| Network tests skipped | `DEEPSEEK_API_KEY` not exported in shell |
| Empty assistant bubble, usage shows tokens | Check `reasoning_content` vs `content`; `finalize_cloud_visible_content` only fills when content is empty |

## Related docs

- [DEEPSEEK_V4_INTEGRATION.md](../architecture/DEEPSEEK_V4_INTEGRATION.md) — API behavior, thinking, cache
- [CLOUD-LLM-ARCHITECTURE.md](../architecture/CLOUD-LLM-ARCHITECTURE.md) — routing and pool
- [local CI rule](../../.cursor/rules/local-ci.mdc) — `./scripts/ci.sh` flags
