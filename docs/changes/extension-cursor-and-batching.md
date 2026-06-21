# Browser Extension: Cursor Hardening and Batch Selection (2026-06-21)

## Overview

This update hardens the Owlynn Browser Bridge extension to handle complex Single Page Applications (SPAs) and dramatically increases agent execution speed on complex interfaces (such as LMS quizzes) through batch selection.

## 1. Cursor Hardening

The standard `.click()` method was insufficient for modern web applications (like React and Vue) that rely heavily on synthetic events and hover states.

- **Full MouseEvent Chains**: The `click` action in `content_interact.js` now simulates a complete, human-like cursor interaction sequence: `pointerover` ➔ `mouseenter` ➔ `mousemove` ➔ `mousedown` ➔ `mouseup` ➔ `click`.
- **Hover Action**: Introduced a new `hover` action to trigger the hover state sequence without clicking, which enables the agent to gracefully reveal hidden dropdown menus or tooltips.

## 2. Batch Selection and Efficiency

Previously, an agent taking a 10-question multiple-choice quiz had to emit 10 separate sequential WebSocket calls (`active_browser_action`).

- **Batch Selection (`element_ids`)**: `active_browser_action` now accepts an `element_ids: list[int]` parameter. The browser extension natively resolves the array of IDs and simultaneously interacts with all targets in a single rapid execution cycle.
- **Full DOM Extraction (`read_full_dom_tree`)**: Added a new extraction mode that forces `buildDomTree.js` to parse and output all visible text nodes alongside the interactive elements. This provides the agent with critical reading context (e.g., the text of a quiz question) mapped directly next to the actionable elements (e.g., the radio buttons).

## 3. Turn Efficiency and Token Minimization

The communication loop between the backend agent and the browser extension has been optimized to reduce the number of reasoning turns and prompt tokens required to interact with a page.

- **Auto-Return DOM Updates**: When the agent performs a mutating action (`click`, `type`, `hover`, or `scroll`), `background.js` now automatically pauses for 600ms (to allow modern React/Vue SPAs to re-render), extracts the new DOM tree natively, and bundles it directly into the success response payload. 
- **Impact**: The agent no longer needs to spend a secondary reasoning turn explicitly calling `read_dom_tree` after every interaction. It instantly receives the new page state, slashing token usage and latency by 50%.

## 4. Testing and Validation

- Added new automated mock evaluation track `EX3.4` ("Hover Element") in `run_extension_eval.py` to ensure the agent correctly uses the `hover` tool.
- Verified that the `read_full_dom_tree` payload correctly extracts and formats textual nodes via `window.__owlynn_include_text`.
