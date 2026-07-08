---
name: mcp_priority
description: Auto-invoke MCP context servers (context7, redis, playwright, browser-extension) proactively before taking action on relevant tasks. Prefer MCP tools over bash equivalents.
---

# MCP Tool Priority

Always load MCP context before acting on relevant tasks. Prefer MCP-provided tools over built-in bash or file tools.

## 1. context7 — Library & Framework Docs

**Trigger:** Before writing or updating any code that uses a library, framework, SDK, API, or CLI tool.

**Even for well-known libraries** (React, Next.js, Prisma, Express, Tailwind, Django, Spring Boot, etc.), your training data may not reflect recent changes. Always fetch current docs.

**Workflow:**
1. `context7_resolve-library-id` — resolve the package name to a Context7 library ID
2. `context7_query-docs` — query for the specific concept, API, or pattern you need
3. Write code based on the returned documentation and examples

**Do not use context7 for:** refactoring, writing scripts from scratch, debugging business logic, code review, or general programming concepts.

## 2. redis — Caching, Sessions, Vector Search

**Trigger:** Before implementing caching, session management, rate limiting, vector search, real-time analytics, message queues, or any data layer using Redis.

**Workflow:**
1. `redis_search_redis_documents` — query Redis docs for the relevant concept or pattern
2. Use the appropriate `redis_*` tool to implement (e.g., `redis_set`, `redis_hset`, `redis_vector_search_hash`)
3. Prefer `redis_*` tools over running `redis-cli` via bash

**Key tool categories:**
- Strings: `redis_get`, `redis_set`, `redis_expire`
- Hashes: `redis_hget`, `redis_hset`, `redis_hgetall`, `redis_hdel`
- Lists: `redis_lpush`, `redis_rpush`, `redis_lpop`, `redis_rpop`, `redis_lrange`
- Sets: `redis_sadd`, `redis_smembers`, `redis_srem`
- Sorted sets: `redis_zadd`, `redis_zrange`, `redis_zrem`
- Streams: `redis_xadd`, `redis_xrange`, `redis_xdel`
- Vector search: `redis_create_vector_index_hash`, `redis_vector_search_hash`, `redis_hybrid_search`, `redis_set_vector_in_hash`, `redis_get_vector_from_hash`
- Pub/Sub: `redis_publish`, `redis_subscribe`, `redis_unsubscribe`
- JSON: `redis_json_set`, `redis_json_get`, `redis_json_del`
- Info: `redis_info`, `redis_dbsize`, `redis_type`, `redis_scan_keys`, `redis_scan_all_keys`

## 3. playwright — Browser Testing & Web Automation

**Trigger:** Before writing tests, UI verification, web scraping, or any browser automation task.

**Workflow:**
1. `playwright_browser_navigate` — navigate to the target URL
2. `playwright_browser_snapshot` — capture the accessibility tree (preferred over screenshots for element targeting)
3. Use `playwright_browser_click`, `playwright_browser_type`, `playwright_browser_fill_form` for interactions
4. `playwright_browser_take_screenshot` — only when visual verification is needed

**Prefer accessibility tree over screenshots.** The snapshot tool returns a structured tree with element references that can be used directly for interactions.

## 4. browser-extension — Web Search & Page Content

**Trigger:** When you need to search the web, fetch page content, or capture a screenshot of the user's browser.

**Workflow:**
- **Search:** `browser_search(query, engine)` — searches Google/Bing/DDG via the user's browser extension, returns structured results. Use this instead of `webfetch` for web searches.
- **Page content:** `browser_fetch_page(url)` — extracts text from a page (handles JS-rendered content). Use this instead of `webfetch` for page content extraction.
- **Screenshot:** `browser_screenshot()` — captures the active tab with interactive element hints.
- **Status:** `browser_status()` — checks if the extension is connected.

**Fallback:** If the browser extension is not available (status returns error), fall back to `webfetch` for URL fetching and `grep_searchGitHub` for code pattern searches.

## 5. Priority Order

When multiple approaches are available:

1. **MCP tools** (context7, redis, playwright, browser-extension)
2. **Built-in tools** (webfetch, grep_searchGitHub, glob, grep, read)
3. **Bash fallback** (curl, redis-cli, etc.)

## 6. Quick Reference

| Task | MCP Tool | Fallback |
|------|----------|----------|
| Library docs | `context7_query-docs` | Web search |
| Redis operations | `redis_*` tools | `redis-cli` via bash |
| Browser testing | `playwright_browser_*` | Manual testing |
| Web search | `browser_search` | `webfetch` |
| Page content | `browser_fetch_page` | `webfetch` |
| Screenshot | `browser_screenshot` | `playwright_browser_take_screenshot` |
