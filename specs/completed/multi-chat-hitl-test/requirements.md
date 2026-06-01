# Requirements: Multi-Chat HITL & Memory Isolation Test

> **Purpose:** Define what the change must do. Written in Plan mode before design. Must be approved via AskQuestion `requirements-review` popup before proceeding to design.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | Developer | to run a medium-length conversation on Owlynn via built-in browser multiple chat | I can verify normal conversation works end-to-end |
| US-2 | Developer | to confirm memory does not leak between separate chat sessions | I can trust session isolation |
| US-3 | Developer | to trigger and observe the HITL (Human-in-the-Loop) feature | I can verify HITL stays in context and does not cross sessions |

## Acceptance Criteria (EARS format)

> EARS = Easy Approach to Requirements Syntax: "When {condition}, the system shall {behavior}".

| ID | Criterion |
|----|-----------|
| AC-1 | When a user sends a message in chat A, the system shall produce a coherent response and maintain context within chat A across a 20+ turn conversation. |
| AC-2 | When chat B is opened while chat A has an active conversation, the system shall not carry over any messages, context, or memory from chat A into chat B. Verified by inspecting chat B's JSON history — zero references to chat A content. |
| AC-3 | When a tool-call HITL trigger fires in chat A, the system shall display the HITL prompt and require user confirmation before the tool executes, without affecting chat B's state. |
| AC-4 | When a prompt-based HITL trigger fires in chat A, the system shall request human input before continuing, without affecting chat B's state. |
| AC-5 | When HITL is confirmed in chat A, the system shall resume the conversation only in chat A, without leaking context into chat B. Verified via audit logs (session ID scoping). |
| AC-6 | When memory isolation is tested, automated assertions shall verify: (a) chat B's history JSON contains zero references to chat A's content, and (b) application audit logs show no cross-session context leakage. |

## Test Harness Requirements

| ID | Requirement |
|----|-------------|
| TH-1 | All test scenarios shall be automated (test scripts, not manual walkthroughs). |
| TH-2 | Tests shall cover medium-length conversations of 20+ turns per chat session. |
| TH-3 | Tests shall exercise both HITL trigger types: tool-call HITL and prompt-based HITL. |
| TH-4 | Memory isolation verification shall include both JSON history inspection and application log auditing. |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Performance | Chat switch latency < 500ms (time to load a different chat session) |
| NFR-2 | Reliability | No silent cross-chat data leakage — verified programmatically by both history JSON scan and log audit |
| NFR-3 | Observability | HITL trigger events shall be logged with chat session ID |

## Edge Cases and Error States

- What happens when HITL is triggered simultaneously in both chats?
- What error response when a chat session ID is invalid/corrupted?
- What happens when chat state fails to serialize/deserialize (memory store failure)?
- What happens when a chat reaches the 20+ turn limit — any token/context window warnings?
- What happens when HITL confirmation times out or is cancelled — is rollback clean?

## Out of Scope

- Performance benchmarks under load (e.g., 50+ concurrent chats)
- Long-term memory persistence across app restarts
- UI styling / visual design changes
- Non-functional load/stress testing

## Dependencies

- Owlynn built-in browser (chat UI)
- Owlynn multi-chat / session management subsystem
- Owlynn HITL (Human-in-the-Loop) hook/interceptor
- Owlynn chat state persistence (JSON history serialization)
- Application audit logging infrastructure

## References

- (Links to related docs, issues, designs)

## Approval

- `requirements-review` AskQuestion: **approved** (2026-05-31)
