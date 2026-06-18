---
status: active
category: evaluation
audience: agent
last_updated: 2026-06-18
---

# Strict Cloud Debug — 2026-06-16/17

**Goal:** Exercise compute paths as if local Qwen fallback did not exist; surface real cloud failures via `large-cloud-failed` / `small-local-failed`.

## Implementation

| Component | Change |
|-----------|--------|
| `src/agent/cloud_strict.py` | `cloud_no_local_fallback_enabled()`, `block_cloud_local_fallback()` |
| `src/agent/nodes/complex.py` | Block all cloud→Qwen fallback sites when strict |
| `src/agent/nodes/simple.py` | Block small→medium fallback; MiniCPM `max_tokens` floor + `reasoning_content` fallback |
| `src/config/env_files.py` | Auto-load `.env` / `.env.local` |
| Eval scripts | `--strict-cloud`, scope/plan/security HITL disabled during runs (`execution_policy=auto_approve`), WS-idle + turn-scoped assistant capture |
| `cloud_payload.py` | Compact completed `write_workspace_file` tool-call args on cloud replay (BUG-27) |
| `frontend-v2/src/App.tsx` | Clear `pendingCorrelationId` on any `status: idle` + `assistant.message` |

## Tier A — Frontier (19 turns)

```bash
python scripts/run_local_frontier_eval.py --profile cloud --strict-cloud
```

**Result:** **91.33%** (1644/1800) — 18 scored, 1 skipped (F9.1 vision)

| Turn | Grade | Notes |
|------|-------|-------|
| F1.1 | 90 | Simple path OK after MiniCPM floor fix |
| F2.1 | 90 | OK |
| F3.1 | 100 | web_search → fetch → write |
| F4.1 | 100 | read_workspace_file |
| F5.1 | **49** | `large-cloud-failed` / `fallback_generic_cloud_error` (strict blocked Qwen) |
| F6.1–F8.1, M*, W*, FF* | 85–100 | OK |
| F9.1 | skipped | `vision_vlm_ok: false` |

`qwen_fallback_turns`: **F5.1 only**

Artifact: `data/frontier_eval_run_data.json`

## Tier B — Educator (8 turns)

```bash
python scripts/run_educator_eval.py --profile cloud --strict-cloud
```

**Run 2 (after BUG-25 fix):** 4/8 pass, **no hangs**, `qwen_fallback_turns: []`

| Turn | Grade | Pass | Notes |
|------|-------|------|-------|
| EDU1 | 100 | ✓ | PDF study guide |
| EDU2 | 100 | ✓ | Quiz (run 2: no `quiz_session_start` — duplicate EDU1 text scraped) |
| EDU3 | 100 | ✓ | Criticism adaptation |
| EDU4 | 90 | ✓ | `mastery_record` |
| EDU5 | 70 | ✗ | Memory recall too short / missing struggle keywords |
| EDU6 | 80 | ✗ | No `flashcard_deck_create` tool — prose only |
| EDU7 | 80 | ✗ | Security HITL + no `quiz_session_start` |
| EDU8 | 55 | ✗ | No `owlynn-steps` / `owlynn-quiz` fence in reply |

Artifact: `data/educator_eval_run_data.json`, report: `docs/evaluations/educator-eval-2026-06-18.md`

## Tier B — Browser (12 turns)

```bash
python scripts/run_browser_eval.py --strict-cloud
```

**Completed.** Multi-turn conversation; several mid-session turns hit `large-cloud-failed` under strict mode (context-heavy thread). Wrap-up (T6.1) succeeded on `small-local`.

Artifact: `data/eval_run_data.json` — 7 entries in `qwen_fallback_turns` (turns 4–10).

## Bugs found & fixes

### BUG-24 — MiniCPM empty simple reply (P1) — **fixed**

Router `token_budget` (256) was below MiniCPM's practical output floor; model filled `reasoning_content` and left `content` empty.

**Fix:** `_simple_output_max_tokens()` floor (512), `_extract_llm_text()` for reasoning fallback, WS handler finalize path.

### BUG-25 — Eval harness `composer-stop` stuck (P1) — **fixed**

`pendingCorrelationId` only cleared when `status: idle` correlation_id matched exactly; graph finished but UI stayed "generating" for 900s.

**Fix:** `App.tsx` — clear pending on any idle + on `assistant.message`; eval `clearPendingCorrelation` hook + WS-idle detection.

### BUG-26 — Scope/plan HITL stalls eval (P1) — **fixed (harness)**

**Fix:** Disable `scope_clarification_enabled` / `plan_review_enabled` during automated eval runs.

### BUG-27 — F5.1 cloud failure under strict (P2) — **fixed**

Round-2 cloud invoke replayed full `write_workspace_file` `content` in `AIMessage.tool_calls`, bloating the API payload and failing with empty exception text.

**Fix:** `compact_tool_call_args_for_api()` in `cloud_payload.py`; `_format_cloud_error_reason()` in `complex.py`.

### BUG-28 — Browser mid-thread cloud failures (P2) — **fixed (harness)**

Circuit breaker opened after consecutive failures in a single browser-eval thread (no per-turn reset).

**Fix:** `reset_circuit_breaker()` per turn in `run_browser_eval.py`; `execution_policy=auto_approve` during eval runs.

### BUG-29 — Stale assistant scrape in educator eval (P2) — **fixed (harness)**

`scrape_final_response` used the last assistant bubble globally; EDU6–8 inherited EDU5 text.

**Fix:** Turn-scoped DOM scrape; `WsEventLog.assistant_text_since()` preferred over DOM; require `assistant.message` after turn start before accepting WS idle.

### Educator EDU5–EDU8 — **product fixes (2026-06-18)**

| Turn | Fix |
|------|-----|
| EDU5 | `format_struggle_recall_block()` prepended to memory context; study-recall volatile nudge |
| EDU6 | Learning-mode nudge to call `flashcard_deck_create` |
| EDU7 | Eval `auto_approve` + `quiz_session_start` nudge |
| EDU8 | Learning style + nudge for `render_interactive_block` (`owlynn-steps` / `owlynn-quiz`) |

Re-run educator eval after harness fixes to confirm pass rate.

## Fix round 2 (2026-06-18) — committed

Code and docs updated for BUG-27..29 and educator EDU5–8 product nudges. **Scores below are from the 2026-06-17 run (pre round-2);** re-run strict-cloud evals to refresh artifacts:

```bash
export PYTHONPATH=.
curl -s http://127.0.0.1:8000/api/cloud-status | jq '.key_valid'
python scripts/run_local_frontier_eval.py --profile cloud --strict-cloud --ids F5.1
python scripts/run_educator_eval.py --profile cloud --strict-cloud
python scripts/run_browser_eval.py --strict-cloud
```

Expected improvements: F5.1 passes cloud round-2 after write; browser turns 4–10 no longer cascade on circuit breaker; EDU6–8 capture distinct assistant text.

## Re-run after fixes

```bash
curl -s http://127.0.0.1:8000/api/cloud-status | jq '.key_valid'
# Restart Vite if App.tsx changed
python scripts/run_educator_eval.py --profile cloud --strict-cloud
python scripts/run_local_frontier_eval.py --profile cloud --strict-cloud --ids F5.1
```

## Unit tests

```bash
pytest tests/test_cloud_strict_mode.py tests/test_cloud_payload_integration.py tests/test_frontier_eval_scoring.py tests/test_educator_memory.py tests/test_env_files.py tests/test_simple_node_streaming.py -q
./scripts/ci.sh --quick
```
