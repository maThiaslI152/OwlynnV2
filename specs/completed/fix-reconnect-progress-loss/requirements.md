# Requirements: Fix Reconnect Task Progress Loss

> **Purpose:** Prevent the SDD agent from losing task progress when the deepseek-cursor-proxy connection disconnects and reconnects. After reconnect, the agent must resume from where it left off instead of restarting from task 1. Must be approved via AskQuestion `requirements-review` popup before proceeding to design.

## Problem Statement

When using deepseek-cursor-proxy and the connection drops, clicking "Retry" to reconnect causes the Cursor agent to lose its conversation context. The agent forgets which SDD implementation tasks it already completed, reverts to "before starting any task," and begins implementing from task 1 again — duplicating work.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | Developer using SDD harness | The agent to remember completed tasks after a disconnect/reconnect | I don't waste time re-implementing work that was already done |
| US-2 | Developer using SDD harness | The agent to auto-skip already-completed tasks on reconnect | I can pick up exactly where I left off |
| US-3 | Developer using SDD harness | Sufficient context injected on session start for the agent to understand current state | The agent can make informed decisions without repeating the full conversation |

## Acceptance Criteria (EARS format)

> EARS = Easy Approach to Requirements Syntax: "When {condition}, the system shall {behavior}".

| ID | Criterion |
|----|-----------|
| AC-1 | When a new Agent session starts and an active SDD change exists, the sessionStart hook shall inject a summary of completed tasks (from state.json.verification.tasks) and the next pending task number into the agent's context. |
| AC-2 | When the agent reads sdd-agent-mode.mdc rules, it shall be instructed to check state.json.verification.tasks first and skip tasks already marked as "pass" before beginning implementation. |
| AC-3 | When a task is already marked "pass" in state.json.verification.tasks, the agent shall not re-implement that task — it shall proceed to the first task without a "pass" status. |
| AC-4 | When the agent resumes after a disconnect, it shall output a brief summary: "Tasks 1-2 already completed. Resuming at task 3." before starting work. |
| AC-5 | When state.json.verification.tasks is empty or has no completed tasks, the agent shall start from task 1 as normal (no regression). |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Reliability | Resume behavior must work even if state.json was the only file updated before disconnect |
| NFR-2 | Performance | Session start injection must add minimal latency (sub-second) |

## Edge Cases and Error States

- What if state.json is corrupted or unreadable? → Log error, fall back to starting from task 1 with a warning
- What if no active SDD change exists? → Normal session start, no special injection
- What if verification.tasks has only some tasks with "pass"? → Resume at first task without "pass" status
- What if state.json has tasks marked "pass" but code doesn't reflect it (partial disconnect mid-task)? → Agent should verify the files exist before skipping (optional v2)
- What if the CHANGELOG entry was written but state.json wasn't updated before disconnect? → CHANGELOG check can supplement state.json (optional v2)

## Out of Scope

- Full conversation history persistence (Cursors internal limitation)
- Deepseek-cursor-proxy-level fixes (we fix the SDD harness side only)
- Automatic detection of partially-completed tasks (v1 trusts state.json)
- Cross-machine session resumption

## Dependencies

- `state.json.verification.tasks` schema (already exists)
- `sdd-session.sh` hook (already exists, needs enhancement)
- `sdd-agent-mode.mdc` rules (already exists, needs enhancement)
- `sdd-core.mdc` rules (already exists, needs enhancement)

## References

- [`.cursor/hooks/sdd-session.sh`](../../.cursor/hooks/sdd-session.sh) — sessionStart hook
- [`.cursor/rules/sdd-agent-mode.mdc`](../../.cursor/rules/sdd-agent-mode.mdc) — agent mode rules
- [`.cursor/rules/sdd-core.mdc`](../../.cursor/rules/sdd-core.mdc) — core SDD rules
- [`specs/templates/state.json`](../../specs/templates/state.json) — state schema

## Approval

- `requirements-review` AskQuestion: **approved** 2026-05-31
