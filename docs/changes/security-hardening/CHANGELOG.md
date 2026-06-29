# Security Hardening — 2026-06-29

## Summary

Comprehensive security audit and hardening of the OwlynnV2 project. Addressed critical, high, medium, and low severity vulnerabilities across backend API, WebSocket, Electron, browser extension, and Docker infrastructure.

## Changes by Severity

### Critical Fixes

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| 1.1 | Unauthenticated WebSocket | Added token-based auth to `/ws/chat/{thread_id}` using `X-Owlynn-Run-Token` | `src/api/ws/handler.py`, `frontend-v2/src/App.tsx` |
| 1.2 | Unauthenticated REST endpoints | Added `LocalAuthMiddleware` to all `/api/*` routes | `src/api/server.py`, `frontend-v2/src/lib/localRunToken.ts` |
| 1.3 | Browser extension token exposed | Added origin validation to `GET /api/browser_extension/token` | `src/api/routes/browser_extension.py` |
| 1.4 | Notebook exec() sandbox | Restricted builtins, added 30s timeout, whitelisted safe imports | `src/tools/notebook_worker.py` |

### High Severity Fixes

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| 2.1 | CORS too permissive | Restricted to specific methods and headers | `src/api/server.py` |
| 2.3 | Mermaid innerHTML XSS | Added DOMPurify sanitization | `frontend-v2/src/lib/interactiveBlocks/InteractiveMermaid.tsx` |
| 2.4 | SSH host key verification | Only disable for localhost (Lima VM) | `src/tools/screen_assist/kali_ssh.py` |
| 2.5 | Electron exec() injection | Changed to `execFile()` for screen capture | `frontend-v2/electron/main.ts` |
| 2.6 | IPC channel exposure | Whitelisted specific IPC channels | `frontend-v2/electron/preload.ts` |
| 2.7 | Profile endpoint accepts arbitrary fields | Removed `deepseek_api_key` from `VALID_FIELDS` | `src/memory/user_profile.py` |

### Medium Severity Fixes

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| 3.1 | Docker ports exposed | Bound all ports to `127.0.0.1` | `docker-compose.yml` |
| 3.2 | No security headers | Added `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy` | `src/api/server.py` |
| 3.3 | API key logging | Removed key prefix from rotation logs | `src/config/secret_store.py` |

### Low Severity Fixes

| # | Issue | Fix | Files |
|---|-------|-----|-------|
| 4.1 | .gitignore missing patterns | Added `*.pem`, `*.key`, `*.cert`, `*.p12`, `*.pfx` | `.gitignore` |

## Architecture

### Authentication Flow

```
Frontend                    Backend
    │                          │
    ├─ GET /api/local-run-token ──►  Returns token (localhost only)
    │                          │
    ├─ WS /ws/chat/{id}?token=X ──►  Validates token, accepts WS
    │                          │
    ├─ API /* + X-Owlynn-Run-Token ──►  Middleware validates token
    │                          │
    └─ Browser Extension ──────►  Origin validation + WS token auth
```

### Token Management

- **Token storage**: `app.state.local_run_token` (generated on startup)
- **Token exposure**: `/api/local-run-token` (localhost only)
- **Token usage**: Query parameter for WS, header for REST
- **Browser extension**: Separate token at `~/.owlynn/browser_extension_token`

## Files Modified

### Backend
- `src/api/server.py` — Added `LocalAuthMiddleware`, `SecurityHeadersMiddleware`, `/api/local-run-token` endpoint, `secrets` import, CORS restriction
- `src/api/ws/handler.py` — Added token validation on WS connect
- `src/api/routes/browser_extension.py` — Added `Request` import, origin validation for token endpoint
- `src/api/local_auth.py` — No changes (existing token infrastructure used)
- `src/tools/notebook_worker.py` — Restricted builtins, added timeout, whitelisted safe imports
- `src/tools/screen_assist/kali_ssh.py` — Conditional SSH host key checking
- `src/config/secret_store.py` — Removed key prefix from rotation logs
- `src/memory/user_profile.py` — Removed `deepseek_api_key` from `VALID_FIELDS`
- `docker-compose.yml` — Bound ports to `127.0.0.1`

### Frontend
- `frontend-v2/src/App.tsx` — Added `localRunToken` state, token fetch, WS URL with token, `fetchWithAuth` usage
- `frontend-v2/src/lib/localRunToken.ts` — Added `fetchWithAuth` wrapper
- `frontend-v2/src/lib/interactiveBlocks/InteractiveMermaid.tsx` — Added DOMPurify sanitization
- `frontend-v2/src/lib/interactiveBlocks/InteractiveCell.tsx` — Updated to use `fetchWithAuth`
- `frontend-v2/electron/main.ts` — Changed `exec` to `execFile`
- `frontend-v2/electron/preload.ts` — Added IPC channel whitelisting
- `frontend-v2/src/components/MemoryPanel.tsx` — Updated to use `fetchWithAuth`
- `frontend-v2/src/components/SafeModePanel.tsx` — Updated to use `fetchWithAuth`
- `frontend-v2/src/components/Composer.tsx` — Updated to use `fetchWithAuth`
- `frontend-v2/src/components/ProjectKnowledgePanel.tsx` — Updated to use `fetchWithAuth`
- `frontend-v2/src/components/CloudSettingsPanel.tsx` — Updated to use `fetchWithAuth`
- `frontend-v2/src/components/DeckBrowserModal.tsx` — Updated to use `fetchWithAuth`

### Tests
- `tests/test_websocket_event_contract.py` — Added `_ws_url` helper, updated all WS connections
- `tests/test_websocket_model_key_updates.py` — Added `_ws_url` helper, updated all WS connections
- `frontend-v2/src/components/__tests__/components.extended.test.tsx` — Added `localRunToken` mock
- `frontend-v2/src/components/__tests__/cloud-settings.test.tsx` — Added `localRunToken` mock

### Dependencies
- `frontend-v2/package.json` — Added `dompurify` and `@types/dompurify`

## Exempt Paths

The following API paths are exempt from token authentication:

- `/api/health` — Used by frontend to check readiness
- `/api/local-run-token` — Used by frontend to fetch the token
- `/api/usage` — Read-only stats
- `/api/cloud-status` — Read-only
- `/api/browser_extension/*` — Has its own WS token auth
- `/api/study/*` — Read-only dashboard, no sensitive data

## Breaking Changes

None. The authentication is transparent to the frontend (token is fetched automatically).

## Verification

```bash
# Run full CI
./scripts/ci.sh --quick

# Expected output:
# ✓ Ruff lint checks passed
# ✓ Ruff format checks passed
# ✓ Mypy type checks passed
# ✓ Unit tests passed (1054 passed, 5 skipped)
# ✓ Audit/contract tests passed
# ✓ Frontend linting passed
# ✓ Frontend tests passed (130 passed)
# All checks passed.
```
