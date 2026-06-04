# Requirements: HITL Auto-Search & Deep Content Fetch

> **Purpose:** Define what the change must do. Written in Plan mode before design. Must be approved via AskQuestion `requirements-review` popup before proceeding to design.

## User Stories

| ID | As a ... | I want to ... | So that ... |
|----|----------|---------------|-------------|
| US-1 | User | to not get HITL approval prompts when the LLM is unsure about external knowledge it can find on the web | the conversation flows naturally and the LLM autonomously searches instead of blocking on me |
| US-2 | User | to fetch and read the full content inside URLs found via search | I get detailed information from the page, not just surface-level search snippets |
| US-3 | User | to still have HITL protection for destructive actions (file writes, exec) | safety is preserved while search friction is removed |
| US-4 | User | for the LLM to be able to see what's in my browser (screen/window/region capture) | I don't have to manually describe browser content |
| US-5 | User | to not have LLM responses cut off mid-sentence | I don't have to explicitly tell the LLM to continue from where it stopped |

## Acceptance Criteria (EARS format)

> EARS = Easy Approach to Requirements Syntax: "When {condition}, the system shall {behavior}".

| ID | Criterion |
|----|-----------|
| AC-1 | When the LLM determines it lacks information that could be found via web search, the system shall autonomously perform a web search and incorporate the results without triggering a HITL approval prompt. |
| AC-2 | When the LLM has search results and needs more context than snippets provide, the system shall autonomously fetch the full content of the relevant URLs from the search results and incorporate the detailed content into the response. |
| AC-3 | When a user provides a specific URL and asks about its contents, the system shall fetch the full page content and respond based on that content. |
| AC-4 | When the LLM is confident in its internal knowledge, the system shall not perform unnecessary web searches. |
| AC-5 | When the LLM encounters ambiguity between knowledge gaps (auto-search) and tool-call safety concerns (file writes, exec, destructive actions), the system shall distinguish between the two — auto-searching for missing information while still requiring HITL for destructive or state-changing tools. |
| AC-6 | When a web search or content fetch fails, the system shall retry once automatically; if it still fails, the system shall inform the user and continue without triggering HITL. |
| AC-7 | When the user has a browser tab open and asks the LLM to look at browser content, the system shall capture the browser viewport (screen/window/region) and incorporate it into the response. |
| AC-8 | When the LLM is generating a long response, the system shall ensure the response is not truncated mid-sentence; if truncation is unavoidable, the system shall automatically continue the response or signal the user without requiring an explicit "continue" prompt. |

## Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Performance | Web search + content fetch should complete within 15s |
| NFR-2 | Reliability | Failed fetches should fall back gracefully with a clear message, not HITL prompt |

## Edge Cases and Error States

- When search returns no results: LLM reports "no results found" and continues conversation
- When a specific URL is unreachable or returns 404: retry once, then inform user
- When content fetch exceeds token limits: truncate or summarize; do not fall back to HITL
- Paywalled or login-required URLs: LLM reports content unavailable and continues
- HITL should still fire for: file writes, shell execution, destructive API calls
- Browser capture should respect viewport permissions; if capture fails, inform user
- Response truncation: detect mid-sentence cutoff and automatically send a continuation request to the LLM

## Out of Scope

- Web search UX improvements (search results display, ranking, etc.)
- Changes to HITL for non-search tool calls (file writes, execution, etc.)
- Changes to the underlying search engine (SearXNG)

## Dependencies

- Existing web search tool infrastructure (SearXNG / search MCP)
- Existing HITL routing / approval mechanism in the agent graph
- Existing `src.agent` tool definitions and routing logic

## References

- `specs/completed/multi-chat-hitl-test/` — previous SDD for HITL testing
- `browser_navigate` / `browser_snapshot` / `WebFetch` MCP tools for deep content retrieval

## Approval

- `requirements-review` AskQuestion: **approved** (2026-06-01) — includes two additional issues (browser capture, response cutoff)
