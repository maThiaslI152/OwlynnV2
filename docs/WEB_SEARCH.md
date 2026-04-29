# Web Search Architecture

## Overview

`web_search` is the agent's single entry point for internet search. It uses a multi-tier fallback pipeline that tries progressively more resilient (but slower) strategies until one succeeds. No API keys are required.

## Pipeline (in order)

```
User query
    │
    ├─ Tier 0:  wttr.in (weather only) ─── fast path for weather queries
    │
    ├─ Tier 0.5: SearXNG ───────────────── self-hosted metasearch aggregator
    │
    ├─ Tier 1:  curl_cffi ──────────────── browser-like TLS fingerprint (Chrome 120)
    │
    ├─ Tier 2:  DDGS ───────────────────── DuckDuckGo SDK wrapper
    │
    ├─ Tier 2C: httpx (DDG HTML → Bing → DDG Lite) ─ direct HTTP parsers
    │
    └─ Tier 3:  Playwright ─────────────── headless Chromium, JavaScript rendered
```

### Tier 0 — wttr.in (weather fast path)

- **Trigger**: Any query containing weather keywords (weather, forecast, temperature, rain, etc.)
- **How it works**: Extracts a location name via regex, calls `https://wttr.in/{location}?format=j1`, returns structured weather data (temp, feels-like, humidity, description)
- **Requirements**: None — free API, no key
- **Tier tag**: `tier0 / wttr`

### Tier 0.5 — SearXNG

- **Trigger**: `SEARXNG_URL` env var is set (e.g. `http://localhost:8888`)
- **How it works**: Calls the SearXNG JSON API at `{SEARXNG_URL}/search?format=json`. Aggregates Google, Bing, DDG, and Wikipedia results through a single self-hosted instance
- **Requirements**: Docker running `searxng/searxng:latest` on port 8888 (defined in `docker-compose.yml`) + `SEARXNG_URL` in `.env`
- **Tier tag**: `tier0.5 / searxng`

### Tier 1 — curl_cffi

- **Trigger**: All non-weather, non-Google queries after SearXNG fails
- **How it works**: Uses `curl_cffi` with `impersonate="chrome120"` to mimic real browser TLS/HTTP fingerprints. Tries DDG HTML, DDG Lite, and Bing in sequence. Detects Cloudflare/anti-bot challenges and skips blocked sources
- **Requirements**: `pip install curl_cffi` (silently skipped if not installed). Toggle via `WEB_SEARCH_ENABLE_CURL_CFFI=false`
- **Tier tag**: `tier1 / curl_cffi`

### Tier 2 — DDGS (DuckDuckGo SDK)

- **Trigger**: All remaining queries
- **How it works**: Calls `duckduckgo_search.DDGS.text()` or `.news()` in a thread
- **Requirements**: `pip install duckduckgo-search` (silently skipped if missing)
- **Tier tag**: `tier2 / ddgs`

### Tier 2C — HTTP parsers

Three direct HTTP fallbacks, tried in order:

| Sub-tier | Provider | URL | Parser |
|----------|----------|-----|--------|
| 2C-a | DDG HTML | `html.duckduckgo.com/html/` | `_parse_ddg_html_results()` |
| 2C-b | Bing | `bing.com/search` | `_parse_bing_html_results()` |
| 2C-c | DDG Lite | `lite.duckduckgo.com/lite/` | `_parse_ddg_html_results()` |

- **Requirements**: None — plain `httpx` + `beautifulsoup4`
- **Tier tag**: `tier2 / httpx_ddg_html`, `httpx_bing_html`, `httpx_ddg_lite`

### Tier 3 — Playwright (dynamic browser)

- **Trigger**: Last resort if every other tier fails
- **How it works**: Launches headless Chromium, navigates to Bing or DDG, waits for JS rendering, parses HTML
- **Requirements**: `playwright install chromium` (now installed). Toggle via `WEB_SEARCH_ENABLE_BROWSER_FALLBACK=false`
- **Tier tag**: `tier3 / playwright_dynamic`

### Google backend (special case)

When `backend="google"` is passed, `web_search` skips the entire pipeline and uses a dedicated Playwright-based Google scraper (`_google_search_playwright`). This is **not** part of the auto-backend chain — it only fires when explicitly requested.

- **Note**: Google actively blocks headless browsers. This often returns `"Blocked by Google CAPTCHA/Bot detection"`.
- **Tier tag**: N/A (dedicated path)

## `fetch_webpage` Tool

Fetches a single URL and returns readable text content.

### Pipeline

1. **URL unwrapping** — expands DuckDuckGo `/l/?uddg=` redirect URLs
2. **SSRF check** — rejects private/internal IPs, resolved DNS must be public
3. **HTTP fetch** — `httpx` with 15s timeout, Chrome UA, follows redirects
4. **HTML to text** — strips `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<aside>`, `<iframe>`, `<noscript>`. Extracts `<article>` / `<main>` / `<section>` / `<body>` text
5. **SPA shell detection** — if extracted text < 100 chars, falls back to `<title>` + meta/OG tags
6. **Focus-query ranking** — if `focus_query` is provided, chunks the text and returns embedding-ranked excerpts (via LM Studio embeddings)
7. **Truncation** — caps at 4000 chars if no `focus_query`

### Requirements

- `pip install httpx beautifulsoup4 lxml` (all already in `requirements.txt`)

## `fetch_webpage_dynamic` Tool

Same as `fetch_webpage`, but uses **Playwright** to render JavaScript before extracting text. 30s page load timeout.

**Note**: This tool is defined but **not** exposed to the agent via any toolbox. It exists for manual/testing use.

### Requirements

- `playwright install chromium`

## Web RAG (Focus-Query Ranking)

When `focus_query` is provided to either `web_search` or `fetch_webpage`, the results are reranked by embedding similarity using your local LM Studio instance.

### How it works

1. Text is chunked (720 chars, 120 char overlap)
2. Query and all chunks are embedded via `POST http://127.0.0.1:1234/v1/embeddings`
3. Top-K chunks (default 5) are returned by cosine similarity as a numbered "source pack"

### Configuration

All in `src/config/settings.py`:

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| `WEB_RAG_ENABLED` | `WEB_RAG_ENABLED` | `true` | Master toggle |
| `WEB_RAG_EMBED_MODEL` | `WEB_RAG_EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5@f16` | Embedding model name in LM Studio |
| `WEB_RAG_TOP_K` | `WEB_RAG_TOP_K` | `5` | Number of ranked excerpts to return |
| `WEB_RAG_CHUNK_CHARS` | `WEB_RAG_CHUNK_CHARS` | `720` | Max characters per chunk |
| `WEB_RAG_CHUNK_OVERLAP` | `WEB_RAG_CHUNK_OVERLAP` | `120` | Overlap between chunks |
| `WEB_RAG_MIN_CHARS_FOR_RANK` | `WEB_RAG_MIN_CHARS_FOR_RANK` | `1800` | Min text length to bother ranking |
| `WEB_SEARCH_RERANK_TOP_N` | `WEB_SEARCH_RERANK_TOP_N` | `8` | Search hits kept after reranking |

If LM Studio is unreachable or the embed model isn't loaded, reranking silently falls back to original result order.

## Externally Required Services

| Service | Config | Port | Purpose |
|---------|--------|------|---------|
| LM Studio (local) | `http://127.0.0.1:1234` | 1234 | LLM inference + embeddings |
| SearXNG (Docker) | `SEARXNG_URL=http://localhost:8888` | 8888 | Self-hosted metasearch |

## Removed Providers

As of April 2026, the following API-key-based providers were removed from the pipeline to simplify the stack:

- **Brave Search API** (`BRAVE_SEARCH_API_KEY`)
- **Serper.dev API** (`SERPER_API_KEY`)
- **Tavily API** (`TAVILY_API_KEY`)

The `WEB_SEARCH_PROVIDER` env var (`auto`/`brave`/`serper`/`tavily`) was also removed — it is no longer read by any code.

These removals affect only `src/tools/web_tools.py` and its tests. The env vars can remain in `.env` harmlessly.
