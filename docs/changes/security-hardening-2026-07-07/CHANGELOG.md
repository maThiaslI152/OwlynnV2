# Security Hardening — 2026-07-07

## What

Seven security fixes closing gaps in authentication, authorization, tool sandboxing, and prompt injection defenses.

## Why

Security audit identified that the HITL safety system was effectively disabled by default, the OpenAI-compatible API endpoint had no authentication, and several tool sandboxes had bypass vectors.

## Changes

### 1. `/v1/chat/completions` authentication

- Added `_verify_openai_token()` to the OpenAI-compatible endpoint (same loopback + timing-safe token check as `LocalAuthMiddleware`)
- Endpoint was previously exempt from auth (outside `/api/*` prefix)
- **Files:** `src/api/routes/openai.py`, `src/api/server.py`

### 2. `auto_approve_sensitive` removed from API surface

- Client can no longer override HITL policy via request body
- Hardcoded to `False` in the endpoint; server-side state only
- **Files:** `src/api/routes/openai.py`, `src/api/server.py`

### 3. Execution policy default changed

- Default changed from `auto_approve` to `require_approval` in both `security_proxy_node` and `plan_review_node`
- Sensitive tools (write, edit, delete, notebook, flashcard) now trigger HITL interrupt by default
- Users can opt into `auto_approve` via profile `execution_policy` setting
- **Files:** `src/agent/nodes/security_proxy.py`, `src/agent/nodes/plan_review.py`

### 4. Notebook sandbox hardened

- Removed `requests` and `httpx` from `_ALLOWED_MODULES` import whitelist
- Sandboxed code can no longer make arbitrary HTTP requests
- Only safe stdlib + data science modules (numpy, pandas, matplotlib, etc.) remain
- **File:** `src/tools/notebook_worker.py`

### 5. SSRF protection on `download_to_workspace`

- Added `url_fetch_blocked_reason()` check before downloading
- Blocks private IPs, localhost, cloud metadata (169.254.169.254), link-local, multicast
- **File:** `src/tools/core_tools.py`

### 6. Prompt injection boundary on `fetch_webpage`

- Web content now wrapped in `<web_context>` tags (same pattern as `deep_research`)
- Prevents attacker-controlled web pages from injecting instructions into LLM context
- **File:** `src/tools/web_tools.py`

### 7. Memory write injection sanitizer

- Added `_neutralize_injection()` to `pii_scrubber.py` — detects and redacts common prompt injection patterns ("ignore previous instructions", "you are now", XML/tag injection)
- Added `scrub_for_memory_write()` — full pipeline: PII scrub + injection neutralization
- Memory write node uses the full pipeline and logs when injection is neutralized
- **Files:** `src/agent/pii_scrubber.py`, `src/agent/nodes/memory.py`

### 8. Destructive command blocking in scope guard

- Added `_DESTRUCTIVE_CMD_RE` — blocks `rm -rf /`, `mkfs`, `dd` to device, fork bombs, `chmod -R 777 /`, `shutdown`, `reboot`
- Runs before scope check — blocks catastrophic commands regardless of engagement state
- **File:** `src/tools/scope_guard.py`

## Verification

```
ruff check:     All checks passed
ruff format:    All files formatted
mypy:           Success: no issues found
```

## Related

- [`docs/HITL.md`](../../HITL.md) — HITL system documentation
- [`docs/features/TOOLS.md`](../../features/TOOLS.md) — Tools reference
- [`docs/features/MEMORY.md`](../../features/MEMORY.md) — Memory system
- [`AGENTS.md`](../../../AGENTS.md) — Agent onboarding (learned rules)
