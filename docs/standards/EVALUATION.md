---
status: active
category: standards
last_updated: 2026-06-18
owner: ai-agent
audience: agent
---

# Evaluation Standard

> **Purpose:** How to run automated browser evaluations against the **current** Owlynn stack (cloud-primary routing, ToolActivityCard UI, memory, vision proxy, file watcher).

## CI vs evaluation

| Layer | Command | Purpose |
|-------|---------|---------|
| Pre-push | `./scripts/ci.sh --quick` | pytest + vitest + ruff/mypy |
| Live cloud | `./scripts/ci.sh --network` | DeepSeek E2E, KV cache, chat matrix (`DEEPSEEK_API_KEY`) |
| Benchmarks | `./scripts/ci.sh --benchmarks` | Router/complex/memory latency → `tests/benchmarks/benchmark_report.json` |
| **Frontier eval** | `python scripts/run_local_frontier_eval.py` | ~19-turn scored routing + tools + memory + vision + formats |
| **Educator eval** | `python scripts/run_educator_eval.py` | 8-turn UID10667 study session (EDU1–EDU8); optional, needs fixtures |
| **Frontier comparison** | `python scripts/run_frontier_comparison_eval.py` | Quality A/B: Owlynn vs raw DeepSeek V4 + blind pro judge |
| **Conversation eval** | `python scripts/run_browser_eval.py` | 12-prompt multi-topic run (qualitative) |

Eval scripts are **not** in the CI gate — they need LM Studio + running stack (+ optional DeepSeek key).

**Checklist before eval:** `./scripts/ci.sh --quick` → `./start.sh` → confirm `:8000` + `:5173` connected.

## Architecture assumptions (2026-06-11)

```text
memory_inject_lite → router → memory_retrieve → auto_summarize?
  → simple | scope_clarify → complex_llm → tool_action (loops) → memory_write
Routes: simple | complex-default (local Qwen) | complex-cloud (DeepSeek) | vision | vision_cloud
UI: ToolActivityCard + HitlPromptCard interleaved in `.messages` timeline
```

### Pipeline diagram

```mermaid
flowchart TD
  subgraph graph [LangGraph backend]
    inject[memory_inject_lite]
    router[router]
    retrieve[memory_retrieve]
    summarize[auto_summarize]
    simple[simple_node]
    scope[scope_clarify]
    complex[complex_llm]
    plan[plan_review]
    sec[security_proxy]
    tools[tool_action]
    memwrite[memory_write]
    inject --> router --> retrieve --> summarize
    summarize --> simple --> memwrite
    summarize --> scope --> complex
    complex --> plan --> sec --> tools
    tools --> complex
    complex --> memwrite
  end
  subgraph ui [Browser eval observes]
    orch[OrchestrationPanel route/model badges]
    toolcard[ToolActivityCard in chat]
    hitl[HitlPromptCard pending]
    composer[Composer stop vs send]
  end
  router --> orch
  tools --> toolcard
  plan --> hitl
  sec --> hitl
  graph --> composer
```

### Observation map

| Graph stage | WS event | UI element |
|-------------|----------|------------|
| Router decision | `router_info` | `.route-badge`, `.orchestration-gauge-value`, Source row |
| Model selection | `model_info` | `.model-badge` |
| Tool execution | `tool_execution` | `.tool-activity-card`, `.tool-activity-name code` |
| HITL | `interrupt` | `.hitl-prompt-card.hitl-pending`, `.hitl-btn-approve` |
| Graph running | `status: reasoning` | `.composer-stop`, `.tool-activity-running`, `.streaming-cursor` |
| Memory write | `memory_updated` | `.orchestration-memory-ok` ("Saved") |
| Context compress | `context_summarized` | `.orchestration-compression` |
| File watcher | `file_status` | (backend only; assert via `/api/files` + `.processed/`) |

### Profiles

| Profile | When | Complex route expected |
|---------|------|----------------------|
| `cloud` | Escalation ON + valid key | `complex-cloud`, `vision_cloud` |
| `local` | Escalation off or no key | `complex-default`, `vision` |
| `auto` | Read from `/api/unified-settings` + `/api/cloud-status` | Resolved at run start |

**Primary baseline:** `cloud-auto` (production-like).

## Turn complete criteria

A turn is **complete** when all of:

1. No `.composer-stop` (graph not running)
2. No `.hitl-prompt-card.hitl-pending`
3. No `.tool-activity-running`
4. No `.streaming-cursor`
5. Final assistant bubble passes quality gate (min chars, no DSML when tools required)

HITL is resolved in-loop: scope → first `.hitl-choice-btn` + approve; plan/security → `.hitl-btn-approve`.

## Frontier evaluation (`run_local_frontier_eval.py`)

### Turn matrix (cloud-auto)

| ID | Topic | Expected route | Key asserts |
|----|-------|----------------|-------------|
| F1.1 | Simple greeting | `simple` | no tools |
| F2.1 | Code review | `complex-cloud` | response quality |
| F3.1 | Web + file write | `complex-cloud` | `web_search`, `write_workspace_file`, HITL |
| F4.1 | Read file | `complex-cloud` | `read_workspace_file` |
| F5.1 | React codegen | `complex-cloud` | long response |
| F6.1 | Conversation recall | `complex-cloud` | Tokyo/tokyo_weather.txt in answer |
| F7.1 | Frontier quality | `complex-cloud` | `model_tier == flash` (frontier hints do **not** auto-escalate tier) |
| F7.2 | Pro tier path | `complex-cloud` | `model_tier == pro` after profile bump |
| F8.1 | Router LLM | `complex-cloud` | `classification_source == llm_classifier` |
| F9.1 | Vision OCR | `vision_cloud` | OCR marker in answer |
| M1.1 | Memory seed | `complex-cloud` | WS `memory_updated` |
| M1.2 | Session recall | `complex-cloud` | codeword ZEBRA-42 |
| M2.1 | LTM cross-thread | `complex-cloud` | codeword in new chat (skipped if Mem0 down) |
| M4.1 | Retrieval gate | `simple` | no `memory_updated` |
| W1.1 | File watcher | `complex-cloud` | `read_workspace_file`, `.processed/` |
| FF1–FF4 | Formats pdf/docx/xlsx/csv | `complex-cloud` | marker string in answer |

Fixtures: `assets/eval_fixtures/` (generate via `python scripts/generate_eval_fixtures.py`).

### Source of truth: WebSocket stream

Routing, tools, and task category are scored from **captured WS events**, not DOM scrapes
(ToolActivityCards are unreliable in headless Chromium):

- `tool_execution` (status != error) → `executed_tools`
- `router_info` `metadata.route` / `classification_source` → route + source
- `router_info` `metadata.features.task_category` → vision detection (`vision`/`vision_cloud`)

DOM scrape is kept only as a fallback. Both are stored (`executed_tools_ws`, `executed_tools_dom`).

### Scoring (`eval_version: 2026-06-11`, per turn /100)

| Criterion | Points |
|-----------|--------|
| Route match (tier-aware) | 35–40 |
| Non-empty response (min chars) | 15–20 |
| Expected tools (timeline scrape) | 25–40 |
| Recall / marker match | +20 (when declared) |
| Tier match (`flash` / `pro`) | +15 |
| Source match (`llm_classifier`) | +15 |
| WS events (`memory_updated`, `file_status`) | +5 each |
| File processed | +10 |
| DSML leak | −15 |
| Premature complete (DSML or missing tools at idle) | −10 |
| Cloud Qwen fallback on cloud-intended turn | cap **49** (`cloud_scoring: qwen_fallback_fail`) |

**Cloud scoring strictness:** When `runtime_profile` is `cloud`/`auto` and the turn expects `complex-cloud` or `vision_cloud`, finishing on `medium-default-fallback` or `medium-default-synthesis` caps the grade at 49. Runtime fallback is **not** blocked — this is eval-only. Exempt: `small-local`, vision profile, `simple` route, `--profile local`.

Skipped turns (Mem0 offline, vision unavailable) are excluded from `max_score`.

### Prerequisites

- `./start.sh` (backend `:8000`, frontend `:5173`)
- LM Studio with models from `defaults.yaml`
- Playwright: `pip install playwright && playwright install chromium`
- Optional: `DEEPSEEK_API_KEY`, Redis/Qdrant for M2 LTM turn

### Commands

```bash
# Production-like (cloud-first):
PYTHONPATH=. python scripts/run_local_frontier_eval.py --profile auto

# Local-only regression:
PYTHONPATH=. python scripts/run_local_frontier_eval.py --cloud-off --profile local

# Strict cloud debug (no Qwen fallback on compute paths — fail with large-cloud-failed):
PYTHONPATH=. python scripts/run_local_frontier_eval.py --profile cloud --strict-cloud
PYTHONPATH=. python scripts/run_educator_eval.py --profile cloud --strict-cloud
PYTHONPATH=. python scripts/run_browser_eval.py --strict-cloud

# Re-run failed turns only:
PYTHONPATH=. python scripts/run_local_frontier_eval.py --profile cloud --strict-cloud --ids F5.1

# Opt out of strict mode (allow silent Qwen fallback again):
PYTHONPATH=. python scripts/run_local_frontier_eval.py --profile cloud --allow-local-fallback
```

Set `PYTHONPATH=.` (repo root) when running eval scripts so `src` imports resolve.

### Strict cloud mode

When `cloud_no_local_fallback` is enabled (via `--strict-cloud` on cloud profile runs):

- **Blocked:** `medium-default-fallback`, `medium-default-synthesis`, `vision_proxy_failed` → Qwen, `simple` → Qwen
- **Allowed:** router MiniCPM, Florence vision proxy, background memory extraction Qwen
- **Failure badge:** `large-cloud-failed` or `small-local-failed` with explicit error text
- **Scoring:** cloud-intended turns ending on fallback badges cap at grade 49 (`cloud_fallback_fail`)
- **Preflight:** `--profile cloud` exits if `/api/cloud-status` reports `key_valid: false`

Config: `cloud.no_local_fallback` in `defaults.yaml`, profile field `cloud_no_local_fallback`, env `OWLYNN_CLOUD_NO_FALLBACK`.

Run JSON includes `strict_cloud: true` and `qwen_fallback_turns[]` with `fallback_chain` reasons for triage.

**Automated eval harness (2026-06-18):** During runs, scripts temporarily set `scope_clarification_enabled=false`, `plan_review_enabled=false`, and `execution_policy=auto_approve` (restored on exit). Educator and browser eval call `reset_circuit_breaker()` per turn. Frontier waiter prefers `assistant.message` WS text and turn-scoped DOM scrape (`BUG-29`).

**Cloud tool-loop (BUG-27):** Completed `write_workspace_file` tool-call args are compacted in `cloud_payload.py` before DeepSeek replay so round-2 invokes do not resend multi-KB `content` blobs. Config: `tool_output.max_api_tool_arg_chars` (default 2048).

Canonical strict-cloud report: [`docs/evaluations/strict-cloud-debug-2026-06-16.md`](../evaluations/strict-cloud-debug-2026-06-16.md).

```bash
# Educator / UID10667 PDF study (5 turns, learning mode):
python scripts/prepare_uid10667_fixtures.py
python scripts/run_educator_eval.py --profile auto
```

### Educator eval (EDU1–EDU8)

| Turn | Focus | Pass (≥70) |
|------|-------|------------|
| EDU1 | Attach chapter 1 PDF, study guide | `read_workspace_file`, no `web_search`, ≥2 course keywords |
| EDU2 | Quiz same thread | ≥2 keywords in quiz |
| EDU3 | User criticism | Acknowledgment + revision language |
| EDU4 | Self-reinforcement | Acknowledgment (informational) |
| EDU5 | New chat struggle recall | Topic + substantive recall (misconception/correction); denial phrases fail |
| EDU6 | Flashcard deck from chapter | `flashcard_deck_create` or PDF read; flashcard keywords |
| EDU7 | Mock exam weak areas | Questions + weak-area language; `quiz_session_start` preferred |
| EDU8 | Step-by-step + MCQ widget | `owlynn-steps` or `owlynn-quiz` fence via `render_interactive_block` |

Fixtures: `assets/eval_fixtures/uid10667/` via `python scripts/prepare_uid10667_fixtures.py --source <UID10667 folder>`.

Artifacts: `data/educator_eval_run_data.json`, `assets/educator_eval_screenshots/`, `docs/evaluations/educator-eval-YYYY-MM-DD.md`.

### Artifacts

| Path | Content |
|------|---------|
| `data/frontier_eval_run_data.json` | Telemetry, grades, `eval_version`, profile |
| `assets/frontier_eval_screenshots/` | Per-turn PNGs |
| `assets/eval_fixtures/` | pdf/docx/xlsx/csv/png test files |
| `docs/evaluations/local-frontier-eval-YYYY-MM-DD.md` | Human summary |

## Comparative quality evaluation (`run_frontier_comparison_eval.py`)

**Purpose:** Answer whether Owlynn's full system (router, memory, tools, RAG, local models) adds value over **raw DeepSeek V4 frontier chat** on the same prompts — with an unbiased quality score and an improvement-focused report.

### Two-arm design

| Arm | What runs | Model tier |
|-----|-----------|------------|
| **Owlynn** | Browser → WebSocket → full LangGraph pipeline | `flash` (cloud path) |
| **Baseline** | Direct `AsyncOpenAI` chat completion | `flash` (same tier) |
| **Judge** | Blind A/B rubric scorer | `pro` |

Baseline system prompt: `"You are a helpful assistant."` (minimal, like a chat UI). Owlynn uses its full stable system prompt — we compare **products**, not prompts.

### Fairness controls

- **Blind labels:** judge sees Response A / B only
- **Dual-order:** each pair judged twice with A/B swapped; inconsistent orders → `tie`
- **Symmetric vendor:** both arms use DeepSeek — judge does not favor either vendor
- **Category split:**
  - `chat` (8 prompts): self-contained reasoning/code/creative — **headline quality** win/tie/loss
  - `capability` (6 prompts): web/files/memory/vision — **task_success** + differentiation metric

### Rubric (judge JSON, 1–5 per dimension)

`correctness`, `completeness`, `instruction_following`, `reasoning_depth`, `clarity_formatting` (penalize DSML / `<tool_call>` leaks), `usefulness`, plus `task_success` for capability prompts.

### Commands

```bash
# Full run (~14 prompts, Owlynn arm dominates runtime):
python scripts/run_frontier_comparison_eval.py --profile auto

# Dry-run (1 chat + 1 capability):
python scripts/run_frontier_comparison_eval.py --dry-run

# Collect arms only (no judge API calls):
python scripts/run_frontier_comparison_eval.py --skip-judge
```

Requires `.env` with `DEEPSEEK_API_KEY` (or Keychain) for baseline + judge arms.

### Artifacts

| Path | Content |
|------|---------|
| `data/frontier_comparison_run_data.json` | Both arms, dual-order judge, per-dimension scores |
| `assets/frontier_comparison_screenshots/` | Per-turn PNGs |
| `docs/evaluations/frontier-comparison-YYYY-MM-DD.md` | Summary, losses, wins, improvements |

Mechanical regression remains [`run_local_frontier_eval.py`](../../scripts/run_local_frontier_eval.py) — run both after significant pipeline changes.

## Conversation evaluation (`run_browser_eval.py`)

12 curated prompts (technical, code review, creative, continuity, web search). Qualitative — no strict route grades.

## Reporting

After each significant frontier run:

1. Write `docs/evaluations/local-frontier-eval-YYYY-MM-DD.md`
2. Add entry to `docs/INDEX.md`
3. Update `docs/STATUS.md` trajectory row
4. Note `runtime_profile`, score, skipped turns, and regressions vs prior baseline

## Related

- [`docs/AGENT_FLOW.md`](../AGENT_FLOW.md) — graph topology
- [`docs/CLOUD-LLM-ARCHITECTURE.md`](../CLOUD-LLM-ARCHITECTURE.md) — cloud + vision proxy
- [`docs/guides/cloud-multi-turn-context.md`](../guides/cloud-multi-turn-context.md) — KV cache
- [`docs/MEMORY.md`](../MEMORY.md) — STM/LTM/personal memory
- [`docs/PROJECT_GUIDE.md`](../PROJECT_GUIDE.md) — CI table + root layout
- [`docs/BUG-TRACKER.md`](../BUG-TRACKER.md) — BUG-13..16
