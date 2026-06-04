# Requirements: Context-Aware HITL Prompts

> **Purpose:** Define what the change must do. Written in Plan mode before design. Must be approved via AskQuestion `requirements-review` popup before proceeding to design.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | User | the HITL approval prompt to show the conversation context that led to the tool call | I can make an informed decision about whether to approve or deny |
| US-2 | User | the HITL prompt to explain why this tool is being called in relation to my request | I understand the relevance instead of getting a generic security warning |
| US-3 | User | to see the tool call arguments in the HITL prompt | I know exactly what files or resources will be affected |

## Acceptance Criteria (EARS format)

> EARS = Easy Approach to Requirements Syntax: "When {condition}, the system shall {behavior}".

| ID | Criterion |
|----|-----------|
| AC-1 | When a security_approval HITL is shown, the system shall include the user's recent message and the LLM's stated intent in the prompt title/reason (not just generic boilerplate). |
| AC-2 | When a security_approval HITL is shown, the system shall include the tool call name and its arguments in the card body. |
| AC-3 | When a plan_review HITL is shown, the system shall include the conversation snippet (last user + assistant message) in the card body. |
| AC-4 | When a scope_clarify HITL is shown, the system shall include the conversation snippet in the card body. |
| AC-5 | When any HITL is shown, the system shall replace generic titles ("Sensitive tool request blocked pending approval") with context-aware text derived from the conversation. |
| AC-6 | When an interrupt payload is built in security_proxy, the system shall call `enrich_interrupt()` to attach context fields. |
| AC-7 | The frontend HITL card shall render `conversation_snippet` and `affected_resources` fields (currently parsed but not displayed). |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Performance | Context extraction must add < 50ms overhead (no extra LLM calls) |
| NFR-2 | Security | Conversation context must not leak sensitive data already in the thread |

## Edge Cases and Error States

- When conversation is very long (>100 messages): truncate to last 3-5 exchanges
- When user message is very long: truncate to 200 chars for display
- When tool call has no clear relationship to conversation: show raw tool name and args

## Out of Scope

- Changes to the HITL decision logic (when it fires)
- Visual/UI redesign of the HITL card layout
- Multi-language localization of HITL text

## Dependencies

- `specs/completed/hitl-auto-search-deep-fetch/` — previous SDD for SAFE_TOOLS
- `src/agent/hitl/context.py` — existing `build_hitl_context()` + `enrich_interrupt()` helpers (already built, not wired to security_proxy)
- `src/agent/nodes/security_proxy.py` — interrupt payload construction
- `src/agent/nodes/plan_review.py` — interrupt payload construction
- `src/agent/nodes/scope_clarify.py` — interrupt payload construction
- `frontend-v2/src/components/HitlPromptCard.tsx` — HITL card renderer (conversationSnippet parsed but not displayed)

## References

- `specs/completed/hitl-auto-search-deep-fetch/` — prior HITL changes

## Approval

- `requirements-review` AskQuestion: **approved** (2026-06-01) — core requirement: HITL must understand conversation context
