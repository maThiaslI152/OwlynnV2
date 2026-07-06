# Frontier Evaluation Report

**Date:** 2026-07-04
**Profile:** auto/local/cloud (strict-cloud enabled)
**Final Score:** 1830/1900 (96.32%) [19 scored, 0 skipped]

## Summary of Run

The evaluation was performed against the `strict-cloud` profile, ensuring the latest complex reasoning routes were fully exercised. 

### Key Obstacles Overcome
1. **Eval Harness Instability:** The initial runs encountered flakiness due to DOM-polling for `is_graph_busy`. This was resolved by migrating the eval harness to listen for the WebSocket `idle` status event, making the harness robust against complex graph iterations.
2. **HITL Collision:** Playwright button locators in `resolve_hitl` were colliding across stale UI cards. This was fixed by scoping the `.locator()` to the active prompt card and using `force=True`.
3. **Browser Deadlock (O(∞) loop):** The most critical blocker was an infinite loop in the frontend `parseInteractiveBlocks` parser that triggered during test `F5.1` (Sustained Reasoning). The AI generated a large streaming block, and a race condition during chunk arrival caused a regex mismatch that locked the main thread. 

### Resolution
- The infinite loop in the markdown parsing was patched by correctly advancing the cursor when an incomplete or languageless code fence is encountered during streaming.
- A 100ms `chunkThrottleTimer` was introduced in `App.tsx` to debounce WebSocket streaming chunks, preventing O(N²) layout thrashing in `react-markdown` during massive token generation.

The final run completed seamlessly with 19/19 test cases successfully scored.
