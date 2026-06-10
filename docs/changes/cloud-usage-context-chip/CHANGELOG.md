---
status: active
category: changelog
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# Changelog: Cloud Usage Chip & Context Breakdown Popover

> **Purpose:** Document the clickable DeepSeek cost chip in the inspector header, per-request context breakdown (OpenCode-style), and the fix for session cost disappearing when switching chats.

## User-facing behavior

| Action | Result |
|--------|--------|
| Cloud turn completes | Header shows **`$0.010`** chip (session estimated cost) |
| Click chip | Popover: session in/out tokens, cache %, **last request context** bar + category rows (opaque panel — BUG-15) |
| Switch chat / new chat | Chip **stays** — cost is app-session scoped, not per-thread |
| Next cloud turn | Context breakdown updates; session totals accumulate |

## Context breakdown categories

Estimated from the prompt sent on the last `complex_llm` turn (scaled to API `prompt_tokens` when available):

| Category | Source messages |
|----------|-----------------|
| **System** | `SystemMessage` — persona, tools guidance, volatile suffix |
| **Conversation** | `HumanMessage`, `AIMessage` (chat history) |
| **Tools** | `ToolMessage` — web search / fetch results |
| **Output** | API `completion_tokens` |
| **Reasoning** | API `reasoning_tokens` (when reported) |

Popover shows `total_used / max_context` and each category’s **% of model window** (e.g. 1M for DeepSeek V4).

## Bug fixed: chip vanished on chat switch

**Symptom:** After selecting another chat, the `$0.01x` chip disappeared until another cloud turn.

**Root causes:**

1. **`clearSession()` cleared `cloudUsage`** — chat switches call `clearSession()` for messages/tools, but cloud cost is **server session** scoped, not per-thread.
2. **`GET /api/usage` shape mismatch** — response had token counts in `session` (`_session_usage`) but `total_calls` / `estimated_cost_usd` only in `cost` (`tracker.summary()`). `parseCloudUsagePayload` preferred `session` → `total_calls: 0` → chip hidden after WS reconnect refetch.

**Fixes:**

| Layer | Change |
|-------|--------|
| `useAppStore.clearSession` | No longer clears `cloudUsage` |
| `parseCloudUsagePayload` | Merges `session` + `cost` fields |
| `GET /api/usage` | `session` = `{**tracker.summary(), **_session_usage}` |
| `App.tsx` | `refreshCloudUsage()` after new chat / switch chat / switch project |

## Implementation map

### Backend

| File | Role |
|------|------|
| `src/agent/nodes/complex_utils/context_breakdown.py` | `estimate_context_breakdown()`, `enrich_token_usage_with_breakdown()` |
| `src/agent/nodes/complex.py` | Attaches `context_breakdown` to `api_tokens_used` before node return |
| `src/api/server.py` | Unified `session` in `/api/usage` |
| `src/api/ws/handler.py` | Forwards `token_usage` (incl. breakdown) in `model_info` events |

### Frontend

| File | Role |
|------|------|
| `frontend-v2/src/components/CloudUsageChip.tsx` | Clickable chip + popover UI |
| `frontend-v2/src/components/AppShell.tsx` | Replaces static `<span class="cloud-usage-chip">` |
| `frontend-v2/src/lib/cloudUsage.ts` | `parseContextBreakdown()`, merged `parseCloudUsagePayload` |
| `frontend-v2/src/state/useAppStore.ts` | `contextBreakdown` state; `cloudUsage` survives `clearSession` |
| `frontend-v2/src/App.tsx` | Sets breakdown from `model_info.token_usage`; refetch on chat switch |
| `frontend-v2/src/index.css` | `.cloud-usage-popover`, context bar styles |

### Tests

| File | Covers |
|------|--------|
| `tests/test_context_breakdown.py` | Category estimation + enrich helper |
| `frontend-v2/src/components/__tests__/cloud-usage-chip.test.tsx` | Popover open + breakdown render |
| `frontend-v2/src/components/__tests__/cloud-settings.test.tsx` | `parseCloudUsagePayload` session/cost merge |

## WebSocket contract addition

`model_info.token_usage` may include:

```json
{
  "prompt_tokens": 12000,
  "completion_tokens": 800,
  "context_breakdown": {
    "max_context": 1048576,
    "categories": { "system": 2000, "conversation": 3000, "tools": 7000, "output": 800, "reasoning": 0 },
    "category_pct": { "system": 0.2, "conversation": 0.3, "tools": 0.7, "output": 0.1, "reasoning": 0 },
    "input_estimated": 12000,
    "total_used": 12800,
    "used_pct": 1.2
  }
}
```

## Related

- [`docs/CLOUD-LLM-ARCHITECTURE.md`](../../CLOUD-LLM-ARCHITECTURE.md) — cost tracker + API endpoints
- [`docs/CHAT_PROTOCOL.md`](../../CHAT_PROTOCOL.md) — `model_info` event
- [`docs/changes/web-search-synthesis-fix/CHANGELOG.md`](../web-search-synthesis-fix/CHANGELOG.md) — prior cloud synthesis work

## Last updated

2026-06-10 — cloud-usage-context-chip + chat-switch persistence fix
