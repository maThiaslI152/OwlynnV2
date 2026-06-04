# Requirements: Evaluation Fixes

## Problem
The `owlynn-conversation-2026-06-03` evaluation report identified several critical issues affecting user experience and reliability:
1. False positive scope clarification on creative writing prompts.
2. A one-turn lag behavior in backend routing caused by dropped messages.
3. Playwright testing script timeouts for long inference tasks.
4. SearXNG 403 Forbidden errors preventing web search from working.

## Acceptance Criteria
- **AC-1:** Creative writing prompts containing words like "story", "poem", "essay", or "review" bypass the scope clarification HITL.
- **AC-2:** The SearXNG backend returns successful search results without 403 errors (by sending `User-Agent` and `Accept` headers).
- **AC-3:** The backend `GraphSession` queues incoming websocket messages or waits for the previous run to finish instead of silently dropping them.
- **AC-4:** The Playwright evaluation script waits up to 300 seconds for responses, preventing premature timeouts on long outputs.
