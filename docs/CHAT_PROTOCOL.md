---
status: active
category: reference
last_updated: 2026-06-15
owner: ai-agent
audience: agent
---

# Chat & Events Protocol

> **Purpose:** Developer-facing JSON contract between the frontend WebSocket client (`frontend-v2`), the backend WebSocket handler (`src/api/ws/handler.py`), and the LangGraph execution stream forwarded to the browser.

## Overview

Defines all client-to-server payloads and server-to-client event types. Keeping this doc accurate prevents UI/backend drift when modifying nodes, tools, or streaming behavior.

## Entry Points

```text
src/api/ws/handler.py              # websocket_endpoint(), serialize_message(), forward_events()
frontend-v2/src/lib/wsClient.ts     # WebSocket client send/receive
frontend-v2/src/App.tsx             # Event handler wiring
frontend-v2/src/lib/toolPreamble.ts # Tool-only placeholder filter (hide from stream)
src/agent/nodes/simple.py           # Simple node streaming source
src/agent/nodes/complex.py          # Complex node streaming source
src/agent/nodes/router.py           # router_node() — router_metadata source
frontend-v2/electron/main.ts        # Desktop runtime events (TTS, etc.)
```

## Architecture

### WebSocket Endpoint

```
ws://<host>:8000/ws/chat/<thread_id>
```

`thread_id` is used as the LangGraph `configurable.thread_id` and is also the key for per-thread memory context caching (`src/agent/nodes/memory.py`).

## API

### Client → Server: Send Payloads

#### Chat Message

```json
{
  "message": "string",
  "files": [
    {
      "name": "string",
      "type": "string (mime type or 'workspace_ref')",
      "data": "string (base64)",
      "path": "string"
    }
  ],
  "mode": "tools_on | tools_off",
  "web_search_enabled": true | false,
  "response_style": "normal | learning | concise | explanatory | formal",
  "project_id": "string",
  "source": "text | voice"
}
```

Default values applied by server:

| Field | Default |
|-------|---------|
| `mode` | `"tools_on"` |
| `web_search_enabled` | `true` |
| `response_style` | `"normal"` |
| `project_id` | `"default"` |
| `source` | `"text"` |

#### Stop Generation

```json
{ "type": "stop" }
```

Cancels the background graph task for that `thread_id`.

#### Security Approval Response

```json
{ "type": "security_approval", "approved": true | false }
```

Resumes HITL-gated sensitive tool calls.

#### Ask-User Response

```json
{ "type": "ask_user_response", "answer": "string | object" }
```

`answer` is forwarded without string coercion — structured router choices (e.g. `{ "route": "...", "toolbox": "..." }`) remain intact.

#### Plan Review Response (NEW)

```json
{ "type": "plan_review_response", "approved": true | false, "feedback": "optional string" }
```

Resumes the `plan_review` HITL gate after human review. `feedback` is optional text from the reviewer.

### File Attachment Handling

#### Workspace References

```json
{
  "type": "workspace_ref",
  "path": "relative/path/in/workspace"
}
```

- Does not write file bytes
- Appends marker to `user_input`: `[Attached Workspace File: <path>]`
- Agent uses `read_workspace_file` if it needs content

#### Uploaded Files (base64)

For non-`workspace_ref` attachments, the server:
1. Normalizes each file via `normalize_file_attachment()` (`src/api/attachment_intake.py`) — strips `data:<mime>;base64,` prefixes, infers MIME from filename when `type` is omitted
2. Base64-decodes payload and saves raw bytes into the active project workspace folder

Frontend should send `type` (MIME) on each file; Composer infers from `file.type` or extension when missing.

| MIME/Type | Behavior |
|-----------|----------|
| `image/png`, `image/jpeg`, `image/webp`, `image/gif` | **Cloud route (`complex-cloud`):** transcribed via `vision_proxy` (Qwen3-VL-4B) before DeepSeek (text-only API). UI shows thumbnail in composer + message bubble. **Not** indexed into Qdrant/RAG. |
| `application/pdf` / `.pdf` | Text extracted inline when possible; otherwise agent calls `read_workspace_file` |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` / `.docx`, `.doc` | Text and table contents extracted inline on upload; otherwise agent calls `read_workspace_file` |
| Other UTF-8 text/code | Inlined in prompt as fenced block |
| Other binary | Saved to workspace; agent instructed to call `read_workspace_file` |

Cloud route (`complex-cloud`) with images: lazy-loaded Qwen3-VL-4B (`models.vision_proxy`) via `vision_proxy` → formatted text block for DeepSeek; on proxy failure, retries `complex-cloud` with text-only prompt.

### Server → Client: Event Types

#### `status`

```json
{ "type": "status", "content": "reasoning | idle" }
```

- Sent when graph run starts/finishes or client disconnects

#### `chunk`

```json
{ "type": "chunk", "content": "string", "metadata": {} }
```

- Sent during streaming for nodes: `simple`, `complex_llm`
- **Suppressed** while tool calls are pending or running (`complex_llm` only) — progress is shown via `tool_execution` cards instead
- **Suppressed** when chunk text is a tool-only placeholder (e.g. `Reading workspace file…`, `Searching the web…`). See `_is_tool_preamble_text()` in `handler.py` and `isToolPreambleText()` in `frontend-v2/src/lib/toolPreamble.ts`
- Optional `metadata` from `TokenBudgetTracker`:

```json
{
  "tokens_used": 12,
  "budget_remaining": 3988
}
```

- `tokens_used` — cumulative tokens consumed (estimated as `len(text) // 4` per chunk)
- `budget_remaining` — tokens remaining in allocated budget
- `metadata` is optional; frontend code not handling it continues to work

#### `assistant.message`

```json
{
  "type": "assistant.message",
  "message": {
    "type": "ai | tool | human | ...",
    "content": "string",
    "tool_calls": [],
    "tool_name": "string",
    "tool_call_id": "string"
  }
}
```

- `AIMessage` with `tool_calls` forwarded for tool-call UI rendering
- Tool-only placeholder text (preamble) is **not** sent as `assistant.message` when the turn is dominated by tool calls — UI relies on `tool_execution` instead
- Tool lifecycle/output via `tool_execution` events (not `message`)

#### `error`

```json
{ "type": "error", "content": "string" }
```

Contract (tested via `test_ws_error_event_shape`):
- `type` must equal `"error"`
- `content` must be a non-empty string

#### `tool_execution`

Running:

```json
{
  "type": "tool_execution",
  "status": "running",
  "tool_name": "string",
  "tool_call_id": "string|null",
  "input": "string|null"
}
```

Finished:

```json
{
  "type": "tool_execution",
  "status": "success|error",
  "tool_name": "string",
  "tool_call_id": "string|null",
  "output": "string|null",
  "error": "string|null",
  "duration": 1.23,
  "chart_artifact": {
    "filename": "chart.html",
    "url": "/api/files/chart.html?project_id=default",
    "kind": "interactive|static",
    "mime_type": "text/html"
  }
}
```

`chart_artifact` is optional — attached when `notebook_run` saves a chart file. Prefer inline `owlynn-embed` fences in the assistant reply (see below); timeline `chart_embed` items remain as a fallback.

Derived from `AIMessage.tool_calls` + `ToolMessage` outputs. Tool outputs normalized into `tool_execution` events to avoid duplicate/misaligned chat message rendering.

`status` is derived server-side via `_tool_status_from_content()`:

- `error` — output starts with `Error:` / `error:` or known failure prefixes (`execution error`, `traceback`, etc.)
- `success` — otherwise (including long PDF text that mentions “error” mid-body)

Do **not** substring-match `"error:"` inside document content; that caused false ERROR cards on successful `read_workspace_file` reads. See [`changes/tool-preamble-read-file-fix/CHANGELOG.md`](changes/tool-preamble-read-file-fix/CHANGELOG.md).

#### Inline interactive markdown (assistant replies)

Assistant `content` may include fenced blocks rendered as inline widgets in `MessageContent` (`frontend-v2/src/lib/interactiveBlocks/`):

| Fence lang | Purpose |
|------------|---------|
| `owlynn-quiz` | Clickable multiple-choice check |
| `owlynn-steps` | Accordion step reveal |
| `owlynn-callout` | Tip / warning / note box |
| `owlynn-embed` | Inline chart or image (`{"type":"chart\|image","url":"..."}`) |
| `owlynn-cell` | Python cell display; optional Run (`POST /api/notebook/run` with loopback token `X-Owlynn-Run-Token` from `GET /api/local-run-token`) |
| `mermaid` | Client-side diagram |

Agents should call `render_interactive_block(block_type, payload)` to validate JSON and receive the fence string. Schemas live in `templates/interactive/`.

Native `<details><summary>` collapsibles are also supported in sanitized markdown.

#### `model_info`

```json
{
  "type": "model_info",
  "model": "string",
  "swapping": true | false,
  "token_usage": {
    "prompt_tokens": 150,
    "completion_tokens": 320,
    "prompt_cache_hit_tokens": 120,
    "prompt_cache_miss_tokens": 30,
    "reasoning_tokens": 0,
    "context_breakdown": {
      "max_context": 1048576,
      "categories": { "system": 1200, "conversation": 8000, "tools": 35000, "output": 320, "reasoning": 0 },
      "category_pct": { "system": 0.1, "conversation": 0.8, "tools": 3.3, "output": 0.03, "reasoning": 0 },
      "total_used": 44620,
      "used_pct": 4.3
    }
  },
  "fallback_chain": [
    {
      "model": "large-cloud",
      "status": "failed",
      "reason": "API key invalid",
      "duration_ms": 42
    },
    {
      "model": "large-cloud",
      "status": "success",
      "reason": "fallback",
      "duration_ms": 8
    }
  ]
}
```

Sent after `complex_llm` or `simple` node completes when `model_used` is present (or `fallback_chain` is present without `model_used`).

| Field | Description |
|-------|-------------|
| `model` | Model that produced the response (e.g. `"large-cloud"`, `"small-local"`). Route `complex-cloud` maps to `"large-cloud"` in `model_info`. |
| `swapping` | Whether a model swap occurred |
| `token_usage` | Optional prompt/completion counts; cloud turns may include cache fields and `context_breakdown` (system/conversation/tools/output/reasoning vs `max_context`) — see [`changes/cloud-usage-context-chip/CHANGELOG.md`](changes/cloud-usage-context-chip/CHANGELOG.md) |
| `fallback_chain` | Optional ordered list of model attempts. Always has ≥1 entry and exactly one with `status == "success"`. Entries are chronological |

Populated by `complex_llm_node` and `simple_node` in every node output.

#### `router_info`

```json
{
  "type": "router_info",
  "metadata": {
    "route": "complex-cloud",
    "confidence": 0.87,
    "reasoning": "Code generation task detected",
    "swap_decision": "not_needed",
    "swap_from": "default",
    "swap_to": null,
    "classification_source": "llm_classifier",
    "token_budget": 4096,
    "cloud_available": true,
    "features": {
      "has_images": false,
      "task_category": "coding",
      "estimated_tokens": 320,
      "web_intent": false
    }
  }
}
```

Sent after router node completes, before the first `chunk` event.

| Field | Values |
|-------|--------|
| `route` | `"simple"`, `"complex-cloud"` |
| `confidence` | [0.0, 1.0] |
| `classification_source` | `"keyword_bypass"`, `"deterministic"`, `"llm_classifier"`, `"hitl"` |
| `swap_decision` | `"kept"`, `"swapped"`, `"not_needed"` |
| `features` | Never contains raw message text |

Telemetry data source: `src/agent/nodes/router.py` — `router_node()` populates `router_metadata` on every return path via `_build_router_metadata()`.

#### `token_budget_update` (planned / not yet implemented)

```json
{
  "type": "token_budget_update",
  "used": 1024,
  "total": 4096,
  "remaining": 3072,
  "percent": 0.25
}
```

> **Status:** Planned — not yet implemented. The server does not currently emit this event.

| Field | Description |
|-------|-------------|
| `used` | Total tokens consumed during streaming |
| `total` | Allocated budget (from router's `token_budget`) |
| `remaining` | `max(0, total - used)` |
| `percent` | Fraction of budget consumed (can exceed 1.0) |

#### `cloud_budget_warning` (planned / not yet implemented)

```json
{
  "type": "cloud_budget_warning",
  "used": 420000,
  "limit": 500000,
  "percent": 84.0,
  "level": "warning"
}
```

> **Status:** Planned — not yet implemented. The server does not currently emit this event.

| Level | Trigger |
|-------|---------|
| `"info"` | 50% of limit |
| `"warning"` | 80% of limit |
| `"critical"` | 95% of limit |

Each level emitted at most once per session. Levels emitted in order: `"info"` → `"warning"` → `"critical"`. If `cloud_daily_token_limit` is 0 or negative, no warnings are emitted.

#### `memory_updated`

```json
{
  "type": "memory_updated",
  "thread_id": "abc-123"
}
```

Sent after `memory_write_node` saves new data and invalidates the memory context cache.

#### `context_summarized`

```json
{
  "type": "context_summarized",
  "summary": "bullet-point summary text...",
  "takeaways": ["Decision: use React for UI", "User prefers concise answers"],
  "messages_compressed": 12,
  "tokens_freed": 4500
}
```

Emitted when `auto_summarize_node` compresses older conversation history. Triggered when `active_tokens > 85%` of `context_window`.

Sent at `on_chain_end` for the `auto_summarize` node. When no summarization needed, no event is emitted.

#### `file_status`

```json
{ "type": "file_status", "name": "string", "status": "processed | deleted" }
```

Sent by `notify_file_processed()` to trigger UI refresh of the workspace file panel.

#### `browser.page_context`

Broadcast when the user sends the active browser tab via Owlynn Browser Bridge (context menu or popup). **Does not auto-send a chat message** — frontend prefills the composer only.

```json
{
  "type": "browser.page_context",
  "url": "string",
  "title": "string",
  "text": "string",
  "selection": "string"
}
```

See [`changes/browser-extension-active-tab/CHANGELOG.md`](changes/browser-extension-active-tab/CHANGELOG.md).

Sent by `notify_file_processed()` to trigger UI refresh of the workspace file panel.

#### `interrupt` (HITL)

```json
{
  "type": "interrupt",
  "interrupts": [
    {
      "type": "scope_clarification_required | plan_review_required | security_approval_required | ask_user",
      "title": "string",
      "stated_intent": "string (optional)",
      "conversation_snippet": "string (optional)",
      "pitfalls": ["string"],
      "questions": [
        {
          "id": "string",
          "question": "string",
          "choices": [{ "label": "string" }],
          "allows_user_input": true | false
        }
      ],
      "planned_actions": [{ "tool": "string", "summary": "string" }],
      "sensitive_tool_calls": [...]
    }
  ]
}
```

New interrupt types added in HITL improvement branch:

| Type | When emitted | Response event |
|------|-------------|----------------|
| `scope_clarification_required` | Vague build/create request detected | `ask_user_response` with structured `answers` |
| `plan_review_required` | Sensitive tool plan needs review | `plan_review_response` with `approved` bool |
| `security_approval_required` | Policy blocks sensitive tool | `security_approval` with `approved` bool |
| `ask_user` | Router or mid-task clarification | `ask_user_response` with `answer` |

Enriched fields now include `conversation_snippet`, `stated_intent`, `affected_resources`, and `clarification_reason` where available.

### TTS Runtime Event (Desktop Channel)

Electron main process emits `runtime-event` IPC from `frontend-v2/electron/main.ts` (consumed as `owlynn://runtime-event` in `App.tsx`):

```json
{ "type": "voice.tts_state", "speaking": true | false, "utterance_id": "string" }
```

Consumed in `frontend-v2/src/App.tsx`.

### Consolidated Settings (`GET /api/unified-settings`)

Returns all user-facing settings merged from `GET /api/profile` and `GET /api/advanced-settings`:

```json
{
  "name": "string",
  "preferred_language": "en",
  "response_style": "concise",
  "small_llm_base_url": "http://127.0.0.1:1234/v1",
  "small_llm_model_name": "minicpm5-1b",
  "llm_base_url": "http://127.0.0.1:1234/v1",
  "llm_model_name": "gemma-4-e2b-heretic-uncensored-mlx",
  "cloud_llm_base_url": "https://api.deepseek.com/v1",
  "cloud_llm_model_name": "deepseek-v4-flash",
  "deepseek_api_key": "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022",
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 2048,
  "top_k": 40,
  "streaming_enabled": true,
  "show_thinking": false,
  "show_tool_execution": true,
  "lm_studio_fold_system": true,
  "cloud_escalation_enabled": true,
  "cloud_anonymization_enabled": true,
  "router_hitl_enabled": true,
  "router_clarification_threshold": 0.6,
  "custom_sensitive_terms": [],
  "redis_url": "redis://localhost:6379",
  "cloud_daily_token_limit": 500000,
  "cloud_budget_warning_thresholds": [0.5, 0.8, 0.95]
}
```

| Note | Detail |
|------|--------|
| API key masking | `deepseek_api_key` always masked (`\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022` when present, `""` when absent) |
| Default limits | `cloud_daily_token_limit` defaults to 500,000; `cloud_budget_warning_thresholds` defaults to `[0.5, 0.8, 0.95]` |
| Backward compatibility | `GET /api/profile` and `GET /api/advanced-settings` unchanged |
| Error fallback | If `get_profile()` raises exception, returns error response; frontend falls back to individual endpoints |

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Single persistent WebSocket per thread | Real-time streaming for chat UX | Connection management complexity |
| Structured router_info event | Frontend visibility into routing decisions | Additional WS event to handle |
| fallback_chain in model_info | Debug unexpected fallbacks | Extra payload per model_info event |
| ask_user_response preserves structured types | Router can ask structured questions | Frontend must handle object answers |

## Testing

```bash
pytest tests/test_websocket_event_contract.py -v
pytest tests/test_websocket_model_key_updates.py -v
cd frontend-v2 && npx vitest run
```

## Configuration

| Profile Field | Type | Default |
|---------------|------|---------|
| `cloud_daily_token_limit` | integer | `500000` |
| `cloud_budget_warning_thresholds` | list | `[0.5, 0.8, 0.95]` |
| `router_clarification_threshold` | float | `0.6` |
| `router_hitl_enabled` | boolean | `true` |
| `cloud_anonymization_enabled` | boolean | `true` |
| `redis_url` | string | `redis://localhost:6379` |
| `deepseek_api_key` | string | `""` |

## Related

- [`docs/API_REFERENCE.md`](API_REFERENCE.md) — REST endpoint reference
- [`docs/architecture/overview.md`](architecture/overview.md) — system architecture
- [`src/api/ws/handler.py`](../src/api/ws/handler.py) — WebSocket handler implementation

## Last updated

2026-06-19 — Qwen3-VL-4B vision proxy replaces Florence-2; `complex-cloud` → `large-cloud` in `model_info`
