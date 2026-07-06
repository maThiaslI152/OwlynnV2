---
status: active
category: architecture
last_updated: 2026-07-07
owner: ai-agent
audience: agent
---

# HITL — Human-in-the-Loop Safety System

> **Purpose:** Safety gates (scope clarify, plan review, security proxy) and interrupt contract.

## Overview

Owlynn uses a multi-gate HITL system to keep the agent safe while minimizing interruptions. The system intercepts sensitive tool calls and ambiguous routing decisions, asking the user for approval before proceeding.

## HITL Gates

| Gate | Location | When It Triggers |
|------|----------|-----------------|
| **Router HITL** | `router.py:470-534` | LLM router confidence < 60% OR skill matcher finds ambiguous matches |
| **Scope Clarify** | `scope_clarify.py` | Underspecified build/create requests (e.g. "build a calculator" with no language/UI specified) |
| **Plan Review** | `plan_review.py` | Tool calls matching sensitive policy (file deletion, network access, execution) |
| **Security Proxy** | `security_proxy.py` | Destructive, network, or privilege-escalation tool calls |

## How Interrupts Work

The system uses LangGraph's `interrupt()` to pause the graph. In **browser mode** (WebSocket), the frontend displays a HITL prompt card with choice buttons. The user selects an option and the graph resumes.

In **API mode** (`mode: "api"`), interrupts are **skipped** — there's no human to respond. The router auto-resolves ambiguities and falls through to the best available route.

## Configuration

All thresholds are in `src/config/defaults.yaml`:

```yaml
routing:
  hitl_enabled: true
  confidence_threshold: 0.6       # Trigger HITL when confidence < 60%
  skill_clarification_threshold: 0.5
  scope_clarification_enabled: true
  plan_review_enabled: true
```

## API Mode Behavior

When `mode == "api"`, the `/v1/chat/completions` endpoint requires authentication (same token as `/api/*` routes) and defaults to HITL-enabled behavior:

- **Authentication:** `_verify_openai_token()` enforces loopback + timing-safe token check (same as `LocalAuthMiddleware`)
- **Sensitive tool calls** → HITL interrupt (user must approve via WebSocket)
- **`auto_approve_sensitive` is hardcoded to `False`** — the client cannot override security policy via the request body
- To opt into auto-approve for automated runs, set `auto_approve_sensitive: true` in the agent state server-side (not exposed to the API caller)

## Execution Policy

The `execution_policy` profile setting controls whether sensitive tools require HITL approval:

| Policy | Behavior |
|--------|----------|
| `require_approval` (default) | All sensitive tools trigger HITL interrupt |
| `auto_approve` | Sensitive tools auto-approve unless they hit a "redline" risk category |

**Redline risks** (always require HITL even with `auto_approve`):
- `destructive_action` — file deletion, drop, truncate
- `network_exfiltration` — curl, wget, scp, HTTP URLs
- `privilege_escalation` — sudo, chmod, chown

The plan review gate respects the same policy: when `execution_policy == "auto_approve"`, plan review is skipped.

### Scope Guard: Destructive Command Blocking

The scope guard (`src/tools/scope_guard.py`) blocks catastrophic commands regardless of engagement state:

- `rm -rf /`, `mkfs`, `dd if=... of=/dev/`, fork bombs, `chmod -R 777 /`, `shutdown`, `reboot`
- These are blocked even without an active pentest engagement
- Extracted network targets are still validated against engagement scope when one exists

## Known Issues

1. **Code refactoring false positive** — "write an improved version" triggers scope_clarify unnecessarily. Partially mitigated by `_REFACTOR_SIGNALS` in `scope_heuristics.py`.
2. **Confidence always 95%** — the router's confidence score is not calibrated and doesn't reflect actual quality.
3. **No self-awareness** — the system never detects when it gives wrong answers. No recovery mechanism.

## Related Files

- `src/agent/nodes/router.py` — Router HITL decisions
- `src/agent/nodes/scope_clarify.py` — Scope clarification node
- `src/agent/nodes/plan_review.py` — Plan review before sensitive execution
- `src/agent/nodes/security_proxy.py` — Security policy enforcement, execution policy evaluation
- `src/agent/hitl/scope_heuristics.py` — Build/create detection heuristics
- `src/tools/scope_guard.py` — Pentest scope enforcement, destructive command blocking
- `src/agent/pii_scrubber.py` — PII scrubbing + prompt injection neutralization for memory writes
- `src/config/defaults.yaml` — HITL thresholds and feature flags
