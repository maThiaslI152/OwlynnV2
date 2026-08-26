---
status: active
category: reference
last_updated: 2026-08-26
owner: ai-agent
audience: agent
---

# Browser Extension Integration

> **Purpose:** Describes the architecture and features of the Owlynn Browser Bridge extension.

## Overview
Owlynn ships with a local browser extension (`browser-extension/`, v1.4.1) compatible with Chromium-based browsers (Brave, Chrome). The extension acts as a client bridge that allows the local Owlynn backend to seamlessly extract context and interact with the user's live browser state.

## Architecture

- **Backend:** `src/api/routes/browser_extension.py` hosts a FastAPI WebSocket endpoint at `ws://127.0.0.1:8000/api/browser_extension/ws`.
- **Extension Background:** `background.js` establishes and maintains a persistent WebSocket connection to the backend, with exponential backoff and alarm-based keepalive/reconnect recovery. Auth token is fetched from `/api/browser_extension/token` **before** opening the WS (never open-then-close), cached in `chrome.storage.local` (`owlynnAuthToken`), and only cleared on auth rejection (`4001`).
- **Tools:** The LangGraph agent has access to specific tools (`src/tools/web_tools.py` and `src/tools/screen_assist/tools.py`) that dispatch commands over this WebSocket.

## Features

### 1. Send page to Owlynn
User-initiated context push via popup or right-click menu. Page URL, title, text, and selection are broadcast to chat WebSocket clients as `browser.page_context`.

> **Removed:** Live page-tracking (Mem0 auto-write) and the iframe sidebar UI were dropped — they were broken by `X-Frame-Options: DENY` and an empty `allowed_live_tracking_domains` allowlist.

### 2. Active Tab Context (`get_active_browser_context`)
The agent can request the URL, title, and full textual content (stripped of HTML) of the user's currently active tab. It also captures any text the user currently has highlighted/selected.
- **Deep Extraction:** Uses a custom `TreeWalker` to aggressively pierce through `#shadow-root` Web Components and recursively extracts text from all cross-origin iframes (`allFrames: true`), ensuring no text is hidden.
- **Sensitive sites:** Banking / SSO / auth-looking hostnames are blocked for agent read/act/screenshot/cookie paths.
- **Implementation:** `content_extract.js`

### 3. Visual Context (`get_active_browser_screenshot`)
The agent can request a base64 encoded JPEG screenshot of the user's active browser viewport. This is automatically plumbed through the Vision Proxy, allowing the vision model to analyze the UI visually.
- **HITL:** Screenshots require security-proxy approval (`get_active_browser_screenshot` is sensitive).
- **Visual Hints (Vimium-Style):** Before the screenshot is taken, the extension injects numbered yellow hint boxes (`[0]`, `[1]`) over all interactable elements.
- **Implementation:** `chrome.tabs.captureVisibleTab` in `background.js`

### 4. Interactive DOM Execution (`active_browser_action`)
The agent can actively interact with the user's browser without Playwright.
- **Actions:** `click`, `hover`, `type`, `scroll`, `read_dom_tree`, `read_full_dom_tree`.
- **Serialization:** Browser actions are queued so overlapping DOM mutations do not race.
- **HITL:** `get_html` requires approval (raw DOM may include PII).
- **Implementation:** `content_interact.js`

### 5. Deep Background Scraping (`browser_background_fetch`)
Allows the agent to concurrently fetch the rendered text of multiple URLs. The extension creates hidden background tabs (tracked for orphan cleanup), waits for load, injects `content_extract.js`, and closes the tabs.
- **SSRF:** Both Python (`url_fetch_blocked_reason`) and the extension mirror block localhost / private / metadata URLs before fetch or tab open.

### 6. Specialized Moodle Extractor
When extracting context from Moodle LMS URLs, the extension detects Moodle-specific DOM structures and extracts a cleanly formatted Markdown representation of course modules, assignments, and grades.
- **Implementation:** `content_moodle.js`

### 7. Workspace File Transfer & Cookie Sync
- **Cookie Synchronization:** Extension asks for per-domain consent (deny-by-default if no active tab / no response); uses `chrome.cookies.getAll({ url })`. Downloads that attach cookies are HITL-gated (`download_to_workspace`).
- **Downloads / Uploads:** Same as before via Python tools + Playwright CDP for uploads.

## Security

| Control | Behavior |
|---------|----------|
| REST auth | `/search`, `/fetch`, `/screenshot`, `/reload` require `X-Owlynn-Run-Token` (local run token **or** extension WS token). `/status` is read-only public; `/token` is Origin-gated only. |
| Token Origin | Empty / `null` Origin rejected for web pages. `chrome-extension://` / `moz-extension://` allowed. Brave MV3 may omit Origin on loopback fetches — those are allowed only when the TCP client is `127.0.0.1` / `::1`. |
| Token file | `~/.owlynn/browser_extension_token` written/chmod'd `0o600`. |
| Token cache | Extension caches successful `/token` responses in `chrome.storage.local` (`owlynnAuthToken`) for SW restarts. |
| Backend URL | Loopback default (`127.0.0.1` / `localhost`); remote requires explicit popup confirmation; `wss://` used for `https`. |
| Search hosts | Allowlisted Google / Bing / DuckDuckGo hosts only. |
| CAPTCHA | Google scraper reports hard failure (empty hits) so Tier 0.2 does not poison fallbacks. |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Backend spam: `Browser extension auth error: (1005…)` every ~3s | Extension opened WS without a token then closed (pre-1.4.1), or stale install after repo path move | Reload extension from `Documents/OwlynnV2/browser-extension` at `brave://extensions`; confirm v1.4.1+; check SW console for token fetch errors |
| `/api/browser_extension/status` → `connected: false` | Backend down, wrong popup URL, or token fetch 403 | Ensure API on `:8000`; popup URL `http://127.0.0.1:8000`; reload SW |
| Auth works then fails after backend restart | Token file rotated / process restarted with new token | Extension clears cache on WS close `4001` and re-fetches automatically |

## Evaluation

The extension has a dedicated scored evaluation suite. See [`docs/standards/EVALUATION.md`](../standards/EVALUATION.md) for the full standard.

```bash
# Run with Python mock extension (no real Brave needed)
python scripts/run_extension_eval.py

# Run a single track only
python scripts/run_extension_eval.py --track EX5

# Run against real connected Brave extension
python scripts/run_extension_eval.py --no-mock
```

### Automated Evaluation Runner

```bash
python scripts/run_extension_eval_automated.py --local-cloud
python scripts/run_extension_eval_automated.py --local-cloud --track EX1
```

**Pass threshold: ≥ 75% overall.**

Reports are written to `docs/evaluations/extension-eval-<date>.md`.

### End-to-End Automation Testing
For debugging and manual verification of the browser extension, an end-to-end (E2E) test script is available at `scratch/test_moodle_extension.py`.
