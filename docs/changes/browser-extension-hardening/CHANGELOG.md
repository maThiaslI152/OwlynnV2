# Browser Extension Hardening — Security, Navigation, Batch Selection, Moodle

> **Date:** 2026-06-28 (v1.2.0→1.3.0), 2026-06-29 (v1.3.0→1.4.0)
> **Status:** COMPLETE
> **Version:** 1.2.0 → 1.4.0

## Overview

Comprehensive hardening of the Owlynn browser extension: security fixes, new navigation actions, batch selection improvements, Moodle framework enhancements, and deep security/performance audit fixes.

---

## v1.4.0 — 2026-06-29 Deep Security & Performance Audit

### Critical Security Fixes (6)

| # | Issue | Severity | Fix |
|---|-------|----------|-----|
| 1 | **`fetch_urls` broken** — `scrapeSingleUrlInBackground` undefined | CRITICAL | Replaced with parallel `fetch()` + `DOMParser` text extraction, concurrency 5 |
| 2 | **Selector injection** — `javascript:`/`data:` URI selectors could execute code | CRITICAL | Added scheme validation block in `content_interact.js` |
| 3 | **`get_html` leaks secrets** — hidden inputs, CSRF tokens, passwords in returned HTML | CRITICAL | Filters `input[type=password]`, `input[type=hidden]`, fields named `token`/`csrf`/`secret`/`api_key` |
| 4 | **Constant-time token comparison** — `!=` operator vulnerable to timing attacks | CRITICAL | Backend uses `hmac.compare_digest()` |
| 5 | **Password values in DOM tree** — `(Value: *****)` shown for password fields | HIGH | `buildDomTree.js` masks `input[type=password]` values |
| 6 | **`submit_form` doesn't submit** — synthetic `submit` event doesn't trigger browser submission | HIGH | Uses `form.requestSubmit()` / `form.submit()` |

### Communication Hardening (4)

| # | Issue | Fix |
|---|-------|-----|
| 7 | **No WS message size limit** — DoS via oversized messages | 1MB limit: uvicorn `--ws-max-size`, extension client-side rejection, backend rejection |
| 8 | **No WS message type allowlist** — unknown types accepted | Both backend and extension validate against known types, reject unknown |
| 9 | **Logging leaks sensitive data** — full message content/URLs/errors in console | `console.debug` for message types only, no content/URLs/error details |
| 10 | **`isSecureUrl` substring matching** — `something-localhost.com` matches "localhost" | Exact match: `hostname === domain \|\| hostname.endsWith('.' + domain)` |

### Service Worker Hardening (5)

| # | Issue | Fix |
|---|-------|-----|
| 11 | **Infinite reconnect loop** — 3s fixed retry when backend down | Exponential backoff: 3s→6s→12s→30s cap, max 20 retries |
| 12 | **Dual keepalive redundant** — `setInterval` + `chrome.alarms` | Removed `setInterval`; rely solely on `chrome.alarms` (survives SW termination) |
| 13 | **Auth token persisted to storage** — accessible to content scripts | Memory-only; removed `chrome.storage.local.set({owlynnAuthToken})` |
| 14 | **`cookieConsentCache` lost on SW termination** | Persisted to `chrome.storage.session` (survives restart, cleared on browser close) |
| 15 | **`BACKEND_URL_UPDATED` dead code** — message sent but never handled | Handler reconnects with new URL |

### Performance Improvements (3)

| # | Issue | Fix |
|---|-------|-----|
| 16 | **Screenshot 4× script injection** — hints + interact.js injected twice | Consolidated to single inline function for hint injection/removal |
| 17 | **`fetch_urls` sequential** — URLs fetched one at a time | Parallel `Promise.all` with concurrency 5 |
| 18 | **Configurable backend URL** — hardcoded `ws://127.0.0.1:8000` | Reads from `owlynnBackendUrl` storage key; popup updates reconnect |

### Additional Fixes (5)

| # | Issue | Fix |
|---|-------|-----|
| 19 | **`wait_for_navigation` hangs** — page already loaded | Checks `document.readyState === 'complete'` first |
| 20 | **`innerHTML` dead code path** — legacy XSS-prone code in `showUI()` | Removed; only safe `textContent` path remains |
| 21 | **Moodle selector injection** — unescaped `input.name`/`input.value` in selectors | `CSS.escape()` on all interpolated values |
| 22 | **Redundant `host_permissions`** — specific domains alongside `<all_urls>` | Removed redundant entries |
| 23 | **Global window exports** — `owlynnShowStatus`/`owlynnHideStatus` exposed to page | Removed exports |

### Files Changed (v1.4.0)

| File | Changes |
|------|---------|
| `browser-extension/background.js` | Auth memory-only, reconnect backoff, configurable URL, message validation, size limit, logging hygiene, screenshot consolidation, fetch_urls parallel, cookieConsentCache persistence, BACKEND_URL_UPDATED handler |
| `browser-extension/content_interact.js` | Selector validation, submit_form fix, wait_for_navigation fix, get_html secret filtering |
| `browser-extension/buildDomTree.js` | Password value masking |
| `browser-extension/content_ui.js` | Removed innerHTML dead code, removed window exports, default URL :5173→:8000 |
| `browser-extension/content_moodle.js` | CSS.escape() on selectors |
| `browser-extension/manifest.json` | Removed redundant host_permissions |
| `browser-extension/popup.js` | Default URL :5173→:8000, BACKEND_URL_UPDATED sends URL |
| `browser-extension/popup.html` | Placeholder URL :5173→:8000 |
| `src/api/routes/browser_extension.py` | hmac.compare_digest(), message type allowlist |
| `start.sh` | --ws-max-size 1048576 |

---

## v1.3.0 — 2026-06-28 Initial Hardening

### Security Hardening (5 fixes)

#### 1. XSS via innerHTML (BUG-33)
**Severity:** HIGH

`content_ui.js` set `innerHTML` from WebSocket messages, allowing potential script injection.

**Fix:** Replaced `innerHTML` with `textContent`/DOM APIs. Added `sanitize()` function. Status updates use `buildStatusHtml()` with DOM APIs.

#### 2. WS Token Exchange Auth (BUG-34)
**Severity:** MEDIUM

Any local process could connect to the WS endpoint and issue browser commands.

**Fix:**
- Backend generates token on startup → writes to `~/.owlynn/browser_extension_token`
- `GET /api/browser_extension/token` endpoint (CORS restricted to extension origin)
- WS handler validates auth token as first message
- Extension fetches token on connect, re-fetches on reconnect

#### 3. Cookie Consent (BUG-36)
**Severity:** MEDIUM

Backend could request cookies for any domain without user approval.

**Fix:** Added `confirm()` dialog before returning cookies. Per-session cache (cleared on extension restart).

#### 4. CSP in Manifest
**Severity:** LOW

No Content Security Policy declared.

**Fix:** Added `content_security_policy` to manifest.json: `script-src 'self'; object-src 'self'; frame-src http://127.0.0.1:*`

#### 5. Configurable Sidebar URL (BUG-14)
**Severity:** LOW

Hardcoded `http://127.0.0.1:5173` in `content_ui.js`.

**Fix:** Added URL field to popup UI. Stored in `chrome.storage.local`. Default to `http://127.0.0.1:5173`.

### Bug Fixes (3 fixes)

#### 6. `.lower` Typo (BUG-35)
`content_google.js` used `.lower` instead of `.toLowerCase()`. Fixed.

#### 7. DOM Tree Size Cap (BUG-37)
`buildDomTree.js` had no size limit. Added `MAX_ELEMENTS=500`, `MAX_CHARS=100000`.

#### 8. Rate Limiting
Added `MAX_QUEUE_SIZE=10`, `MIN_COMMAND_INTERVAL_MS=100` to prevent command flooding.

### Navigation Enhancements (5 new actions)

| Action | Description | File |
|--------|-------------|------|
| `wait_for_navigation` | Wait for page load after click/submit (10s timeout) | `content_interact.js` |
| `scroll_to_element` | Scroll element into view with smooth behavior | `content_interact.js` |
| `select_option` | Select dropdown option by value/text | `content_interact.js` |
| `submit_form` | Submit parent form via `closest('form')` | `content_interact.js` |
| `focus` | Focus element for keyboard navigation | `content_interact.js` |

### Batch Selection Enhancements (3 new actions)

| Action | Description | File |
|--------|-------------|------|
| `select_checkboxes` | Batch check/uncheck checkboxes by `element_ids` | `content_interact.js` |
| `select_radio` | Select radio button by `element_id` | `content_interact.js` |
| `type_into_sequence` | Type into multiple fields with Tab between | `content_interact.js` |

### Moodle Framework Enhancements (6 new extractions)

| Extraction | Selectors | Output |
|------------|-----------|--------|
| **Grades** | `.gradestable`, `#user-grades`, `.generaltable` | Structured grades data |
| **Course sections** | `.section`, `.sectionname`, `.section-info` | Section titles + activities |
| **Assignments** | `.assignsubmission`, `.duedate`, `.submissionstatus` | Due dates, status |
| **File links** | `.resource a[href]`, `.modtype_resource a[href]` | File URLs |
| **Quiz navigation** | `.qn_buttons`, `.qnbutton`, `.mod_quiz-next-nav` | Total questions, navigation |
| **User profile** | `.userprofile`, `.username`, `.user-email` | Name, email, avatar |

### Robustness Improvements

| Improvement | Description |
|-------------|-------------|
| **Service worker keepalive** | `chrome.alarms` with 0.5min period to prevent MV3 termination |
| **Tab ID pinning** | Verify tab ID matches request before action |
| **Re-auth on reconnect** | Re-fetch token on WS disconnect |

---

## Verification

- CI: All checks passed (1054 Python tests, 130 frontend tests)
- `test_extension_websocket_lifecycle`: Passes with auth token
- Syntax check: All JS files pass `node -c`

## Message Protocol Reference

### Extension → Backend

| Type | Shape | Purpose |
|------|-------|---------|
| `auth` | `{ type: "auth", token }` | First message after WS open |
| `ping` | `{ type: "ping" }` | Keepalive (30s alarm) |
| `page_context_push` | `{ type, is_live_tracking, url, title, text, selection, intent }` | Send tab context |
| Response | `{ id, ...result }` | Reply to backend request |

### Backend → Extension

| Type | Shape | Purpose |
|------|-------|---------|
| `search` | `{ id, action: "search", url }` | Open search URL, scrape results |
| `get_active_tab` | `{ id, action: "get_active_tab" }` | Extract tab context |
| `capture_screenshot` | `{ id, action: "capture_screenshot" }` | JPEG screenshot with hints |
| `browser_action` | `{ id, action: "browser_action", payload }` | DOM interaction |
| `fetch_urls` | `{ id, action: "fetch_urls", urls }` | Background fetch multiple URLs |
| `get_cookies` | `{ id, action: "get_cookies", url }` | Get cookies (with consent) |
| `ui_status` | `{ id, action: "ui_status", payload }` | Fire-and-forget UI overlay |
| `page_context_response` | `{ type, thread_id }` | Return active thread ID |
| `RELOAD` | `{ type: "RELOAD" }` | Force extension reload |
