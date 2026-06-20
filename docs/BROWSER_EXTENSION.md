# Browser Extension Integration

> **Purpose:** Describes the architecture and features of the Owlynn Browser Bridge extension.

## Overview
Owlynn ships with a local browser extension (`browser-extension/`) compatible with Chromium-based browsers (Brave, Chrome). The extension acts as a client bridge that allows the local Owlynn backend to seamlessly extract context and interact with the user's live browser state.

## Architecture

- **Backend:** `src/api/routes/browser_extension.py` hosts a FastAPI WebSocket endpoint at `ws://127.0.0.1:8000/api/browser_extension/ws`.
- **Extension Background:** `background.js` establishes and maintains a persistent WebSocket connection to the backend, retrying every 3 seconds if disconnected. This ensures that whenever the backend starts, the extension automatically connects to it without manual intervention.
- **Tools:** The LangGraph agent has access to specific tools (`src/tools/web_tools.py` and `src/tools/screen_assist/tools.py`) that dispatch commands over this WebSocket.

## Features

### 1. Active Tab Context (`get_active_browser_context`)
The agent can request the URL, title, and full textual content (stripped of HTML) of the user's currently active tab. It also captures any text the user currently has highlighted/selected.
- **Implementation:** `content_extract.js`

### 2. Visual Context (`get_active_browser_screenshot`)
The agent can request a base64 encoded JPEG screenshot of the user's active browser viewport. This is automatically plumbed through the Vision Proxy, allowing the vision model to analyze the UI visually.
- **Implementation:** `chrome.tabs.captureVisibleTab` in `background.js`

### 3. Interactive DOM Execution (`active_browser_action`)
The agent can actively interact with the user's browser without Playwright.
- **Actions:** `click`, `type`, `scroll`.
- **Implementation:** `content_interact.js` receives selector targets and simulates native DOM events.

### 4. Deep Background Scraping (`browser_background_fetch`)
Allows the agent to concurrently fetch the rendered text of multiple URLs. The extension programmatically creates hidden background tabs, waits for them to load (allowing SPAs to render), injects `content_extract.js`, and closes the tabs, returning the aggregated results. This bypasses many Cloudflare/bot protections that block standard backend curl/httpx requests.

### 5. Specialized Moodle Extractor
When extracting context from Moodle LMS URLs, the extension detects Moodle-specific DOM structures (`moodle-version`, `.course-content`). It strips away navigation sidebars and extracts a cleanly formatted Markdown representation of course modules, assignments, and grades.
- **Implementation:** `content_moodle.js`

### 6. Workspace File Transfer (Downloads & Uploads)
Because Chrome and Brave heavily restrict extensions from reading or writing to arbitrary OS folders (like the `workspace/` directories), Owlynn handles file transfers through native backchannels:
- **Downloads:** Uses the `download_to_workspace` tool to fetch web files natively via the Python backend, saving them directly into the secure project workspace.
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
