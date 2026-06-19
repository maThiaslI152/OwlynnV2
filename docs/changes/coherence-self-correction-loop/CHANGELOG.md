---
status: active
category: changelog
audience: agent
last_updated: 2026-06-18
owner: ai-agent
---

# Changelog: Coherence Self-Correction Loop (R5 / IMP-6)

> **Purpose:** Convert the existing `coherence_check` telemetry into an actionable retry cycle. When a response grades below the confidence threshold, transparently re-invoke the same model path with a synthesis nudge before surfacing to the user. Bounded by `coherence.max_retries` (default 1).

## Verified

- 2026-06-18 — code complete; targeted tests pass (42/42 backend, 4/4 frontend vitest). **`./scripts/ci.sh --quick` deferred — user traveling; run before push.**
- Re-run frontier + educator eval deferred until CI passes.

## Symptom (what R5 closed)

- Coherence_check graded every turn and emitted `response_coherence` + `response_confidence`, but **never acted on a bad grade**. Low-quality answers reached the user unchanged.
- No automatic recovery from "I don't know" / off-topic / tool-failure responses. Same shape as `needs_web_synthesis_retry` (BUG-13) but generalized to all low-coherence cases.

## Files changed

| File | Change |
|------|--------|
| `src/agent/state.py` | New fields: `_coherence_retry_round: int \| None`, `coherence_retry_reason: str \| None`. |
| `src/config/defaults.yaml` | New `coherence:` block: `retry_threshold: 0.4`, `max_retries: 1`, `retry_token_budget: 2048`, `enabled: true`. |
| `src/agent/nodes/coherence_retry.py` (NEW) | New node. Mirrors `complex.py:1490-1546` synthesis-retry pattern: builds nudge from last user query + prior confidence/reason, invokes cloud (`_invoke_cloud_path`) or local medium (`get_medium_llm("default")`) per `state["route"]`, replaces last AI message with cleaned retry content. Respects `cloud_no_local_fallback_enabled()` — strict-cloud mode surfaces `coherence_retry` blocked in `fallback_chain` rather than silently falling back. |
| `src/agent/graph.py` | New `coherence_retry_gate()` conditional edge: `coherence_check → coherence_retry` (when `confidence < threshold AND rounds < max_retries`), else `→ memory_write`. Cycle edge `coherence_retry → complex_llm` so the new response flows through the normal pipeline and gets re-graded. |
| `src/api/ws/handler.py` | Emits `coherence_retry_started` (when below-threshold coherence emitted) and `coherence_retry_completed` (when retry node ends) WS events. |
| `frontend-v2/src/state/useAppStore.ts` | New state slice: `coherenceRetryActive`, `coherenceRetryAttempt`, `coherenceRetryOriginalConfidence`. `setCoherenceRetryActive(active, attempt, confidence)` action; `clearSession()` resets it. |
| `frontend-v2/src/App.tsx` | Wires `coherence_retry_started` / `coherence_retry_completed` WS events to the store action. |
| `frontend-v2/src/components/__tests__/coherence-retry.test.tsx` (NEW) | 4 vitest cases: initial state, activate, deactivate, clearSession reset. |
| `tests/test_coherence_retry_node.py` (NEW) | 7 cases: local-medium happy path, disabled, budget exhausted, strict-cloud block, cloud-invoke path, DSML strip, no-messages short-circuit. |
| `tests/test_coherence_graph_wiring.py` (NEW) | 11 cases: graph compiles with new node, gate routes retry when below threshold + budget, skips on high confidence / exhausted budget / missing confidence / disabled / exact threshold boundary. |
| `tests/test_response_coherence.py` | Added `test_coherence_check_node_below_retry_threshold` for coverage of <0.4 path. |

## Graph wiring

```
complex_llm ─┐
plan_review ─┼──► coherence_check ──score<0.4, _round<1──► coherence_retry ──┐
security_proxy ┤                   │                                          │
simple ────────┘                   └──score>=0.4 OR _round>=1──► memory_write ─┴─► END
                                    ▲                                          │
                                    └───────────────── complex_llm ◄───────────┘
```

Cycle is bounded by `_coherence_retry_round` counter (mirrors `_cutoff_round` pattern, proven safe under `recursion_limit: 100`).

## Config additions

```yaml
coherence:
  retry_threshold: 0.4      # below this confidence, retry
  max_retries: 1            # hard cap per turn
  retry_token_budget: 2048  # output budget for retry call
  enabled: true             # kill-switch for telemetry-only mode
```

## Nudge template

```
[QUALITY IMPROVEMENT NEEDED] Your previous answer scored {conf:.2f}/1.0 on
coherence (reason: {reason}). Address the user's original query: {query[:300]}

Write a complete, accurate answer. If you don't know, say so explicitly rather
than guessing. Do NOT output tool_calls, DSML, or partial markup.
```

## Behavior

- **Happy path**: confidence ≥ 0.4 → no retry, emit `response_coherence`, proceed to `memory_write`.
- **Bad response, retry allowed**: confidence < 0.4 AND rounds done < 1 → emit `coherence_retry_started` WS event, run `coherence_retry_node` (cloud `_invoke_cloud_path` or local medium), replace last AI message, cycle back through `complex_llm`. New response re-enters coherence_check.
- **Retry exhausted**: rounds done ≥ 1 → proceed to `memory_write` with whatever response we have (low confidence surface to user).
- **Strict cloud**: cloud failure with `cloud_no_local_fallback_enabled()` → block local fallback, append `strict_cloud_no_local_fallback` to `fallback_chain`, surface `[empty response after retry]` marker.
- **Empty response after retry**: kept prose if DSML split leaves a tail; else `[empty response after retry]` placeholder.

## Frontend UX

- `coherenceRetryActive` flag drives a transient "Improving answer…" indicator (component to be added in a follow-up; store wiring lands in this PR).
- `coherenceRetryOriginalConfidence` available for badge tooltip / debug panel.

## Risks / known limitations

- **No visible UI component yet.** Store/action wiring lands; the actual "Improving answer…" badge is a follow-up (small isolated UI work).
- **Adds 1 LLM call on bad path.** Adds ~1s (MiniCPM grade is unchanged — always runs) + ~3-8s local / 2-5s cloud for the retry. Happy-path latency unchanged.
- **No code-response validation** via `notebook_run` syntax check (IMP-6 item 3) — deferred.
- **No "I don't know" regex** — relies on MiniCPM5 coherence judgment alone.
- **CI gate deferred** — `./scripts/ci.sh --quick` not run before commit due to travel. Run before push and re-run frontier + educator evals to confirm score lift.

## Verification (run before push)

```bash
# Backend targeted
pytest tests/test_coherence_retry_node.py tests/test_coherence_graph_wiring.py \
       tests/test_response_coherence.py tests/test_graph.py -q

# Frontend targeted
cd frontend-v2 && npx vitest run src/components/__tests__/coherence-retry.test.tsx

# Full CI gate (deferred)
./scripts/ci.sh --quick

# Quality measurement (deferred)
python scripts/run_local_frontier_eval.py --profile cloud --strict-cloud
python scripts/run_educator_eval.py --profile cloud --strict-cloud
```

## Related

- `docs/STATUS.md` R5 entry — was "Open"; this PR closes it pending eval verification.
- `docs/ENGINEERING_IMPROVEMENTS.md` IMP-6 — was scoped; this PR ships the first half (retry-on-low-coherence). Code-validation pass deferred.
- `docs/changes/web-search-synthesis-fix/CHANGELOG.md` — sibling pattern this implementation mirrors.
