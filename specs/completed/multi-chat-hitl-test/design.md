# Design: Multi-Chat HITL & Memory Isolation Test

> **Purpose:** Define how the requirements will be implemented. Written in Plan mode after requirements are approved.

## Architecture Overview

Extend the existing Playwright E2E test harness to run multi-chat scenarios that verify: (1) normal 20+ turn conversations work, (2) memory is isolated between chat sessions, (3) both HITL trigger types fire correctly and stay scoped to their originating session. Verification uses the history JSON API and audit log inspection — no product code changes needed, only new test scripts.

## System Diagram

```mermaid
flowchart TD
  subgraph TestScript
    TC[Test Controller]
    PW[Playwright Browser]
    APIClient[HTTP API Client]
  end

  subgraph Owlynn
    WS[WebSocket /ws/chat/{thread_id}]
    HistoryAPI[GET /api/history/{thread_id}]
    AuditLog[audit.jsonl / agent.hitl channel]
    Checkpointer[Redis / MemorySaver]
  end

  TC --> PW
  TC --> APIClient
  PW --> WS
  APIClient --> HistoryAPI
  APIClient --> AuditLog
  HistoryAPI --> Checkpointer
```

## Test Script Structure

### File: `tests/test_multi_chat_hitl_e2e.py`

Single test file with 4 test functions:

| Test | Maps to | Description |
|------|---------|-------------|
| `test_medium_conversation_20_turns` | AC-1 | Opens chat A, sends 20+ messages, asserts coherent responses and context retention |
| `test_memory_isolation_between_chats` | AC-2, AC-6 | Opens chat A (5+ turns), opens chat B, fetches history JSON for both — asserts zero cross-chat content in B |
| `test_tool_call_hitl_in_chat` | AC-3, AC-5 | Triggers a sensitive tool call in chat A, verifies HITL prompt appears, confirms it, verifies no HITL in chat B |
| `test_prompt_based_hitl_in_chat` | AC-4, AC-5 | Triggers scope_clarification in chat A (via underspecified build request), verifies HITL prompt, confirms, checks chat B untouched |

### Shared Fixtures (`conftest.py` or fixture module)

- `backend_url` — `http://127.0.0.1:8000`
- `browser_context` — Playwright Chromium context
- `audit_log_path` — resolved from `OWLYNN_AUDIT_LOG_DIR` or default `~/.owlynn/logs/audit.jsonl`

### Helper Functions

| Function | Signature | Purpose |
|----------|-----------|---------|
| `create_chat()` | `→ (project_id, thread_id)` | Creates a new project + chat via API |
| `send_message(page, message)` | `→ last_assistant_msg` | Types into composer, sends, waits for response, returns last assistant message text |
| `switch_to_chat(page, thread_id)` | `→ None` | Clicks chat in sidebar, waits for WS connect |
| `fetch_history(thread_id)` | `→ list[dict]` | Calls `GET /api/history/{thread_id}`, returns message array |
| `trigger_tool_hitl(page)` | `→ hitl_payload` | Sends a message that triggers a sensitive tool (e.g., "create a file named test.txt with content 'hello'"), waits for HitlPromptCard, returns the interrupt payload |
| `trigger_prompt_hitl(page)` | `→ hitl_payload` | Sends an underspecified build request, waits for HitlPromptCard, returns the interrupt payload |
| `confirm_hitl(page)` | `→ None` | Clicks "Approve" / submits confirmation on the HitlPromptCard |
| `assert_no_cross_reference(history_a, history_b)` | `→ None` | Scans chat B history for any text from chat A's messages — asserts none found |
| `fetch_audit_entries(session_id, channel)` | `→ list[dict]` | Reads JSON lines from audit log filtered by session_id and channel |

### HITL Trigger Strategy

**Tool-call HITL (security_proxy):**
- Send a message like: "Create a new file called hello.txt with the content 'world'"
- This triggers `security_approval_required` interrupt (file write is a sensitive tool)
- Assert: HitlPromptCard appears with sensitive_tool_calls metadata
- Assert: interrupt payload logged to `agent.hitl` channel with thread_id

**Prompt-based HITL (scope_clarify):**
- Send a message like: "Build me a web app" (deliberately underspecified)
- This triggers `scope_clarification_required` interrupt
- Assert: HitlPromptCard appears with multi-choice questions
- Assert: interrupt payload logged to `agent.hitl` channel with thread_id

### Memory Isolation Verification

For each test that involves multiple chats:

1. Send 5+ turns in chat A (include distinctive content like "CHAT_A_SECRET_TOKEN")
2. Switch to chat B, send a greeting
3. Fetch history JSON for both chats via API
4. Assert: `"CHAT_A_SECRET_TOKEN"` not present in any message field in chat B's history
5. Assert: audit log entries for chat A's messages have `session_id == thread_a`, entries for chat B have `session_id == thread_b` — no cross-contamination

### Error Handling / Edge Cases

- **HITL simultaneous triggers**: If both chats could trigger HITL concurrently, test that each resume resolves independently (cover in soak variant)
- **History API empty**: Handle case where `GET /api/history/{thread_id}` returns `[]` for fresh chats
- **Audit log missing**: Graceful skip if audit log not found (log only warning, don't fail the memory test)
- **HITL timeout**: If HITL prompt doesn't appear within 30s, fail with clear error about HITL not triggering

## Data Model (test-specific)

No new persistence. Tests read from:
- `GET /api/history/{thread_id}` → `list[{type, content, role, tool_calls?, ...}]`
- `audit.jsonl` → `JSON lines[{channel, event, thread_id, timestamp, data}]`

## Component / Module Breakdown

| Component | Responsibility | Files |
|-----------|---------------|-------|
| Test file | All 4 test functions + helper imports | `tests/test_multi_chat_hitl_e2e.py` |
| Fixtures | Shared Playwright context, API client, audit log path | `tests/test_multi_chat_hitl_e2e.py` (same file) |
| Helpers utility | Chat creation, message send, history fetch, audit search | `tests/test_multi_chat_hitl_e2e.py` (same file) |

All test logic in one file for simplicity — existing Playwright tests follow this pattern.

## Error Handling Strategy

- All tests use `async with` for Playwright page/browser context cleanup
- API calls use `httpx.AsyncClient` timeout of 30s
- HITL detection uses `page.wait_for_selector('[data-testid="hitl-prompt-card"]', timeout=30000)`
- Assertion failures produce clear messages: `f"Chat B history contains content from chat A: {cross_refs}"`
- Test teardown: close all pages, delete test projects via API

## Security Considerations

- Tests run against localhost — no external data exposure
- Test projects are cleaned up after run (delete via API)
- No credentials/tokens in test scripts

## Trade-offs and Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Single test file | Existing Playwright tests follow this pattern; keeps imports/helpers local | Separate files per test — more boilerplate, harder to share fixtures |
| Playwright (Python) over npm Playwright | Already in requirements, existing harness uses it | npm Playwright would require new dep + setup duplication |
| Audit log file read vs. API | Audit log is JSONL file, no query API exists; direct file read is simplest | Adding audit API endpoint — scope creep, product code change |
| `data-testid` selectors | Stable against UI text changes | Text-based selectors — brittle with i18n/rewording |

## Open Questions

- [ ] Does the frontend expose `data-testid` attributes on HitlPromptCard or do we need a small frontend test-id addition? (Check existing frontend test files for test-id patterns)
- [ ] What's the default audit log path resolution — always `~/.owlynn/logs/audit.jsonl` or overridable? (Check `src/config/audit_log.py`)

## References

- `requirements.md` — acceptance criteria AC-1 through AC-6
- `plan_ref: .cursorplan/active/multi-chat-hitl-test/plan.md`

## Approval

- `design-review` AskQuestion: **approved** (2026-05-31)
