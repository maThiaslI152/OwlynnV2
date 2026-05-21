# Engineering improvement suggestions

This document captures prioritized improvement ideas for Owlynn. It is **advisory**: nothing here is a commitment until tracked in issues or `docs/STATUS.md`.

**Audience:** maintainers, contributors, and AI agents planning work.

**Related:** `docs/STATUS.md` (current risks), `docs/PERFORMANCE_SLOS.md` (targets), `docs/ADR.md` (decisions), `.cursor/rules/local-ci.mdc` (local CI).

---

## 1. Critical: automated CI beyond the laptop

**Context:** The project uses **local CI** via `scripts/ci.sh` (and optionally a pre-push hook) to avoid burning GitHub Actions quota. That is a deliberate trade-off documented in workspace rules.

**Improvement:** Add an **optional** automated pipeline (e.g. GitHub Actions on `main` + PRs, or another runner) that runs the same gates as `scripts/ci.sh`, or a subset (Python + vitest only) on a schedule.

**Suggested gates (align with `scripts/ci.sh`):**

- `pytest -q -m "not network" --tb=short`
- Audit/contract subset: `test_verify_report_fixture.py`, `test_websocket_event_contract.py`, `test_frontend_cutover_serving.py`
- `cd frontend-v2 && npx vitest run`
- `cd frontend-v2 && npm run build` (nightly or on release branches if full build is heavy)

**Impact:** Catches regressions when local hooks are skipped or environments differ.

---

## 2. High: frontend test and state coverage

**Gap:** Core UI behavior depends heavily on `frontend-v2/src/state/useAppStore.ts` and WebSocket handling (`frontend-v2/src/lib/wsClient.ts`). Contract tests exist on the backend; the frontend benefits from more **unit and integration** coverage around:

- Store actions (messages, connection, tool/security flows, project context).
- `WsClient` lifecycle and malformed payloads (partially covered; extend as protocol evolves).
- Markdown rendering edge cases and failure modes.

**Impact:** Safer refactors when changing `App.tsx`, protocol types, or inspector panels.

---

## 3. High: resilience and graceful degradation

**Observation:** The stack depends on several external or local services (LM Studio, Qdrant, Redis, optional SearxNG, Mem0). Failures should **degrade** where possible instead of failing the whole turn.

**Suggestions:**

- Consistent **timeouts and retries** for HTTP clients (LM Studio, search providers, Mem0/Qdrant).
- **Circuit-breaker or backoff** patterns for flaky dependencies (document behavior in `docs/ADR.md` when chosen).
- Where safe, **isolate memory failures** from the reasoning path (e.g. log + continue with empty memory context rather than aborting the graph), with explicit metrics or logs for operators.

**Impact:** Better day-to-day reliability on laptops with optional services stopped.

---

## 4. Medium: structured logging and traceability

**Suggestion:** Prefer **structured logs** (JSON or key-value) for server paths that interleave: WebSocket thread id, project id, route, tool names, and latency. Keep correlation across a single user turn.

**Optional:** OpenTelemetry or similar for LangGraph spans if operational complexity is acceptable.

**Impact:** Faster post-mortems and easier alignment with `docs/PERFORMANCE_SLOS.md` checks.

---

## 5. Medium: frontend maintainability

**Suggestions:**

- **Split large CSS:** `frontend-v2/src/index.css` is very large; consider scoped modules or clearer sectioning as features grow.
- **Zustand shape:** If `useAppStore` grows further, consider **slices** or feature-scoped stores to reduce coupling and test surface.
- **Error boundaries:** Add React error boundaries around major regions (shell, conversation, inspector) so one panel failure does not blank the entire app.

**Impact:** Easier onboarding and safer UI iteration.

---

## 6. Medium: security hardening (defense in depth)

**Existing:** Security proxy / HITL for sensitive tools is a strong baseline.

**Additional hardening ideas:**

- **Path safety:** Audit workspace file tools for `..` and symlink escape; enforce canonical paths under the workspace root.
- **Notebook / REPL:** Treat as high risk; document threat model; consider stronger isolation (separate process, container, or OS sandbox) if execution moves beyond trusted dev machines.
- **MCP configuration:** Treat `mcp_config.json` as trusted input; consider validation, checksums, or explicit user approval for new servers.

**Impact:** Reduces blast radius if prompts or configs are hostile or mistaken.

---

## 7. Medium: performance and resource discipline

**Ideas:**

- **LLM concurrency:** Cap parallel local LLM calls to avoid GPU / unified memory contention on Apple Silicon (align with SLOs in `docs/PERFORMANCE_SLOS.md`).
- **Memory I/O:** Batch or debounce expensive memory operations where the graph allows.
- **Frontend:** Lazy-load heavy panels if bundle or initial parse time grows.

**Impact:** Keeps latency and thermals within documented envelopes.

---

## 8. Low–medium: developer experience

**Suggestions:**

- Document a **standard dev loop** (backend reload, frontend HMR, Tauri dev vs debug `.app` for permissions) in one place (`README.md` or `docs/guides/quickstart.md`).
- **Type checking in CI:** `mypy` (incremental strictness) and `tsc --noEmit` where feasible.
- **Pre-commit:** Optional hooks for format/lint to match CI.

**Impact:** Fewer “works on my machine” deltas.

---

## 9. Low: architecture and product knobs

**Ideas:**

- **Graph / checkpoint compatibility:** When LangGraph topology changes, document migration or versioning for checkpoints (ADR if non-trivial).
- **Tool extensibility:** A small plugin or registration API for tools could reduce core churn.
- **Rate limiting:** Consider limits on WebSocket message rates per connection in untrusted or multi-user deployments (less critical for strict single-user local).

---

## Summary table

| Priority   | Theme                         | Effort (rough) |
|-----------|--------------------------------|----------------|
| Critical  | Optional remote CI + parity    | 0.5–2 days     |
| High      | Frontend store / WS tests    | 2–5 days       |
| High      | Service resilience patterns    | 3–7 days       |
| Medium    | Structured logging / traces  | 2–4 days       |
| Medium    | Frontend boundaries / CSS    | Ongoing        |
| Medium    | Security depth (paths, MCP)  | 2–5 days       |
| Medium    | Performance / concurrency    | 2–5 days       |
| Low–med   | DevX, mypy, pre-commit       | 1–3 days       |
| Low       | Plugins, graph versioning      | Multi-sprint   |

---

## How to use this doc

1. Open an issue per item when work starts.
2. For architectural choices, add an **ADR** in `docs/ADR.md` instead of only editing this file.
3. When an item is done or rejected, update **this file** or `docs/STATUS.md` so agents do not re-propose stale work.

_Last updated: 2026-05-11_
