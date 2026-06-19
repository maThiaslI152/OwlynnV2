---
status: active
category: architecture
last_updated: 2026-06-10
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

When `mode == "api"`, interrupts are disabled. This prevents `GraphInterrupt` exceptions from producing empty responses. Instead:
- Ambiguous skill matches → auto-select top skill or "all" toolbox
- Low router confidence → use `complex-cloud` route (best-effort, HITL gating by security proxy)
- Sensitive tool calls → **denied by default** unless the client sets `auto_approve_sensitive: true` on the OpenAI-compat request (see `security_proxy.py`)

## Known Issues

1. **Code refactoring false positive** — "write an improved version" triggers scope_clarify unnecessarily. Partially mitigated by `_REFACTOR_SIGNALS` in `scope_heuristics.py`.
2. **Confidence always 95%** — the router's confidence score is not calibrated and doesn't reflect actual quality.
3. **No self-awareness** — the system never detects when it gives wrong answers. No recovery mechanism.

## Related Files

- `src/agent/nodes/router.py` — Router HITL decisions
- `src/agent/nodes/scope_clarify.py` — Scope clarification node
- `src/agent/nodes/plan_review.py` — Plan review before sensitive execution
- `src/agent/nodes/security_proxy.py` — Security policy enforcement
- `src/agent/hitl/scope_heuristics.py` — Build/create detection heuristics
- `src/config/defaults.yaml` — HITL thresholds and feature flags
