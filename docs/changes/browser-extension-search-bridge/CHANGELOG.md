---
status: active
category: changelog
audience: agent
last_updated: 2026-06-11
owner: ai-agent
---

# Changelog: Browser Extension Search Bridge

> **Purpose:** Document the Chrome Search Bridge browser extension that routes search queries through a local user browser session (e.g. Brave) to bypass CAPTCHAs, load AI Overviews/Merlin summaries, and perform resilient fallback routing.

## User-facing behavior

| Action | Result |
|--------|--------|
| Trigger search in Chat UI | Backend checks if the browser extension is connected via WebSocket. |
| Extension online (Tier 0.2) | Opens a background tab in Brave, runs search query, content scripts scrape results (including AI Overviews, Merlin AI summaries, Copilot summaries, and DuckAssist), and auto-closes the tab within 15 seconds. |
| Extension offline / Timeout | Gracefully falls back to SearXNG (Tier 0.5), `curl_cffi` (Tier 1), DDG SDK (Tier 2), and Playwright (Tier 3). |
| Start application (`./start.sh`) | Launcher checks if Brave Browser is installed and automatically starts Brave loaded with the unpacked extension. |

## Supported Scraping Providers

Content scrapers are dynamically injected into search tabs to parse standard results and premium AI elements:

| Browser / Domain | Selector Scope | Premium Target |
|------------------|----------------|----------------|
| **Google** (`google.com`) | `a h3` headers & `.VwiC3b` snippets | Google AI Overviews (SGE), Featured Snippet, Merlin AI Sidebar |
| **Bing** (`bing.com`) | `li.b_algo` headers & captions | Bing Copilot inline card / chat summaries |
| **DuckDuckGo** (`duckduckgo.com`) | React article tags, HTML table layouts | DuckAssist & AI Chat modules |

## WebSocket API Contract

The extension connects to the backend at `ws://127.0.0.1:8000/api/browser_extension/ws`.

### Server-to-Client Request
Dispatched from backend when a search query is executed:
```json
{
  "id": "7d9d73e2-c2ed-425b-847b-d79d73e2384d",
  "action": "search",
  "url": "https://www.google.com/search?q=rust+programming+tutorial"
}
```

### Client-to-Server Response
Sent from background script after scraping results:
```json
{
  "id": "7d9d73e2-c2ed-425b-847b-d79d73e2384d",
  "results": [
    {
      "title": "⭐ Google AI Overview / Featured Snippet Summary",
      "href": "https://www.google.com/search?q=...",
      "body": "Rust is a multi-paradigm, general-purpose programming language..."
    },
    {
      "title": "The Rust Programming Language",
      "href": "https://www.rust-lang.org/",
      "body": "An official tutorial and reference book for learning Rust..."
    }
  ]
}
```

## Implementation map

### Extension Files

| File | Role |
|------|------|
| [manifest.json](file:///Users/tim/Works/OwlynnV2/browser-extension/manifest.json) | Manifest V3 configurations, host permissions, script matches |
| [background.js](file:///Users/tim/Works/OwlynnV2/browser-extension/background.js) | Handles WebSocket connection, manages background tabs, receives scraped hits, manages tab timeouts |
| [content_google.js](file:///Users/tim/Works/OwlynnV2/browser-extension/content_google.js) | Injected script scraping Google results, SGE, Merlin AI |
| [content_bing.js](file:///Users/tim/Works/OwlynnV2/browser-extension/content_bing.js) | Injected script scraping Bing results and Copilot summaries |
| [content_ddg.js](file:///Users/tim/Works/OwlynnV2/browser-extension/content_ddg.js) | Injected script scraping DDG (standard/HTML/lite/DuckAssist) |

### Backend Files

| File | Role |
|------|------|
| [browser_extension.py](file:///Users/tim/Works/OwlynnV2/src/api/routes/browser_extension.py) | APIRouter exposing the WS client registry and the async job dispatcher |
| [server.py](file:///Users/tim/Works/OwlynnV2/src/api/server.py) | Mounts `/api/browser_extension` router |
| [web_tools.py](file:///Users/tim/Works/OwlynnV2/src/tools/web_tools.py) | Places Tier 0.2 (`browser_extension`) at the top of the search pipeline |
| [defaults.yaml](file:///Users/tim/Works/OwlynnV2/src/config/defaults.yaml) | Configures `web_search.timeouts.extension: 15.0` timeout |
| [start.sh](file:///Users/tim/Works/OwlynnV2/start.sh) | Detects macOS Brave application installation and automatically launches it with the unpacked extension via `--load-extension` flag |

### Tests

| File | Covers |
|------|--------|
| [test_browser_extension_api.py](file:///Users/tim/Works/OwlynnV2/tests/test_browser_extension_api.py) | WebSocket lifecycle connect/disconnect, search query routing, and offline fallback |

## Related

- [docs/WEB_SEARCH.md](file:///Users/tim/Works/OwlynnV2/docs/WEB_SEARCH.md) — Web Search Architecture overview
- [docs/PROJECT_GUIDE.md](file:///Users/tim/Works/OwlynnV2/docs/PROJECT_GUIDE.md) — File mappings for tasks
- [docs/INDEX.md](file:///Users/tim/Works/OwlynnV2/docs/INDEX.md) — Documentation manifest index

## Last updated

2026-06-11 — Created Browser Extension Search Bridge changelog
