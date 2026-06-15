---
status: active
category: changelog
audience: agent
last_updated: 2026-06-15
owner: ai-agent
---

# Changelog: Browser Extension Active Tab Assist

> **Purpose:** Extend Owlynn Browser Bridge beyond search-only Tier 0.2 to support active-tab context for user push and agent tools.

## User-facing behavior

| Action | Result |
|--------|--------|
| Right-click page → **Send page to Owlynn** | Active tab URL, title, and text prefill the chat composer (not auto-sent) |
| Extension popup → **Send page to Owlynn** | Same as context menu |
| Agent calls `get_active_browser_context` | Extension returns URL, title, page text, selection when connected |
| Extension offline | Tool falls back to AppleScript (Chrome/Safari/Arc) + optional Playwright CDP |

## WebSocket protocol (extension ↔ backend)

Endpoint: `ws://127.0.0.1:8000/api/browser_extension/ws`

### Agent request — active tab

Server → extension:

```json
{ "id": "<uuid>", "action": "get_active_tab" }
```

Extension → server:

```json
{
  "id": "<uuid>",
  "tab": {
    "url": "https://example.com",
    "title": "Example",
    "text": "…",
    "selection": "…",
    "error": ""
  }
}
```

### User push — page context

Extension → server (no `id`):

```json
{
  "type": "page_context_push",
  "url": "https://example.com",
  "title": "Example",
  "text": "…",
  "selection": "…"
}
```

Server broadcasts to chat clients:

```json
{
  "type": "browser.page_context",
  "url": "…",
  "title": "…",
  "text": "…",
  "selection": "…"
}
```

Search (`action: "search"`) is unchanged from v1.0.

## Files

| Area | Path |
|------|------|
| Extension | `browser-extension/` — `background.js`, `content_extract.js`, `popup.html`, `popup.js`, `manifest.json` v1.1.0 |
| Backend API | `src/api/routes/browser_extension.py` |
| Screen assist | `src/tools/screen_assist/gateway.py`, `tools.py` |
| Config | `src/config/defaults.yaml` → `browser_extension.*` |
| Frontend | `frontend-v2/src/lib/browserPageContext.ts`, `App.tsx`, `Composer.tsx`, `useAppStore.ts` |
| Tests | `tests/test_browser_extension_api.py`, `frontend-v2/src/lib/browserPageContext.test.ts` |

## Privacy

- User push requires explicit context-menu or popup click
- Agent read only via `get_active_browser_context` when `screen_assist` toolbox is bound
- Page text truncated per `browser_extension.max_tab_text_chars` (default 12000)

## Verification

```bash
python3 -m pytest tests/test_browser_extension_api.py -q
cd frontend-v2 && npm test -- src/lib/browserPageContext.test.ts
./scripts/ci.sh --quick
```
