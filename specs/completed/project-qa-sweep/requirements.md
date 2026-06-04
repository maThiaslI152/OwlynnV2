# Requirements: Project QA Sweep

> **Purpose:** Audit the CI/testing suite for relevance, fix gaps, then validate workspace behavior, long-conversation memory, and HITL context-awareness.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | Developer | a functional pre-push CI hook and strict test configuration | every push is validated without relying on GitHub Actions |
| US-2 | Developer | workspaces to enforce project isolation and path sandboxing | project files cannot leak between workspaces or escape the workspace root |
| US-3 | User | long conversations to maintain coherent memory without cutoff or hallucinated recall | I can have extended multi-turn sessions without losing context |
| US-4 | User | HITL prompts that reflect actual conversation context, not generic templates | I can make informed decisions based on what the agent is actually doing |

## Acceptance Criteria (EARS format)

### CI & Testing Suite

| ID | Criterion |
|----|-----------|
| AC-1 | When `git push` is executed, the pre-push hook shall run `scripts/ci.sh --quick` and block the push on failure. |
| AC-2 | When pytest runs in CI, `--strict-markers` shall be enforced so undefined markers cause errors, not silent passes. |
| AC-3 | When CI runs, the benchmark report (`tests/benchmarks/benchmark_report.json`) shall not be empty — benchmarks shall produce actual results. |
| AC-4 | When CI runs, coverage thresholds shall be configured and reported (baseline only — no enforcement yet). |

### Workspace Behavior

| ID | Criterion |
|----|-----------|
| AC-5 | When file operations target a project workspace, the system shall reject paths outside `workspace/projects/<id>/`. |
| AC-6 | When two projects are active concurrently, file operations in project A shall not affect or read from project B's workspace. |
| AC-7 | When a file is uploaded to a project, the system shall store it under the correct `workspace/projects/<id>/` directory. |

### Long Conversation Memory

| ID | Criterion |
|----|-----------|
| AC-8 | When a conversation exceeds the context window threshold, the auto-summarize node shall compress older messages without losing key facts, decisions, or user preferences. |
| AC-9 | When the LLM response hits token budget cutoff, the system shall auto-continue up to 3 times with coherent context bridging. |
| AC-10 | When memory is recalled from past conversations, the recalled facts shall be relevant to the current conversation — not random or hallucinated. |

### HITL Context-Awareness

| ID | Criterion |
|----|-----------|
| AC-11 | When a scope-clarification HITL fires, the questions shall reference the actual user request — not show a generic "build what?" template. |
| AC-12 | When a security-proxy HITL fires, the prompt shall display the specific tool, args, and affected files from the current request — not hardcoded examples. |
| AC-13 | When a plan-review HITL fires, the stated intent shall derive from the pending tool calls — not a static placeholder. |
| AC-14 | When a router HITL fires (low confidence), the options shall reflect the actual ambiguous route candidates with confidence scores. |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Reliability | The pre-push hook must not produce false positives — CI must match what the hook checks. |
| NFR-2 | Performance | Auto-summarize must complete within 5 seconds (Small LLM call). |
| NFR-3 | Testability | All verify_steps must be reproducible on any developer machine with `./scripts/ci.sh`. |

## Edge Cases and Error States

- **Pre-push hook missing:** Recreate `.git/hooks/pre-push` from the expected content (runs `scripts/ci.sh --quick`).
- **Benchmarks fail silently:** If benchmarks return empty results, flag the failure instead of committing an empty report.
- **Summarizer LLM unavailable:** If Small LLM fails, auto-summarize should log a warning and skip gracefully — already implemented but verify.
- **HITL context truncated:** If the conversation snippet is too short to capture intent, the HITL prompt should fall back to the full user message, not show an empty context.
- **Project isolation under concurrency:** Two simultaneous WebSocket connections targeting different projects must not cross-contaminate state.

## Out of Scope

- Rewriting or restructuring the test suite
- Adding new test frameworks (accessibility, visual regression, security scanning)
- Enforcing coverage thresholds (baseline config only)
- Modifying the agent graph architecture beyond bug fixes discovered during testing

## Dependencies

- `hitl-context-awareness` (specs/active/) — HITL testing must run against both current state and post-merge state
- `prep-and-push-to-github` (specs/active/) — CI fixes may overlap; coordinate push-hook changes
- Running Owlynn backend + frontend for end-to-end workspace/chat/HITL tests

## References

- `docs/guides/dev-startup.md` — how to start the app
- `scripts/ci.sh` — current CI pipeline
- `src/agent/graph.py` — agent graph with HITL interrupt nodes
- `src/agent/hitl/context.py` — HITL context enrichment
- `src/agent/nodes/summarize.py` — auto-summarize node
- `tests/` — existing test suite (107 Python + 7 frontend files)
- Specs/active/hitl-context-awareness/ — in-progress HITL improvements

## Approval

- `requirements-review` AskQuestion: approved 2026-06-02T06:37:00Z
