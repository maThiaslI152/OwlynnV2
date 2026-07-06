# Frontend Freeze and UI Polish

**Date:** 2026-07-04

## Streaming Deadlock Fixes
- **WebSocket Throttling:** Implemented a 100ms debounce buffer for incoming streaming `chunk` events in `App.tsx`. This significantly reduces the render overhead of `react-markdown` when parsing large, continuous code blocks from the LLM.
- **Interactive Block Parser Patch:** Fixed a critical infinite loop in `parseInteractiveBlocks.ts` that occurred when the parser encountered an incomplete code block fence (e.g. ` ``` ` without a language identifier) during a streaming update. The parser now correctly consumes the partial fence and advances the cursor, preventing browser thread deadlocks.

## UI / UX Enhancements
- **Glassmorphic Dropdowns:** Restyled the `.menu-dropdown` class in `index.css` to use the unified transparent glass aesthetic (`var(--bg-surface)` with `blur(24px)`), replacing the legacy opaque background.
- **Memory Menu Overhaul:** Refactored `MemoryPanel.tsx` to display the Long-Term Memory (Mem0) management section by default, removing the unnecessary "Show" toggle. Users can now instantly view, search, add, and delete memories as soon as they open the dropdown.
- **Test Harness Upgrades:** Enhanced the `run_local_frontier_eval.py` test harness with a `page.evaluate("1")` deadlock detector to fail instantly if the main thread freezes, rather than timing out after 15 minutes.
