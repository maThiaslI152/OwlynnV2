---
status: active
category: architecture
last_updated: 2026-08-26
owner: human
---

# Web Search Architecture

> **Purpose:** Web search architecture — multi-tier fallback pipeline for internet search.

## Overview

`web_search` is the agent's single entry point for internet search. Uses a multi-tier fallback pipeline with progressively more resilient (but slower) strategies. No API keys required.

**Tool-first path (router):** When `selected_toolboxes=["web_search"]`, `complex_llm` injects a synthetic `web_search` call without `bind_tools` planning (`src/agent/core/tool_first_web.py`). Queries are resolved with pronoun-expansion intelligence: true pronoun follow-ups (`it`, `its`, `they`) are prepended with cleaned prior turn context, while temporal phrases (`this year`, `this month`, `today`) and self-contained queries remain unpolluted. After results, extractive synthesis is preferred (`complex.tool_first_extractive_synth`). Checkpointed `_tool_first_web_phase=done` is cleared on a new user turn that has not searched yet so mid-thread digressions (T3/T6) still inject search.

## Entry Points

```text
src/tools/web_tools.py              # web_search, fetch_webpage
src/tools/web_search_enhanced.py    # SearXNG integration
src/config/settings.py              # WEB_RAG_* env vars
docker-compose.yml                  # SearXNG container opt-in (compose profile searxng, port 8888)
```

## Architecture

### Search Pipeline

```
User query
    │
    ├─ Tier 0:   wttr.in (weather only) ─── fast path for weather queries
    │
    ├─ Tier 0.2: Chrome Search Bridge ───── delegator to user's active Brave session (primary)
    │
    ├─ Tier 1:   curl_cffi ───────────────── browser-like TLS fingerprint (Chrome 120)
    │
    ├─ Tier 1.5: SearXNG (opt-in) ────────── self-hosted metasearch (requires SEARXNG_URL)
    │
    ├─ Tier 2:   DDGS ────────────────────── DuckDuckGo SDK wrapper
    │
    ├─ Tier 2C:  httpx (DDG HTML → Bing → DDG Lite) ─ direct HTTP parsers
    │
    └─ Tier 3:   Playwright ──────────────── headless Chromium, JavaScript rendered
```

## API

### Tier 0: wttr.in (Weather Fast Path)

- Trigger: Query containing weather keywords (weather, forecast, temperature, rain, etc.)
- Behavior: Extracts location via regex, calls `https://wttr.in/{location}?format=j1`, returns structured weather data (temp, feels-like, humidity, description)
- Requirements: None — free API, no key
- Tier tag: `tier0 / wttr`

### Tier 0.2: Owlynn Browser Bridge

- Trigger (search): An active extension client is connected to `ws://localhost:8000/api/browser_extension/ws`
- Trigger (active tab): User context menu / popup push, or agent tool `get_active_browser_context` when `screen_assist` toolbox is bound
- Search behavior: Opens a background tab on allowlisted Google/Bing/DDG hosts, scrapes DOM (AI Overviews, Merlin, Copilot, DuckAssist) with MutationObserver readiness (budget &lt; 15s backend timeout)
- CAPTCHA / bot walls: Treated as **hard failure** (empty hits) so the pipeline falls through to curl_cffi / later tiers — never a synthetic “success” hit
- Active tab behavior: Reads the user's focused tab via `chrome.scripting` (`content_extract.js`); user push broadcasts `browser.page_context` to chat WebSocket clients. Sensitive (bank/SSO) hostnames are blocked for agent read/act paths
- Requirements: Unpacked extension (`browser-extension/` v1.4.0+) loaded in Brave/Chrome; `./start.sh` auto-loads on macOS when Brave is installed
- Auth: Extension fetches Origin-gated `/api/browser_extension/token`; privileged REST (`/search` `/fetch` `/screenshot`) requires run token or extension token
- Tier tag: `tier0.2 / browser_extension` (search); active tab is separate from search pipeline
- See [`features/BROWSER_EXTENSION.md`](BROWSER_EXTENSION.md)

### Tier 1.5: SearXNG (opt-in)

- Trigger: `SEARXNG_URL` env var is set **and** container is running
- Behavior: Calls SearXNG JSON API at `{SEARXNG_URL}/search?format=json`. Aggregates Google, Bing, DDG, Wikipedia results
- Requirements: `podman compose --profile searxng up -d searxng` + `SEARXNG_URL=http://localhost:8888` in `.env`. **Not started by `./start.sh`.**
- Tier tag: `tier1.5 / searxng`

### Tier 1: curl_cffi

- Trigger: All non-weather, non-Google queries after browser extension (and before SearXNG when configured)
- Behavior: Uses `curl_cffi` with `impersonate="chrome120"` for real browser TLS/HTTP fingerprints. Tries DDG HTML, DDG Lite, Bing in sequence. Detects Cloudflare/anti-bot challenges, skips blocked sources
- Requirements: `pip install curl_cffi` (silently skipped if not installed). Toggle: `WEB_SEARCH_ENABLE_CURL_CFFI=false`
- Tier tag: `tier1 / curl_cffi`

### Tier 2: DDGS (DuckDuckGo SDK)

- Trigger: All remaining queries
- Behavior: Calls `duckduckgo_search.DDGS.text()` or `.news()` in a thread
- Requirements: `pip install duckduckgo-search` (silently skipped if missing)
- Tier tag: `tier2 / ddgs`

### Tier 2C: HTTP Parsers

Three direct HTTP fallbacks, tried in order:

| Sub-tier | Provider | URL | Parser |
|----------|----------|-----|--------|
| 2C-a | DDG HTML | `html.duckduckgo.com/html/` | `_parse_ddg_html_results()` |
| 2C-b | Bing | `bing.com/search` | `_parse_bing_html_results()` |
| 2C-c | DDG Lite | `lite.duckduckgo.com/lite/` | `_parse_ddg_html_results()` |

Requirements: `httpx` + `beautifulsoup4` (in `requirements.txt`)
Tier tag: `tier2 / httpx_ddg_html`, `httpx_bing_html`, `httpx_ddg_lite`

### Tier 3: Playwright (Dynamic Browser)

- Trigger: Last resort if every other tier fails
- Behavior: Launches headless Chromium, navigates to Bing or DDG, waits for JS rendering, parses HTML
- Requirements: `playwright install chromium`. Toggle: `WEB_SEARCH_ENABLE_BROWSER_FALLBACK=false`
- Tier tag: `tier3 / playwright_dynamic`

### Google Backend (Special Case)

When `backend="google"` is passed, `web_search` uses a dedicated Playwright-based Google scraper (`_google_search_playwright`). Not part of the auto-backend chain — only fires when explicitly requested.

Note: Google actively blocks headless browsers. Often returns `"Blocked by Google CAPTCHA/Bot detection"`.

### `fetch_webpage` Tool

Fetches a single URL and returns readable text content.

Pipeline:

| Step | Detail |
|------|--------|
| URL unwrapping | Expands DuckDuckGo `/l/?uddg=` redirect URLs |
| SSRF check | Rejects private/internal IPs, resolved DNS must be public |
| HTTP fetch | `httpx` with 15s timeout, Chrome UA, follows redirects |
| HTML→text | Strips `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<aside>`, `<iframe>`, `<noscript>`. Extracts `<article>` / `<main>` / `<section>` / `<body>` text |
| SPA detection | If text < 100 chars, falls back to `<title>` + meta/OG tags |
| Focus-query ranking | If `focus_query` provided, chunks text and returns embedding-ranked excerpts (via LM Studio embeddings) |
| Truncation | Caps at 4000 chars if no `focus_query` |

Requirements: `pip install httpx beautifulsoup4 lxml` (all in `requirements.txt`)



### Web RAG (Focus-Query Ranking)

When `focus_query` is provided to `web_search` or `fetch_webpage`, or when `deep_research` scrapes documents larger than the threshold, results are reranked by embedding similarity via local LM Studio.

Flow:
1. Text chunked (720 chars, 120 char overlap)
2. Query and all chunks embedded via `POST http://127.0.0.1:1234/v1/embeddings`
3. Top-K chunks (default 5) returned by cosine similarity as numbered "source pack"

### `deep_research` Tool

Performs exhaustive web research by combining the Tiered search pipeline with concurrent async scraping using `Crawl4AI`.

Pipeline:
1. Calls `web_search` to retrieve search URLs.
2. Deduplicates and concurrently crawls the top URLs (asyncio + Crawl4AI).
3. If the combined markdown size exceeds `WEB_RAG_MIN_CHARS_FOR_RANK`, the text is sent to the Web RAG pipeline for extraction.
4. Outputs the final markdown inside strict `<web_context>...</web_context>` tags for prompt injection defense.

## Key Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Multi-tier fallback pipeline | Resilience without API keys | Complex error handling across tiers |
| Browser extension as tier 0.2 (primary) | Uses real Brave session; bypasses bot checks | Requires extension connected |
| SearXNG as tier 1.5 (opt-in) | Self-hosted metasearch when explicitly configured | Not started by `./start.sh`; requires profile + SEARXNG_URL |
| curl_cffi TLS fingerprinting | Bypasses anti-bot detection | Additional dependency |
| Playwright as last resort | Full JS rendering | Slowest tier, highest resource cost |
| Removed API-key providers (Brave/Serper/Tavily) | Simplified stack, no key management | Fewer search backends |

## Testing

- Tiers are exercised manually or via integration tests
- Env vars: `WEB_SEARCH_TIMEOUT_SECONDS`, `WEB_SEARCH_ENABLE_BROWSER_FALLBACK`, `WEB_SEARCH_ENABLE_CURL_CFFI`

## Configuration

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| `WEB_RAG_ENABLED` | `WEB_RAG_ENABLED` | `true` | Master toggle |
| `WEB_RAG_EMBED_MODEL` | `WEB_RAG_EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5-embedding` | Embedding model in LM Studio |
| `WEB_RAG_TOP_K` | `WEB_RAG_TOP_K` | `5` | Ranked excerpts to return |
| `WEB_RAG_CHUNK_CHARS` | `WEB_RAG_CHUNK_CHARS` | `720` | Max characters per chunk |
| `WEB_RAG_CHUNK_OVERLAP` | `WEB_RAG_CHUNK_OVERLAP` | `120` | Overlap between chunks |
| `WEB_RAG_MIN_CHARS_FOR_RANK` | `WEB_RAG_MIN_CHARS_FOR_RANK` | `1800` | Min text length for ranking |
| `WEB_SEARCH_RERANK_TOP_N` | `WEB_SEARCH_RERANK_TOP_N` | `8` | Search hits kept after reranking |
| `web_search.timeouts.extension` | - | `15.0` | Browser extension search timeout |

If LM Studio unreachable or embed model not loaded, reranking silently falls back to original result order.

### External Services

| Service | Config | Port | Purpose |
|---------|--------|------|---------|
| LM Studio (local) | `http://127.0.0.1:1234` | 1234 | LLM inference + embeddings |
| SearXNG (opt-in) | `SEARXNG_URL=http://localhost:8888` + `podman compose --profile searxng up -d` | 8888 | Self-hosted metasearch fallback |
| Browser Extension | `ws://localhost:8000/api/browser_extension/ws` | 8000 | Non-headless search gateway |

### Removed Providers (April 2026)

API-key-based providers removed from pipeline:

- Brave Search API (`BRAVE_SEARCH_API_KEY`)
- Serper.dev API (`SERPER_API_KEY`)
- Tavily API (`TAVILY_API_KEY`)

`WEB_SEARCH_PROVIDER` env var also removed. Removals affect `src/tools/web_tools.py` and its tests only.

## Troubleshooting (agent synthesis)

If web search runs but the UI never gets a written answer (tool loop, DSML markup, raw excerpt dump), see the fix log:

- [`docs/changes/web-search-synthesis-fix/CHANGELOG.md`](../changes/backbone-modernization/CHANGELOG.md) — BUG-WS-1..6, config `complex.max_web_tool_rounds`
- [`docs/BUG-TRACKER.md`](../archive/BUG-TRACKER.md) — BUG-13 summary

## Related

- [`docs/architecture/overview.md`](../architecture/overview.md) — system architecture
- [`docs/architecture/AGENT_FLOW.md`](../architecture/AGENT_FLOW.md) — tool-first web inject / sticky phase
- [`docs/README.md`](../README.md) — project documentation map

## Last updated

2026-08-26 — tool-first sticky `done` clear + extractive synth note
2026-06-11 — added Tier 0.2 Chrome Search Bridge extension details
