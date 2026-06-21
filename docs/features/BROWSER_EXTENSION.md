# Browser Extension Integration

> **Purpose:** Describes the architecture and features of the Owlynn Browser Bridge extension.

## Overview
Owlynn ships with a local browser extension (`browser-extension/`) compatible with Chromium-based browsers (Brave, Chrome). The extension acts as a client bridge that allows the local Owlynn backend to seamlessly extract context and interact with the user's live browser state.

## Architecture

- **Backend:** `src/api/routes/browser_extension.py` hosts a FastAPI WebSocket endpoint at `ws://127.0.0.1:8000/api/browser_extension/ws`.
- **Extension Background:** `background.js` establishes and maintains a persistent WebSocket connection to the backend, retrying every 3 seconds if disconnected.
- **Tools:** The LangGraph agent has access to specific tools (`src/tools/web_tools.py` and `src/tools/screen_assist/tools.py`) that dispatch commands over this WebSocket.

## Features

### 1. Embedded Iframe Sidebar UI
Instead of relying on fragile background script routing to stream text, the extension operates an **Iframe Sidebar**. 
- When the user triggers "Send to Owlynn", the backend returns the `thread_id` of the active workspace.
- `content_ui.js` dynamically injects an `iframe` into the active tab pointing to `http://127.0.0.1:5173/chat/{thread_id}?mode=sidebar`.
- The React application runs completely natively inside this iframe in a condensed layout. It connects directly to the standard backend WebSocket (`/ws/chat/{thread_id}`), handling streaming, markdown, and tool execution history perfectly.

### 2. Active Tab Context (`get_active_browser_context`)
The agent can request the URL, title, and full textual content (stripped of HTML) of the user's currently active tab. It also captures any text the user currently has highlighted/selected.
- **Deep Extraction:** Uses a custom `TreeWalker` to aggressively pierce through `#shadow-root` Web Components and recursively extracts text from all cross-origin iframes (`allFrames: true`), ensuring no text is hidden.
- **Implementation:** `content_extract.js`

### 3. Visual Context (`get_active_browser_screenshot`)
The agent can request a base64 encoded JPEG screenshot of the user's active browser viewport. This is automatically plumbed through the Vision Proxy, allowing the vision model to analyze the UI visually.
- **Visual Hints (Vimium-Style):** Before the screenshot is taken, the extension injects numbered yellow hint boxes (`[0]`, `[1]`) over all interactable elements. The agent can use these IDs to precisely click elements without guessing CSS selectors.
- **Implementation:** `chrome.tabs.captureVisibleTab` in `background.js`

### 4. Interactive DOM Execution (`active_browser_action`)
The agent can actively interact with the user's browser without Playwright.
- **Actions:** `click`, `hover`, `type`, `scroll`, `read_dom_tree`, `read_full_dom_tree`.
- **Implementation:** `content_interact.js` receives selector targets or batch `element_ids` and simulates native DOM events.
- **Features:** 
  - Simulates a full, human-like sequence of `PointerEvent` and `MouseEvent` for robust compatibility with React/Vue.
  - Supports batch operations: supplying an array of `element_ids` executes actions on multiple elements simultaneously (e.g. rapid test-taking).
  - `read_full_dom_tree` distills the DOM to include all visible text alongside interactive elements.
  - **MutationObserver Waits:** Mutating actions accept a `wait_for_selector` argument to dynamically delay the "success" response until an element appears, eliminating race conditions on slow SPAs.
  - **Auto-Return State**: After executing mutating actions (`click`, `type`, `hover`, `scroll`), the extension automatically waits 600ms and returns the updated DOM tree to the agent. This saves the agent a full round-trip turn previously spent querying the new page state.

### 5. Deep Background Scraping (`browser_background_fetch`)
Allows the agent to concurrently fetch the rendered text of multiple URLs. The extension programmatically creates hidden background tabs, waits for them to load (allowing SPAs to render), injects `content_extract.js`, and closes the tabs, returning the aggregated results. This bypasses many Cloudflare/bot protections that block standard backend curl/httpx requests.

### 6. Specialized Moodle Extractor
When extracting context from Moodle LMS URLs, the extension detects Moodle-specific DOM structures (`moodle-version`, `.course-content`). It strips away navigation sidebars and extracts a cleanly formatted Markdown representation of course modules, assignments, and grades.
- **Implementation:** `content_moodle.js`

### 7. Workspace File Transfer & Cookie Sync
Because Chrome and Brave heavily restrict extensions from reading or writing to arbitrary OS folders (like the `workspace/` directories), Owlynn handles file transfers through native backchannels:
- **Cookie Synchronization:** The backend automatically queries the extension over the WebSocket for the user's active cookies (`chrome.cookies.getAll`) on the target domain, allowing Python tools to seamlessly bypass auth walls.
- **Downloads:** Uses the `download_to_workspace` tool to fetch web files natively via the Python backend, injecting the synchronized browser cookies and saving them directly into the secure project workspace.
- **Uploads:** Uses the `upload_from_workspace` tool to bypass extension restrictions by attaching Playwright CDP to the active browser tab, allowing the agent to programmatically set `<input type="file">` element values directly from the native filesystem.

## Security
The extension only connects to `127.0.0.1:8000` and respects restricted browser pages (`chrome://`, `brave://`, etc.). Content scripts are injected programmatically on demand, keeping overhead minimal.

## Evaluation

The extension has a dedicated scored evaluation suite. See [`docs/standards/EVALUATION.md`](standards/EVALUATION.md) for the full standard.

```bash
# Run with Python mock extension (no real Brave needed)
python scripts/run_extension_eval.py

# Run a single track only
python scripts/run_extension_eval.py --track EX5

# Run against real connected Brave extension
python scripts/run_extension_eval.py --no-mock
```

**Pass threshold: ≥ 75% overall.**

Reports are written to `docs/evaluations/extension-eval-<date>.md`.

*Note: As of June 2026, the evaluation successfully passes with a score >75%. The backend automatically connects with the extension immediately upon startup without manual intervention, allowing Track 6 (Connection Lifecycle) and Interactive DOM tests to reliably succeed.*

### End-to-End Automation Testing
For debugging and manual verification of the browser extension, an end-to-end (E2E) test script is available at `scratch/test_moodle_extension.py`. 
This script:
1. Spins up a local HTTP server to host sample files.
2. Uses Playwright to launch Chromium with the **real** Owlynn extension loaded.
3. Connects directly to the Owlynn Chat WebSocket API and dispatches prompts (e.g., *"Automate this Moodle quiz"*).
4. Relies on the agent to successfully use the `active_browser_action` tool to extract the DOM and click elements through the extension.

It is highly recommended to use this script to test the interaction between the LLM and the real browser extension when making changes to `content_interact.js` or `content_moodle.js`.
