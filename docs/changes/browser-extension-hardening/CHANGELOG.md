# Browser Extension Hardening — Security, Navigation, Batch Selection, Moodle

> **Date:** 2026-06-28
> **Status:** COMPLETE
> **Version:** 1.2.0 → 1.3.0

## Overview

Comprehensive hardening of the Owlynn browser extension: security fixes, new navigation actions, batch selection improvements, and Moodle framework enhancements.

## Security Hardening (5 fixes)

### 1. XSS via innerHTML (BUG-33)
**Severity:** HIGH

`content_ui.js` set `innerHTML` from WebSocket messages, allowing potential script injection.

**Fix:** Replaced `innerHTML` with `textContent`/DOM APIs. Added `sanitize()` function. Status updates use `buildStatusHtml()` with DOM APIs.

### 2. WS Token Exchange Auth (BUG-34)
**Severity:** MEDIUM

Any local process could connect to the WS endpoint and issue browser commands.

**Fix:**
- Backend generates token on startup → writes to `~/.owlynn/browser_extension_token`
- `GET /api/browser_extension/token` endpoint (CORS restricted to extension origin)
- WS handler validates auth token as first message
- Extension fetches token on connect, re-fetches on reconnect

### 3. Cookie Consent (BUG-36)
**Severity:** MEDIUM

Backend could request cookies for any domain without user approval.

**Fix:** Added `confirm()` dialog before returning cookies. Per-session cache (cleared on extension restart).

### 4. CSP in Manifest
**Severity:** LOW

No Content Security Policy declared.

**Fix:** Added `content_security_policy` to manifest.json: `script-src 'self'; object-src 'self'; frame-src http://127.0.0.1:*`

### 5. Configurable Sidebar URL (BUG-14)
**Severity:** LOW

Hardcoded `http://127.0.0.1:5173` in `content_ui.js`.

**Fix:** Added URL field to popup UI. Stored in `chrome.storage.local`. Default to `http://127.0.0.1:5173`.

## Bug Fixes (3 fixes)

### 6. `.lower` Typo (BUG-35)
`content_google.js` used `.lower` instead of `.toLowerCase()`. Fixed.

### 7. DOM Tree Size Cap (BUG-37)
`buildDomTree.js` had no size limit. Added `MAX_ELEMENTS=500`, `MAX_CHARS=100000`.

### 8. Rate Limiting
Added `MAX_QUEUE_SIZE=10`, `MIN_COMMAND_INTERVAL_MS=100` to prevent command flooding.

## Navigation Enhancements (5 new actions)

| Action | Description | File |
|--------|-------------|------|
| `wait_for_navigation` | Wait for page load after click/submit (10s timeout) | `content_interact.js` |
| `scroll_to_element` | Scroll element into view with smooth behavior | `content_interact.js` |
| `select_option` | Select dropdown option by value/text | `content_interact.js` |
| `submit_form` | Submit parent form via `closest('form')` | `content_interact.js` |
| `focus` | Focus element for keyboard navigation | `content_interact.js` |

## Batch Selection Enhancements (3 new actions)

| Action | Description | File |
|--------|-------------|------|
| `select_checkboxes` | Batch check/uncheck checkboxes by `element_ids` | `content_interact.js` |
| `select_radio` | Select radio button by `element_id` | `content_interact.js` |
| `type_into_sequence` | Type into multiple fields with Tab between | `content_interact.js` |

## Moodle Framework Enhancements (6 new extractions)

| Extraction | Selectors | Output |
|------------|-----------|--------|
| **Grades** | `.gradestable`, `#user-grades`, `.generaltable` | Structured grades data |
| **Course sections** | `.section`, `.sectionname`, `.section-info` | Section titles + activities |
| **Assignments** | `.assignsubmission`, `.duedate`, `.submissionstatus` | Due dates, status |
| **File links** | `.resource a[href]`, `.modtype_resource a[href]` | File URLs |
| **Quiz navigation** | `.qn_buttons`, `.qnbutton`, `.mod_quiz-next-nav` | Total questions, navigation |
| **User profile** | `.userprofile`, `.username`, `.user-email` | Name, email, avatar |

## Robustness Improvements

| Improvement | Description |
|-------------|-------------|
| **Service worker keepalive** | `chrome.alarms` with 0.5min period to prevent MV3 termination |
| **Tab ID pinning** | Verify tab ID matches request before action |
| **Re-auth on reconnect** | Re-fetch token on WS disconnect |

## Files Changed

| File | Changes |
|------|---------|
| `browser-extension/manifest.json` | CSP, version bump 1.2.0 → 1.3.0 |
| `browser-extension/background.js` | Auth, cookie consent, rate limiting, keepalive, tab pinning |
| `browser-extension/content_ui.js` | XSS fix, configurable URL, cookie consent handler |
| `browser-extension/content_interact.js` | 8 new actions |
| `browser-extension/content_moodle.js` | 6 new extractions |
| `browser-extension/buildDomTree.js` | Size cap (500 elements, 100KB) |
| `browser-extension/content_google.js` | `.lower` typo fix |
| `browser-extension/popup.html` | URL config field |
| `browser-extension/popup.js` | URL config logic |
| `src/api/routes/browser_extension.py` | Token generation, auth validation |
| `tests/test_browser_extension_api.py` | Auth token in test |

## Verification

- CI: All checks passed (1054 Python tests, 130 frontend tests)
- `test_extension_websocket_lifecycle`: Passes with auth token
- Syntax check: All JS files pass `node -c`
