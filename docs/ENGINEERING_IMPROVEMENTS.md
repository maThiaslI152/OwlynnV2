---
status: active
category: planning
last_updated: 2026-05-31
owner: human
---

# Engineering improvement suggestions

> **Purpose:** Prioritized engineering improvement suggestions for the Owlynn project.

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

## Summary table (original items)

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

## Improvements from Completeness Review (2026-06-10)

> Source: [`docs/COMPLETENESS_REVIEW.md`](COMPLETENESS_REVIEW.md) — frontier chat & co-work gap analysis.
> Bug fixes from this review are tracked as BUG-17..20 in [`docs/BUG-TRACKER.md`](BUG-TRACKER.md).

### IMP-1: Implement Token Budget + Cloud Budget WS Events

**Context:** `token_budget_update` and `cloud_budget_warning` events are documented in [`docs/CHAT_PROTOCOL.md`](CHAT_PROTOCOL.md) as planned but not implemented. Users have no real-time budget visibility during long generations or when approaching daily limits.

**Improvement:** Emit both event types from `ws/handler.py` during streaming. `token_budget_update` during chunk streaming; `cloud_budget_warning` once per level (info/warning/critical) from `SessionCostTracker`.

**Files:** `src/api/ws/handler.py`, `src/agent/cloud_cost_tracker.py`, `frontend-v2/src/App.tsx`  
**Effort:** 1–2 days | **Impact:** High — transparency + cost control UX

---

### IMP-2: Document RAG UX Polish (LocalDocs Parity)

**Context:** File watcher + Qdrant + `search_workspace_docs` work (W1.1 now passes), but:
- No indexing progress indicator (progress %, per-file indexed/pending status in UI)
- No hybrid BM25 + vector search (Qdrant supports sparse vectors)
- No "drop a folder → ask questions" seamless flow visible to new users

**Improvement:**
1. Add `file_indexing_progress` WS event (`{name, status: "indexing|indexed|failed", chunk_count}`) from `files.py`
2. Render per-file status in `ProjectKnowledgePanel.tsx`
3. Add BM25 sparse vector path in `rag_tools.py` for hybrid re-ranking
4. Add onboarding hint in empty knowledge panel: "Drop files here to ask questions about them"

**Files:** `src/api/routes/files.py`, `src/tools/rag_tools.py`, `frontend-v2/src/components/ProjectKnowledgePanel.tsx`  
**Effort:** 3–5 days | **Impact:** Very High — GPT4All LocalDocs parity

---

### IMP-3: Push-to-Talk Voice Input (Whisper STT)

**Context:** Live Talk (wake-word + STT) was removed April 2026. Only TTS remains. All frontier chat products have voice input. A simpler push-to-talk approach avoids the ObjC FFI crashes that killed Live Talk.

**Improvement:**
1. Mic button in `Composer.tsx`: `navigator.mediaDevices.getUserMedia()` + `MediaRecorder` API → send WAV/WebM to backend
2. `POST /api/transcribe` endpoint using `faster-whisper` (`tiny.en`, <200 MB, Apple Silicon optimised)
3. Transcription text inserted into composer input (not auto-sent — user reviews and sends)
4. No continuous listening, no wake words

**Files:** `src/api/routes/` (new `transcribe.py`), `frontend-v2/src/components/Composer.tsx`  
**Effort:** 2–4 days | **Impact:** Medium-High — frontier parity for voice

---

### IMP-4: Thread / Conversation Organization

**Context:** As conversation history grows, there is no way to search, pin, tag, or date-group past chats. Jan's thread view is a good reference.

**Improvement:**
1. `GET /api/chats/search?q=<term>` — full-text search over chat titles and first messages
2. `pinned: bool` field in chat metadata → pinned chats sorted to top in sidebar
3. `tags: string[]` on chat metadata — filter by tag in sidebar
4. Date grouping: Today / Yesterday / This Week / Older in sidebar `AppShell.tsx`

**Files:** `src/api/routes/projects.py` (or new `chats.py`), `frontend-v2/src/components/AppShell.tsx`  
**Effort:** 2–3 days | **Impact:** Medium — growing history UX

---

### IMP-5: In-App Model Browser

**Context:** All model management requires leaving Owlynn to use LM Studio. Competitors (LM Studio, Jan) offer in-app discovery and one-click assignment.

**Improvement:**
1. `GET /api/models/loaded` — proxy `GET http://127.0.0.1:1234/v1/models` from LM Studio
2. Settings panel section: shows currently loaded models, assigns to `small`/`medium` slots
3. (Stretch) HuggingFace model search via HF API filtered to MLX-compatible models
4. Saves assignment to `user_profile.json` overrides (no `defaults.yaml` edits required)

**Files:** `src/api/routes/` (new `models.py`), `frontend-v2/src/components/CloudSettingsPanel.tsx` (or new `ModelSettingsPanel.tsx`)  
**Effort:** 3–5 days | **Impact:** High — model management UX

---

### IMP-6: Response Coherence / Self-Correction Loop

**Context:** The agent has no mechanism to detect wrong answers (HITL.md: "No self-awareness"). No recovery or retry on quality. Cursor and Devin use compiler/test output as a feedback signal.

**Improvement:**
1. After `complex_llm_node` produces a response, run a lightweight quality gate: detect empty content, detect raw tool-call markup, detect "I don't know" on factual turns
2. On quality failure: retry with synthesis prompt (similar to BUG-13 fix for web search)
3. For code responses: optionally run `notebook_run` on short snippets to validate syntax
4. Track retry count in `router_metadata` for telemetry

**Files:** `src/agent/nodes/complex.py`, `src/agent/nodes/complex_utils/formatter.py`  
**Effort:** 1–2 weeks | **Impact:** High — quality vs frontier

---

### IMP-7: Electron Desktop Revival

**Context:** Electron is "on hold" per STATUS.md. Safe Mode, Screen Assist window sizing, and TTS all require Electron IPC and have no browser fallback.

**Improvement:**
1. Audit which Electron IPC calls have no REST fallback and add REST fallbacks where feasible
2. Add `npm run electron:dev` to `start.sh` as an optional flag (`--desktop`)
3. Ensure Screen Assist panel works in Electron desktop mode with proper window management
4. Build + publish `.app` / `.dmg` artifacts in CI on `main` push

**Files:** `frontend-v2/electron/main.ts`, `frontend-v2/src/lib/electronBridge.ts`, `start.sh`  
**Effort:** 1 week | **Impact:** Medium — desktop completeness

---

### IMP-8: Coding Pair-Programming Depth (vs Cursor)

**Context:** Owlynn has file tools + screen assist, but no language-server integration, no diff/patch view (write = overwrite), no git context, and no compiler feedback loop. Cursor is deeply embedded in the editor.

**Improvement (incremental):**
1. **Diff view:** `edit_workspace_file` generates a unified diff and shows it in HITL plan review before applying
2. **Git context:** Add `git_status`, `git_diff`, `git_log` tools using `subprocess` + `gitpython`
3. **Syntax check:** For code responses, optionally run `py_compile` / `tsc --noEmit` and feed errors back as a tool result
4. **LSP (stretch):** pyright/pylsp subprocess for diagnostics on file reads

**Files:** `src/tools/core_tools.py` (new git tools), `src/agent/tool_sets.py`, `src/agent/nodes/security_proxy.py`  
**Effort:** 2–3 weeks | **Impact:** High — vs Cursor differentiation

---

## Updated Summary Table

| ID | Theme | Effort | Priority |
|----|-------|--------|----------|
| IMP-1 | Token/cloud budget WS events | 1–2 days | **High** |
| IMP-2 | Document RAG UX (LocalDocs) | 3–5 days | **Very High** |
| IMP-3 | Push-to-talk Whisper STT | 2–4 days | **Medium-High** |
| IMP-4 | Thread organization (search/pin/tag) | 2–3 days | **Medium** |
| IMP-5 | In-app model browser | 3–5 days | **High** |
| IMP-6 | Response coherence / self-correction | 1–2 weeks | **High** |
| IMP-7 | Electron desktop revival | 1 week | **Medium** |
| IMP-8 | Coding pair-programming depth | 2–3 weeks | **High** (strategic) |

---

## How to use this doc

1. Open an issue per item when work starts.
2. For architectural choices, add an **ADR** in `docs/ADR.md` instead of only editing this file.
3. When an item is done or rejected, update **this file** or `docs/STATUS.md` so agents do not re-propose stale work.

## Related

- [`docs/STATUS.md`](STATUS.md) — project status and risks
- [`docs/COMPLETENESS_REVIEW.md`](COMPLETENESS_REVIEW.md) — source of IMP-1..8 (frontier gap analysis 2026-06-10)
- [`docs/BUG-TRACKER.md`](BUG-TRACKER.md) — BUG-17..20 (reliability bugs from same review)
- [`docs/COMPETITIVE_FEATURE_ANALYSIS.md`](COMPETITIVE_FEATURE_ANALYSIS.md) — detailed competitor gap analysis

## Last updated

2026-06-10 — IMP-1..8 added from completeness review (frontier chat & co-work comparison)
