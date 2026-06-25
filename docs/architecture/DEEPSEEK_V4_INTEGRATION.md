---
status: active
category: architecture
last_updated: 2026-06-07
owner: ai-agent
purpose: "DeepSeek V4 integration in Owlynn: architecture, API behavior, implemented optimizations, and deferred Phase 5 response cache."
---

# DeepSeek V4 Integration & API Reference

**Last researched:** 2026-06-07  
**Implementation status:** Implemented (2026-06-07) — cache-friendly prompt layers, cloud brief first-turn gate, flash/pro tier, thinking policy, `reasoning_content` replay, cache observability, vision transcription cache, brief invalidation on memory write. **Phase 5 exact-match output cache deferred** (Part V); not LangCache / semantic similarity.

Official references:
- [DeepSeek API docs](https://api-docs.deepseek.com/)
- [Thinking mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [Context caching (KV cache)](https://api-docs.deepseek.com/guides/kv_cache)
- [Chat Completion API](https://api-docs.deepseek.com/api/create-chat-completion)
- [Tool calls](https://api-docs.deepseek.com/guides/tool_calls)

Related Owlynn docs: [`CLOUD-LLM-ARCHITECTURE.md`](../CLOUD-LLM-ARCHITECTURE.md), [`CHAT_PROTOCOL.md`](../CHAT_PROTOCOL.md)

---

## Part I — Current Owlynn Architecture

### 1. Role split: cloud-primary planner/workhorse

- **Local Unified Model** (`models.small`): router + simple path + vision proxy + background memory extraction (`gemma-4-e2b-heretic-uncensored-mlx`); preloaded at startup.
- **Local nomic embedding** (`models.embedding`): memory/RAG/web-rank; preloaded at startup.
- **DeepSeek V4** (`models.cloud`): primary complex workhorse on route `complex-cloud` (default when cloud available).
- The router can emit an `execution_plan` JSON block injected into the cloud system prompt.

Entry points: [`src/agent/llm.py`](../../src/agent/llm.py) (`get_cloud_llm`), [`src/agent/nodes/complex.py`](../../src/agent/nodes/complex.py) (`complex_llm_node`), [`src/agent/nodes/router.py`](../../src/agent/nodes/router.py).

### 2. Vision-to-text proxy (Gemma-4-E2B)

DeepSeek V4 is **text-only**. Images never go to the API as multimodal input.

When `route == complex-cloud` and the user attached images:

1. [`vision_proxy.py`](../../src/agent/nodes/complex_utils/vision_proxy.py) runs the unified local model Gemma-4-E2B (`models.small`, lazy via `vision_model_manager.py`).
2. Default mode: natural-language prompts → [`vision_qwen3vl.py`](../../src/agent/nodes/complex_utils/vision_qwen3vl.py) parses text/UI into structured blocks; [`vision_schema.py`](../../src/agent/nodes/complex_utils/vision_schema.py) formats `[Image content transcribed by vision sensor]` text.
3. DeepSeek receives a normal text conversation (no `image_url`).

On proxy failure, the code retries with a text-only prompt (no local multimodal fallback).

### 3. Cloud path security

Before any DeepSeek call on `complex-cloud`, [`prepare_cloud_payload()`](../../src/agent/nodes/complex_utils/cloud_payload.py):

1. **Anonymization** — deterministic SHA-256 placeholders for PII/paths/emails.
2. **Cloud brief** (first turn only) — compact HITL summary when no tool history; full anonymized history on tool-loop turns.
3. **Vision proxy** — local Gemma-4-E2B transcription with hash cache; post-vision re-anonymization.
4. **Deanonymization** on response content, `reasoning_content`, and tool-call args.

Routes are **`simple | complex-cloud`** (cloud-primary; legacy `complex-default` / `complex-vision` / `complex-longctx` removed).

### 4. Context, files, and config

| Setting | Location | Value |
|---------|----------|-------|
| Model default | `defaults.yaml` → `models.cloud.model_name` | `deepseek-v4-flash` |
| Base URL | `models.cloud.base_url` | `https://api.deepseek.com/v1` |
| Context window | `models.cloud.context_window` | 1,048,576 tokens |
| Max output | `models.cloud.max_tokens` | 8192 (per-request bind may cap higher via budget) |
| Pricing (miss) | `models.cloud.pricing` | $0.14 / 1M input, $0.28 / 1M output |

Uploaded text/code/CSV files are inlined into prompts via [`build_message_content()`](../../src/api/shared.py) (1M window).

Cloud tool calls use raw OpenAI client via [`cloud_invoke.py`](../../src/agent/nodes/complex_utils/cloud_invoke.py) with `strict=True` on `/v1`, falling back to `/beta` on schema errors. [`message_to_deepseek_dict()`](../../src/agent/nodes/complex_utils/cloud_payload.py) preserves `reasoning_content` on tool-loop replay.

### 6. What Owlynn sends (thinking config)

Per-request via [`resolve_cloud_thinking_config()`](../../src/agent/nodes/complex_utils/cloud_payload.py):

```yaml
extra_body.thinking.type: enabled | disabled   # NOT legacy thinking_mode
reasoning_effort: high | max                   # top-level when thinking enabled
```

Profile: `cloud_thinking_mode` (auto|always|never), `cloud_reasoning_effort`, `cloud_model_tier` (flash|pro). UI: [`CloudSettingsPanel.tsx`](../../frontend-v2/src/components/CloudSettingsPanel.tsx).

Local API key for dev/tests: copy [`.env.local.example`](../../.env.local.example) → `.env.local` (gitignored); loaded by [`start.sh`](../../start.sh) after `.env`.

---

## Part II-b — Phase 1.6 Resolved Decisions (2026-06-07)

| # | Topic | Decision |
|---|-------|----------|
| 1 | LangChain `reasoning_content` replay | Standard serializers **drop** custom fields → custom converter in `_prepare_cloud_payload()` |
| 2 | `strict=True` endpoint | Use **`/v1`**; fallback to **`/beta`** only on schema validation errors |
| 3 | `thinking_mode: true` | **Ignored**; explicit `thinking.type` required for control |
| 4 | `ainvoke` + streaming | **Unreliable** for reasoning aggregation → `astream_events` or custom handler |

### Implementation status (Phases 0–4)

| Item | Status |
|------|--------|
| Legacy route removal | Done — `complex-vision`, `complex-longctx` removed |
| `prepare_cloud_payload()` | Done — stable/volatile layers, brief gate, vision hook |
| `reasoning_content` replay | Done — custom converter + `cloud_invoke.py` |
| Cache observability | Done — `prompt_cache_hit_tokens` → `SessionCostTracker` + WS |
| Flash/Pro tier UI | Done — `CloudSettingsPanel` + dual `LLMPool` clients |
| Brief / vision local caches | Done — process-local TTL caches |
| Brief invalidation on memory write | Done — `invalidate_brief_cache()` from `memory_write_node` |
| Network prefix cache test | [`tests/test_deepseek_cache_network.py`](../../tests/test_deepseek_cache_network.py) (`@pytest.mark.network`) |
| V4 chat matrix (flash/pro × thinking) | [`tests/test_deepseek_v4_chat_matrix_network.py`](../../tests/test_deepseek_v4_chat_matrix_network.py) — see [testing guide](../guides/deepseek-v4-testing.md) |
| Multi-turn cloud brief regression | `tests/test_cloud_brief.py::test_brief_preserves_user_task_after_assistant_turn` |

---

## Part II — How DeepSeek V4 API Works

### 1. Models

| Model ID | Role |
|----------|------|
| `deepseek-v4-flash` | Default; cost/latency optimized |
| `deepseek-v4-pro` | Higher reasoning quality; higher cost |

Legacy IDs (`deepseek-chat`, `deepseek-reasoner`) map to flash non-thinking / flash thinking respectively and are **deprecated** (retirement scheduled 2026-07-24 UTC). New integrations should use explicit V4 IDs.

User override today: `cloud_model_tier: flash | pro` in profile + **Cloud & Usage** panel in the frontend.

### 2. Thinking vs non-thinking (single model, runtime toggle)

V4 does **not** use a separate “reasoner” model. The same model ID runs in one of two modes:

| Control | Where | Values | API default |
|---------|-------|--------|-------------|
| `thinking.type` | Request body (`extra_body` via LangChain) | `enabled` / `disabled` | **`enabled`** |
| `reasoning_effort` | Top-level request param | `high` / `max` | `high` |

**Non-thinking** (`thinking.type: disabled`):

- Returns `content` only (plus optional `tool_calls`).
- `temperature`, `top_p` are effective.
- Omit `reasoning_effort` entirely (do not pass `null`).
- Supports FIM (fill-in-middle beta).
- Tool calls: standard OpenAI-style loop (no `reasoning_content`).

**Thinking** (`thinking.type: enabled`):

- Returns `reasoning_content` (chain-of-thought) **and** `content` (final answer).
- `temperature`, `top_p`, penalties are **ignored** (no error).
- `max_tokens` caps **CoT + answer + tool JSON combined** — long CoT can exhaust budget before visible output.
- `usage.completion_tokens_details.reasoning_tokens` reports CoT token count.
- Tool calls supported; see replay rules below.

Example requests:

```python
# Non-thinking + tools
client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[...],
    tools=[...],
    temperature=0.4,
    max_tokens=8192,
    extra_body={"thinking": {"type": "disabled"}},
)

# Thinking + tools
client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[...],
    tools=[...],
    reasoning_effort="high",  # or "max"
    max_tokens=16384,
    extra_body={"thinking": {"type": "enabled"}},
)
```

### 3. Multi-turn chat (no tools)

```
Turn 1: user → assistant(reasoning_content, content)   [no tool_calls]
Turn 2: user + prior assistant message → new response
```

- You may append the full assistant message including `reasoning_content`.
- The API **ignores** prior `reasoning_content` when no tools were called (not an error).
- Legacy `deepseek-reasoner` docs said including `reasoning_content` caused **400** — V4 thinking mode **relaxed** this for non-tool chat. Follow V4 docs, not reasoner docs.

### 4. Tool loops in thinking mode (critical for Owlynn)

Owlynn’s graph (`complex_llm → security_proxy → tool_action → complex_llm`) matches DeepSeek’s agentic tool pattern.

**Rule:** After an assistant message with `tool_calls`, **every subsequent API call in that tool loop must include that assistant’s `reasoning_content`**. Missing it → **400 Bad Request**.

Correct loop:

```
1. API call → assistant { reasoning_content, content, tool_calls }
2. messages.append(response.choices[0].message)   # full message
3. Execute tools → append ToolMessage(s)
4. API call again with full history
5. Repeat until no tool_calls
```

Sub-turns within one user question (1.1, 1.2, 1.3) each replay accumulated reasoning. See [thinking mode tool sample](https://api-docs.deepseek.com/guides/thinking_mode).

**Non-tool follow-up user turn:** prior turn’s messages (including reasoning) stay in history; API accepts them.

### 5. Streaming

When `stream=true`, thinking mode emits:

1. `delta.reasoning_content` chunks (CoT)
2. Then `delta.content` chunks (answer)
3. Optional tool_call deltas

Owlynn sets `streaming=True` on the client but uses **`ainvoke()`**, so LangChain aggregates the full message. Live CoT in the UI would require `astream` + WebSocket events (not implemented).

### 6. Context caching (disk KV cache)

Enabled **by default** for all API users. No `cache_control` breakpoints.

- Cache hits require **identical prefix from token 0** across requests.
- Response `usage` includes:
  - `prompt_cache_hit_tokens` — billed ~$0.014 / 1M (vs ~$0.14 / 1M miss on flash)
  - `prompt_cache_miss_tokens`
- Multi-turn conversations benefit when earlier messages are preserved (tool loops).
- Optional `user_id` request param isolates KV cache per logical user/thread ([API docs](https://api-docs.deepseek.com/api/create-chat-completion)).

**Owlynn mitigations (implemented):**

- Stable core in `COMPLEX_PROMPT_STABLE`; date/memory/persona in volatile suffix.
- Cloud brief when **no tool history**; full anonymized thread when tools ran (see [`guides/cloud-multi-turn-context.md`](../guides/cloud-multi-turn-context.md)).
- `thread_id` passed as API `user` for per-conversation cache isolation.
- Cache hit telemetry in `SessionCostTracker` and WebSocket `model_info.token_usage`.

**Cache compliance (honest summary):** Owlynn is **designed for** prefix reuse (stable-first system, append-only tool threads) and **measures** hits — but volatile session text, cloud brief mode, trimming, and summarization **reduce** hit rate by design. Not every turn achieves cache hits.

### 7. Pricing snapshot (flash, 2026)

| Tier | Input (cache miss) | Input (cache hit) | Output |
|------|-------------------|-------------------|--------|
| v4-flash | ~$0.14 / 1M | ~$0.014 / 1M | ~$0.28 / 1M |
| v4-pro | higher | ~90%+ cheaper on hit | higher |

Exact pro rates vary with promotions; track via `SessionCostTracker` once cache fields are wired.

---

Exact pro rates vary with promotions; track via `SessionCostTracker` (cache hit/miss tiers wired).

---

## Part III — Remaining gaps (minor)

| Gap | Impact | Notes |
|-----|--------|-------|
| `show_thinking` UI | CoT not streamed to chat | `reasoning_content` captured in state; UI surfacing optional |
| `_strip_thinking_tags()` | Strips Qwen inline tags in `content` only | Unrelated to DeepSeek `reasoning_content` field |
| Live CoT streaming | No WS stream of reasoning deltas | Would need `astream` + protocol extension |

---

## Part IV — Implemented optimizations (Phases 0–4)

| Phase | Scope | Status |
|-------|--------|--------|
| **0** | Remove legacy routes; single `complex-cloud` prep path | Done |
| **1** | Prompt layers; cloud_brief first-turn; flash/pro UI; thinking + `reasoning_content`; cache observability | Done |
| **2** | Local brief builder cache; vision transcription cache + re-anonymize | Done |
| **3** | Security tests (`test_cloud_payload_integration.py`, etc.) | Done |
| **4** | Docs sync; network integration test for prefix cache hits | Done |

### Thinking policy (implemented)

Profile fields:

```yaml
cloud_thinking_mode: auto    # auto | always | never
cloud_reasoning_effort: high # high | max
cloud_model_tier: flash      # flash | pro
```

`cloud.tool_loop_force_thinking: true` in `defaults.yaml` overrides `never` during tool loops (DeepSeek API requirement).

---

## Part V — Phase 5 response cache (deferred)

**Decision (2026-06-07):** Do **not** implement Redis (or in-process) exact-match **output** cache now.

| Reason | Detail |
|--------|--------|
| Prefix cache covers input ROI | DeepSeek KV cache already discounts repeated system/history prefixes |
| Low hit rate on desktop | Byte-identical prompts within TTL are rare outside dev loops |
| Invalidation complexity | Volatile suffix (date, memory, plans) makes stale answers likely |
| Anonymization drift | Cached post-anonymization responses + later mapping tables risk corruption |

**Revisit only if:** prefix hit ratio **>30%** on stable turns, telemetry shows identical repeat prompts, and cost/latency still hurts after prefix optimization.

**If ever built:** prefer process-local LRU exact-match over Redis for single-user desktop; never cache `tool_calls` responses; block on `has_tool_history`.

---

## Part VI — Quick Reference Card

```
Route:        complex-cloud only (after Phase 0 cleanup)
Model:        deepseek-v4-flash (default) | deepseek-v4-pro (user choice)
Thinking:     extra_body.thinking.type = enabled|disabled
Effort:       reasoning_effort = high|max  (only when thinking enabled)
Tools:        bind_tools(strict=True); replay reasoning_content in loops
Cache:        automatic prefix cache; put stable text first, volatile last
Security:     anonymize → cloud → deanonymize
Images:       vision_proxy (Gemma-4-e2b) → text block in prompt
KV cache:     OpenAI `user` param = thread_id for per-conversation prefix isolation
Legacy:       deepseek-chat / deepseek-reasoner → migrate before 2026-07-24
```

---

## Changelog (this document)

| Date | Change |
|------|--------|
| 2026-06-07 | Initial integration summary (implementation details) |
| 2026-06-07 | Expanded with V4 API research: thinking/non-thinking, tool replay, KV cache, gaps |
| 2026-06-19 | Qwen3-VL-4B vision proxy replaces Florence-2; natural-language transcription |
