# Changelog: frontier-eval-memory-session

Session work (2026-06-10 → 2026-06-11): frontier eval investigation, harness fixes, Florence vision hardening, scoring-only cloud strictness, background memory extraction scheduler.

---

## 1. Problem statement

### Frontier eval — cloud turns hitting Qwen fallback

**Symptom:** Cloud-intended complex turns ended with model badges `medium-default-fallback` or `medium-default-synthesis` instead of DeepSeek, dragging eval scores down.

**Initial hypothesis:** Block local fallback at runtime during eval.

**Decision (user-approved):** Do **not** block runtime fallback. Use **scoring-only strict cloud**: cloud-intended turns that finish on Qwen fallback badges are graded as failed (cap 49). Exempt by design: `small-local` router, vision turns, `simple` route, `--profile local`.

### Eval harness — mechanical failures

| Turn | Problem | Root cause |
|------|---------|------------|
| F3.1 | 900s DOM stall | Waiter did not merge WS `tool_execution` events |
| F4.1 | Missing `read_workspace_file` | Workspace seed path wrong; `docs/STATUS.md` not present in eval project |
| F9.1 | Vision OCR fail / wrong route | Florence not loaded; weak preflight |
| M4.1 | `memory_updated` on greeting | Greeting gate regex missed `"Hi there!"` |
| F8.1 | `deterministic` not `llm_classifier` | Prompt hit explain/compare bypass; prior turn tool history |

### Vision proxy confusion

**Symptom:** F9 appeared to use Qwen for OCR.

**Actual path:** Florence-2 OCR → DeepSeek synthesis. Qwen only on `vision_proxy_failed` → `complex-default` fallback.

### Memory extraction — GPU contention

**Symptom:** Background Qwen extraction (LTM atom worker) could run during active chat or local fallback, hogging unified memory/GPU on M4 Air.

**Constraint:** LM Studio OpenAI API has no per-request GPU throttle.

---

## 2. Changes implemented

### 2.1 Scoring-only cloud strictness (eval harness)

**File:** `scripts/run_local_frontier_eval.py`

- `CLOUD_QWEN_FALLBACK_BADGES`, `eval_cloud_qwen_fallback()` — caps grade at 49 when cloud-intended turn ends on Qwen fallback
- `cloud_scoring: qwen_fallback_fail` recorded in run JSON
- **Rolled back:** runtime `eval_cloud_no_fallback` blocking in `complex.py` (user rejected blocking local LLM during eval)

**Tests:** `tests/test_frontier_eval_scoring.py`

### 2.2 WS waiter + idle stall exit

**File:** `scripts/run_local_frontier_eval.py`

- `merge_executed_tools()` — WS `tool_execution` is source of truth for tool list
- `should_exit_idle_tool_stall()` — ~16s early exit when graph idle + response ready but expected tools missing (fixes F3 900s stall)

### 2.3 F4 workspace fixture

**Files:** `scripts/run_local_frontier_eval.py`, `scripts/generate_eval_fixtures.py`, `assets/eval_fixtures/status_eval.md`

- F4.1 `workspace_seed: docs/STATUS.md` + `workspace_seed_from_fixture: status_eval.md`
- `seed_workspace_file()` creates parent dirs (`mkdir` parents)

### 2.4 M4 greeting gate

**File:** `src/agent/nodes/memory.py`

- `_should_save_memory()` greeting regex aligned with router keyword bypass (`"Hi there!"`)

**Tests:** `tests/test_memory_greeting_gate.py`

### 2.5 F8 prompt + new chat

**File:** `scripts/run_local_frontier_eval.py`

- Reworded F8.1 prompt (removed `trade-off` — triggers explain/compare deterministic bypass)
- `new_chat_before: True` on F8.1

### 2.6 F9 Florence preflight + OCR scoring

**Files:** `scripts/run_local_frontier_eval.py`, `src/agent/nodes/complex_utils/vision_model_manager.py`, `src/agent/nodes/complex_utils/lm_studio_florence.py`, `src/config/defaults.yaml`

- Strict `check_vision_vlm_available()` — Florence loaded check, not just LM Studio up
- `ensure_florence_loaded()` via LM Studio native `/api/v1/models/load`
- Vision proxy rejects non-Florence model names; no medium/Qwen OCR fallback
- OCR fail caps vision grade at 60
- Telemetry: `vision_intake_mode`, `vision_proxy_model` on node output + WS `model_info`

**Tests:** `tests/test_lm_studio_florence.py`

### 2.7 Background memory extraction scheduler

**Files:** `src/agent/local_llm_scheduler.py` (new), `src/agent/llm.py`, `src/memory/extraction/worker.py`, `src/api/ws/handler.py`, `src/config/defaults.yaml`

- Extraction still uses Qwen (`get_medium_llm(foreground=False)` + `invoke_medium_background()`)
- Defers until: no active graph run + no foreground medium LLM call + cooldown
- Agent paths wrap medium LLM with foreground slot tracker
- `process_nice: 10` lowers CPU priority during extraction (Unix)
- Config under `memory.extraction.*`

**Tests:** `tests/test_local_llm_scheduler.py`

### 2.8 Documentation updates (this session)

- `docs/standards/EVALUATION.md` — WS source of truth, turn matrix, comparison eval
- `docs/guides/lm_studio.md` — Florence vision proxy section
- `docs/technical/model-quirks-and-routing.md` — §5 Florence OCR
- `docs/evaluations/local-frontier-eval-2026-06-11.md` — post-fix run appended
- `docs/MEMORY.md` — background extraction deferral
- `docs/STATUS.md` — trajectory + recent changes

---

## 3. Eval results

| Run | Score | Notes |
|-----|-------|-------|
| Pre-fix (v9 baseline) | **1565/1900 (82.37%)** | DOM under-scoring; many Qwen fallback badges |
| Post-fix run 1 (`FrontierEval_b1e097`) | **1790/1900 (94.21%)** | F4=100, F9=100, F3=33s |
| Post-fix run 2 (`FrontierEval_ba6eb0`) | **1785/1900 (93.95%)** | M4=90, F8=95 (hitl), F9=60 (Florence flaky) |
| Target | ≥97% (1860/1900) | Not reached — variance on F1/F6/F9 |

**Artifact:** `data/frontier_eval_run_data.json` (latest: 93.95%)

---

## 4. Known remaining issues

| ID | Issue | Impact | Suggested fix |
|----|-------|--------|---------------|
| F1 | Simple route empty DOM bubble / timeout | 70/100 | DOM waiter for simple streaming |
| F6 | Agent uses tools when STM recall expected | 75/100 | Prompt tightening or route gate |
| F9 | Florence load/OCR flaky between runs | 60–100 variance | Ensure Florence loaded before eval; stack restart |
| F8 | May hit HITL (`source=hitl`) not pure `llm_classifier` | 90–95 | Narrow prompt or eval HITL auto-approve |
| GPU | Extraction cannot detect external GPU apps | Other programs still compete | Manual: increase `idle_cooldown_seconds` |
| Docs | Pre-fix eval report showed 82.37% only | Stale until this update | ✅ Updated in eval report |

---

## 5. Files touched (summary)

| Area | Key paths |
|------|-----------|
| Eval harness | `scripts/run_local_frontier_eval.py`, `scripts/generate_eval_fixtures.py`, `scripts/run_frontier_comparison_eval.py` |
| Vision | `src/agent/nodes/complex_utils/lm_studio_florence.py`, `vision_model_manager.py`, `vision_proxy.py`, `complex.py` |
| Memory | `src/agent/nodes/memory.py`, `src/memory/extraction/worker.py`, `src/agent/local_llm_scheduler.py` |
| API | `src/api/ws/handler.py` |
| Config | `src/config/defaults.yaml` |
| Tests | `tests/test_frontier_eval_scoring.py`, `tests/test_memory_greeting_gate.py`, `tests/test_lm_studio_florence.py`, `tests/test_local_llm_scheduler.py` |

---

## 6. Operational notes

- **Restart required** after code changes (`./start.sh`). A scheduled restart was aborted — backend may still be on old code until manually restarted.
- **Before frontier eval:** `./scripts/ci.sh --quick` → `./start.sh` → load Florence in LM Studio → confirm `vision_vlm_ok` in preflight.
- **Tune background extraction:** `memory.extraction.idle_cooldown_seconds`, `defer_while_graph_active`, `process_nice` in `defaults.yaml`.

---

## Related

- [`docs/evaluations/local-frontier-eval-2026-06-11.md`](../../evaluations/local-frontier-eval-2026-06-11.md)
- [`docs/standards/EVALUATION.md`](../../standards/EVALUATION.md)
- [`docs/MEMORY.md`](../../MEMORY.md)
- [`docs/guides/lm_studio.md`](../../guides/lm_studio.md)
