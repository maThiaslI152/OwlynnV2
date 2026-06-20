# Browser Extension Fixes & Moodle Mock
Date: 2026-06-20

## Summary
Fixed critical bugs in the browser extension's data payload delivery, upgraded the right-click menu to support intent-based auto-sending, fixed the missing "Stop" button in the UI, and created a fully interactive multi-page mock environment for Moodle quiz testing.

## Changes

### Backend & Gateway
- **`src/tools/screen_assist/tools.py`**: Fixed a bug where `active_browser_action` was returning only a success string and swallowing the JSON payload (e.g., `html` for `get_html` and `count` for `show_hints`). Now, the entire result payload is appended to the return string, allowing the agent to actually perceive the DOM.
- **`src/api/routes/browser_extension.py`**: Upgraded `_broadcast_page_context` to propagate the user's `intent` alongside the context.

### Frontend
- **`frontend-v2/src/lib/browserPageContext.ts`**:
  - Implemented intent handling.
  - Prepended strong system instructions explicitly banning Playwright.
  - Refined the `automate` intent to send a tiny prompt explicitly directing the agent to use `get_html` ("Developer Mode") instead of pasting massive 3,000-character page excerpts into the chat.
- **`frontend-v2/src/components/Composer.tsx`**: Wired up `useEffect` to trigger `onSend` immediately upon receiving page context via the WebSocket.
- **`frontend-v2/src/App.tsx`**: Fixed the runaway agent UI bug. Added a listener that intercepts active background tool-execution events and manually patches `pendingCorrelationId` to ensure the Stop button remains visible even if the user refreshes the page mid-loop.

### Extension
- **`browser-extension/background.js`**: Replaced the generic context menu with a nested parent menu containing `Default`, `Summarize`, and `Automate` intents.

### Evaluation & Testing
- **`frontend-v2/public/mock_moodle.html` (and linked assets)**: Cloned real Moodle test samples into the Vite public directory. Wired up navigation via JavaScript so the agent can traverse from `page1.html` -> `page2.html` -> `page3.html` -> `summary.html` natively, providing a complete interactive testbed for DOM automation evaluation.
