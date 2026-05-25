---
last_verified: 2026-05-26
auto_generated: false
---

# API Reference

Backend endpoints exposed by `src/api/server.py`. Written for developers modifying backend behavior.

## Overview

Documents all REST endpoints and WebSocket entry point. Consumed by `frontend-v2`.

## Entry Points

```text
src/api/server.py              # All endpoint implementations
frontend-v2/src/lib/wsClient.ts # WebSocket client consumer
frontend-v2/src/App.tsx         # REST API consumer
```

## Architecture

Base URL: `http://<host>:8000`

### Static/UI

- `GET /` — serves `frontend-v2/dist/index.html`

## API

### Health

`GET /api/health`
- Response: `{ "status": "ok", "agent": "ready" | "initializing" }`

### Usage

`GET /api/usage`
- Returns cumulative session token usage for cloud (DeepSeek) API calls
- Response: `{ "prompt_tokens": 5000, "completion_tokens": 2000, "total_tokens": 7000, "session_id": "..." }`

### Chat (WebSocket)

`WS /ws/chat/{thread_id}` — see `docs/CHAT_PROTOCOL.md` for payload and event contract

### Profile

`GET /api/profile`
- Returns merged profile from `data/user_profile.json`

`POST /api/profile`
- Updates profile keys from request body using `update_profile(field, value)`
- Runtime-impacting model fields (`small_*`, `medium_models`, `llm_*`, `large_*`, `cloud_*`, `deepseek_api_key`) trigger `LLMPool.clear()` so subsequent runs pick up new keys without restart
- Response:
  - Full updated profile on success
  - Partial-success envelope on field failures:

```json
{
  "status": "partial_success",
  "profile": { "...": "..." },
  "updated_fields": ["name", "medium_models"],
  "errors": { "unknown_field": "Unknown profile field 'unknown_field'" }
}
```

### System Prompt / Persona

`GET /api/system-settings`
- Response: `{ "system_prompt": "...", "custom_instructions": "...", "name": "...", "tone": "..." }`

`POST /api/system-settings`
- Body keys: `system_prompt`, `custom_instructions`, `name`, `tone`
- Response: `{ "status": "ok" | "error", "message": "..." }`

### Memory Settings

`GET /api/memory-settings`
- Response: `{ "short_term_enabled": true | false, "long_term_enabled": true | false }`

`POST /api/memory-settings`
- Body keys: `short_term_enabled`, `long_term_enabled`
- Response: `{ "status": "ok" | "error", "message": "..." }`

### Advanced Settings

`GET /api/advanced-settings`
- Response:

```json
{
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 2048,
  "top_k": 40,
  "streaming_enabled": true,
  "show_thinking": false,
  "show_tool_execution": true,
  "cloud_escalation_enabled": true,
  "cloud_anonymization_enabled": true,
  "router_hitl_enabled": true,
  "router_clarification_threshold": 0.6,
  "custom_sensitive_terms": [],
  "redis_url": "redis://localhost:6379",
  "lm_studio_fold_system": true
}
```

`POST /api/advanced-settings`
- Body keys: `temperature`, `top_p`, `max_tokens`, `top_k`, `streaming_enabled`, `show_thinking`, `show_tool_execution`, `cloud_escalation_enabled`, `cloud_anonymization_enabled`, `router_hitl_enabled`, `router_clarification_threshold`, `custom_sensitive_terms`, `redis_url`, `lm_studio_fold_system`
- Response: `{ "status": "ok" | "error", "message": "..." }`

### Unified Settings

`GET /api/unified-settings`
- Merged profile + advanced settings payload for frontend bootstrap
- Includes: profile identity, LLM config, all advanced settings, cloud budget defaults, masked `deepseek_api_key`

### Short-Term Memory (JSON)

`GET /api/memories` → list raw stored memories

`POST /api/memories`
- Body: `{ "fact": "..." }`

`DELETE /api/memories`
- Body: `{ "fact": "..." }`

### Long-Term Memory (Mem0 + Qdrant)

`GET /api/mem0/search?query=<string>&limit=<int>&project_id=<string>`
- Searches Mem0/Qdrant vector store. If `project_id` provided, scopes to that project's memory space
- Response: `{ "status": "ok", "memories": [...], "count": <int> }`

`GET /api/mem0/count?project_id=<string>`
- Response: `{ "status": "ok", "count": <int>, "user_id": "..." }`

`POST /api/mem0/delete`
- Body: `{ "memory_id": "..." }`

`POST /api/mem0/clear`
- Body: `{ "user_id": "owner" }` (default `"owner"`)
- Clears all memories for a user_id

`POST /api/mem0/reset`
- Resets ALL Mem0 memories (global)

### Personal Assistant Data

`GET /api/topics` → `{ "status": "ok", "topics": [...] }`

`GET /api/interests` → `{ "status": "ok", "interests": [...] }`

`GET /api/conversations?limit=<int>` → `{ "status": "ok", "conversations": [...] }`

`GET /api/memory-context` → `{ "status": "ok", "memory_context": "..." }`

`POST /api/topics/track`
- Body: `{ "topic": "string", "category": "string" }`

`POST /api/interests/update`
- Body: `{ "interests": { "<interest_name>": <count>, ... } }`

### Workspace Files (Project-Scoped)

Project-scoping handled by `get_project_workspace(project_id)` with path-prefix checks.

`GET /api/files?sub_path=<string>&project_id=<string>`
- Lists files/folders including `status` field (`processed` if cached, otherwise `idle`)

`GET /api/files/{filename}?sub_path=<string>&project_id=<string>`
- `FileResponse` serving raw file bytes

`POST /api/upload?sub_path=<string>&project_id=<string>`
- Multipart upload: `file: UploadFile`

`DELETE /api/files/{filename}?sub_path=<string>&project_id=<string>`
- Deletes file/folder and cached `.processed/<name>.{txt,md}`

`POST /api/files/{filename}/rename`
- Body: `{ "new_name": "...", "sub_path": "...", "project_id": "..." }`

`POST /api/files/{filename}/move`
- Body: `{ "current_sub_path": "...", "target_sub_path": "...", "project_id": "..." }`

`POST /api/folders`
- Body: `{ "name": "...", "sub_path": "...", "project_id": "..." }`

### Projects

`GET /api/projects`

`POST /api/projects`
- Body: `{ "name": "...", "instructions": "..." }`

`GET /api/projects/{project_id}`

`POST /api/projects/{project_id}/chats`
- Body: `{ "id": "...", "name": "..." }`

`PUT /api/projects/{project_id}/chats/{chat_id}`

`DELETE /api/projects/{project_id}/chats/{chat_id}`

`DELETE /api/projects/{project_id}`

### Tool Discovery

`GET /api/tools`
- Returns list of tool metadata derived from `src/agent/tool_sets.py`

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| WebSocket for chat, REST for everything else | Streaming needs WS, CRUD fits REST | Two transport protocols |
| Partial-success on profile update | Don't fail entire update for one bad field | More complex response parsing |
| LLMPool.clear() on profile change | Pick up new model keys without restart | All cached model instances dropped |
| Masked API key in unified settings | Never expose raw key in API responses | Frontend can't display full key |

## Testing

```bash
pytest tests/test_websocket_event_contract.py -v
pytest tests/test_websocket_model_key_updates.py -v
pytest tests/test_frontend_backend_alignment.py -v
```

## Configuration

WebSocket request payload keys parsed in `websocket_endpoint()` and passed into agent state:

| Key | Field |
|-----|-------|
| `mode` | `tools_on` / `tools_off` |
| `web_search_enabled` | Boolean |
| `response_style` | `normal` / `learning` / `concise` / `explanatory` / `formal` |
| `project_id` | Project identifier string |

### User Profile Fields (`data/user_profile.json`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `cloud_llm_base_url` | string | `"https://api.deepseek.com/v1"` | DeepSeek cloud API base URL |
| `cloud_llm_model_name` | string | `"deepseek-chat"` | Cloud model name |
| `deepseek_api_key` | string | `""` | DeepSeek API key (env var `DEEPSEEK_API_KEY` takes priority) |
| `medium_models` | object | `{"default": "gemma-4-e4b-uncensored-hauhaucs-aggressive", ...}` | M-tier model key mapping |
| `cloud_escalation_enabled` | boolean | `true` | Allow routing to cloud |
| `cloud_anonymization_enabled` | boolean | `true` | Scrub PII before cloud API calls |
| `custom_sensitive_terms` | list | `[]` | Additional terms to anonymize |
| `router_hitl_enabled` | boolean | `true` | Allow router to ask clarifying questions |
| `router_clarification_threshold` | float | `0.6` | Confidence threshold for clarification |
| `redis_url` | string | `"redis://localhost:6379"` | Redis URL for checkpointing |
