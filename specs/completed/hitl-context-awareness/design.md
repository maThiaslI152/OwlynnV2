# Design: Context-Aware HITL Prompts

> **Purpose:** Define how the requirements will be implemented. Written in Plan mode after design is approved. Must be approved via AskQuestion `design-review` popup before proceeding to tasks.

## Architecture Overview

Two changes: (1) Backend — wire `enrich_interrupt()` into `security_proxy.py`, improve the `stated_intent` field in `context.py`, and include tool arguments in the security_approval payload. (2) Frontend — render the already-parsed `conversationSnippet` and `affected_resources` fields in `HitlPromptCard.tsx`. All infrastructure already exists; we're connecting the dots.

## System Diagram

```mermaid
flowchart LR
  subgraph Backend
    SP[security_proxy.py]
    PR[plan_review.py]
    SC[scope_clarify.py]
    CX[context.py]
  end
  subgraph Frontend
    HPC[HitlPromptCard.tsx]
  end

  SP -.->|No enrich_interrupt() call| CX
  PR -->|enrich_interrupt| CX
  SC -->|enrich_interrupt| CX
  CX -->|conversation_snippet, stated_intent, affected_resources| HPC
  HPC -.->|conversationSnippet parsed but NOT rendered| UI
```

**Changes:**
- Red arrow: `security_proxy.py` → call `enrich_interrupt()` (currently missing)
- Dotted: frontend → render `conversationSnippet` + tool args + `affected_resources` (currently hidden)

## API / Interface Design

### Backend: Enriched Interrupt Payload Shape

**security_proxy.py** will produce (new fields in **bold**):

```json
{
  "type": "security_approval_required",
  "title": "Approve: {tool_name} on {path}?",
  "reason": "{conversation-derived explanation}",
  "sensitive_tool_calls": [{ "name": "...", "args": {...}, ... }],
  "safe_tool_calls": [...],
  "risk_categories": [...],
  "conversation_snippet": "User: ...\nOwlynn: ...",
  "stated_intent": "Owlynn wants to create a file named report.txt summarizing the data",
  "affected_resources": ["/path/to/report.txt"],
  "tool_args": { "path": "/path/to/report.txt", "content": "...", ... }
}
```

### Frontend: HITL Card Display Changes

| Current | New |
|---------|-----|
| `{title: "Sensitive tool request blocked pending approval"}` | `{title: "Approve write_workspace_file on report.txt?"}` |
| No conversation snippet visible | Shows `conversationSnippet` as a collapsed/expandable "Context" section |
| Tool name only (`<code>write_workspace_file</code>`) | Tool name + key arguments rendered as a table |
| `affected_resources` not rendered | Shows "Affected files" list if present |

## Data Model

No changes to data models. All changes are to payload structures and UI rendering.

| Entity | Current State | Change |
|--------|--------------|--------|
| `security_proxy_node()` payload | No `enrich_interrupt()` call, no tool_args, generic title/reason | Add `enrich_interrupt()`, add `tool_args`, dynamic title/reason |
| `build_hitl_context()` output | `stated_intent` = "Owlynn wants to {last_ai_content}" — weak | Improve to extract intent from tool call name + args |
| `HitlPromptViewModel` | `conversationSnippet` parsed but unused | Render in all 4 card variants |
| `HitlPromptViewModel` | No `toolArgs` field | Add `toolArgs` from `sensitive_tool_calls[0].args` |
| `HitlPromptViewModel` | No `affectedResources` field | Add from backend payload |

## Component / Module Breakdown

| Component | Responsibility | Files |
|-----------|---------------|-------|
| Context builder | Improve `stated_intent` generation; ensure tool args passed through | `src/agent/hitl/context.py` |
| Security proxy node | Call `enrich_interrupt()`; add tool_args to payload; dynamic title/reason | `src/agent/nodes/security_proxy.py` |
| HITL card component | Render conversation snippet, tool args, affected resources | `frontend-v2/src/components/HitlPromptCard.tsx` |
| HITL card parser | Add `toolArgs`, `affectedResources` to view model | `frontend-v2/src/components/HitlPromptCard.tsx` |

## Detailed Design: Backend

### 1. `security_proxy.py` — enrich + dynamic title/reason

```python
# Current (line 182-191):
decision = interrupt({
    "type": "security_approval_required",
    "title": "Sensitive tool request blocked pending approval",
    "reason": "One or more tool calls are marked sensitive by policy.",
    ...
})

# New:
from src.agent.hitl.context import enrich_interrupt

payload = enrich_interrupt({
    "type": "security_approval_required",
    "title": _build_title(sensitive_calls),
    "reason": _build_reason(sensitive_calls),
    "sensitive_tool_calls": sensitive_calls,
    "safe_tool_calls": safe_calls,
    "risk_categories": ...,
    "tool_args": sensitive_calls[0].get("args", {}) if sensitive_calls else {},
}, state)
decision = interrupt(payload)
```

Where `_build_title()` produces e.g. `"Approve write_workspace_file on report.txt?"` and `_build_reason()` produces a plain-language explanation.

### 2. `context.py` — better `stated_intent`

```python
# Current:
intent = f"Owlynn wants to {truncated_ai_content}"

# New:
intent = _build_intent_from_tool_calls(messages)
# Produces: "Owlynn wants to create a file named report.txt"
# or: "Owlynn wants to run a shell command: ls -la /tmp"
```

### 3. `plan_review.py` / `scope_clarify.py`

Already use `build_hitl_context()`. Ensure they also include the tool args in their payloads (not just the names).

## Detailed Design: Frontend

### `HitlPromptCard.tsx`

1. **Add to `HitlPromptViewModel`:**
   - `conversationSnippet: string` — already exists, just needs JSX
   - `toolArgs: Record<string, string>` — new
   - `affectedResources: string[]` — new

2. **Update `parseHitlPrompt()`:**
   - Extract `toolArgs` from `sensitive_tool_calls[0]?.args` for `security_approval`
   - Extract `affected_resources` from payload

3. **Render in JSX:**
   - `conversationSnippet` → collapsed `<details>` section "Conversation context" at the top of the card
   - `toolArgs` → table "Arguments" below tool name for `security_approval`
   - `affectedResources` → list "Affected files" for `security_approval` and `plan_review`

## Error Handling Strategy

- If `enrich_interrupt()` fails (e.g., missing messages), fall back to the current generic payload
- If frontend receives null/empty context fields, don't render those sections (graceful degradation)
- `stated_intent` extraction from tools: if unrecognized tool, fall back to "A tool call requires approval"

## Security Considerations

- Conversation snippets are already in the user's chat history — adding them to the HITL card doesn't expose new data
- Tool args may contain sensitive data (API keys, passwords) — but they're already visible in the conversation via tool execution output. The HITL card is shown *before* execution, so this is the right time to review them.

## Trade-offs and Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Use existing `enrich_interrupt()` in security_proxy | Zero new infrastructure; just wire a call that already exists | Building a custom payload — duplicates existing work |
| Collapsed `<details>` for conversation context | Keeps the card compact while providing context on demand | Always-expanded — too much visual noise |
| Dynamic title from tool name + primary arg | Immediately answers "what is this about?" at a glance | Keeping generic title — defeats the purpose |
| Improve `stated_intent` from tool calls + args | More accurate than last-AI-message heuristic | Running an extra LLM call — too slow |

## Open Questions

- [ ] For `_build_intent_from_tool_calls()`: how to map arbitrary tool names to human-readable descriptions? Use a lookup map for known tools, fall back to raw name for unknown ones?

## References

- `requirements.md` — acceptance criteria to satisfy
- `plan_ref: .cursorplan/active/hitl-context-awareness/plan.md`
- `specs/completed/hitl-auto-search-deep-fetch/` — prior HITL changes
- `frontend-v2/src/components/HitlPromptCard.tsx` — HITL card renderer
- `src/agent/hitl/context.py` — `build_hitl_context()` + `enrich_interrupt()`
- `src/agent/nodes/security_proxy.py` — interrupt payload construction

## Approval

- `design-review` AskQuestion: **approved** (2026-06-01)
