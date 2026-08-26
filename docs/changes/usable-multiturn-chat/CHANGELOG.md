---
status: active
category: changes
last_updated: 2026-08-26
owner: ai-agent
audience: agent
---

# Usable multi-turn chat (local-first) — 2026-08-25/26

## Goal

Make Owlynn usable for personal Normal-mode multi-turn chat on Mac M4 Air 24GB:
simple answers → web follow-ups → workspace notes, without HITL thrash or broken file writes.

## How to re-run

Backend + LM Studio must be up (`./start.sh` or uvicorn on `:8000`, LM Studio on `:1234`).

```bash
# Critical path (3 turns): capital → GDP web → write_workspace_file
PYTHONUNBUFFERED=1 uv run python scripts/manual/e2e_topic_drift_ws.py \
  --profile usable --out /tmp/e2e_usable.json

# Full topic drift (6 turns)
PYTHONUNBUFFERED=1 uv run python scripts/manual/e2e_topic_drift_ws.py \
  --profile full --out /tmp/e2e_topic_drift_result.json
```

Success criteria for **usable** profile: all turns `passed` (correct tools + idle).
SLO bands may still be `unacceptable` until warm TTFT improves — functional correctness first.
UI `usable_gate` stays `False` while any turn is SLO `unacceptable` (typically T1 simple &gt;8s).

## Fixes in this pass

| Issue | Fix |
|-------|-----|
| `ask_user` → fake `system_error` loop | Re-raise `GraphInterrupt` in `complex_tool_action` |
| Mid-thread fat `web_search` prefills | `_trim_tool_history` caps prior-turn tool blobs (`tool_output.prior_turn_max_chars`) |
| `file_ops` only had ingest connectors | Restore workspace CRUD; move ingest → `data_connectors` |
| Web digression used toolbox `all` | `tool_history_bypass` prefers `web_search` / `file_ops` |
| Scratch writes always denied | `get_safe_workspace_path` checks active root only (not also `BASE_WORKSPACE_DIR`) |
| Write/read thrash after success | Unbind tools after successful write; ToolMessage stop nudge |
| Models emit `path=` instead of `filename=` | `write_workspace_file` accepts `path` alias |
| Sticky `_tool_first_web_phase=done` blocked T3/T6 | `maybe_clear_stale_tool_first_web_phase` clears `done` on new turns without search |
| T5 list/read bind_tools thrash | `tool_first_list_read` inject + post-read short-circuit |
| Verbose trivia / slow simple decode | `simple.max_tokens` **128**; streaming honors cap |
| Tool-first synth prefill ~50s | Prefer extractive synth (`complex.tool_first_extractive_synth`) |
| Postgres OOM / health flap on 2 GB Podman | Recommend Podman machine **4 GB**; postgres `mem_limit: 768m` |

## Measured E2E (usable profile)

| Round | T1 simple | T2 web | T4 write | Notes |
|-------|-----------|--------|----------|-------|
| R1 (pre scratch-fix) | PASS ~15s | PASS ~49s | FAIL timeout (access denied) | Correct tool selected |
| R2 (scratch fixed) | FAIL short_answer | PASS ~49s | FAIL timeout (write looped) | Write **succeeded** repeatedly |
| R3 (unbind after write) | PASS ~15s | PASS ~41s | FAIL timeout (force-write re-injected) | Empty prose after write re-triggered force write |
| R4 (post-write hard stop) | PASS 16.3s | PASS 43.3s | PASS 79.3s (**1 write**) | **3/3 functional pass** — `/tmp/e2e_usable_r4.json` |
| R5 (post-write no-LLM confirm) | PASS 12.7s | PASS 49.3s | PASS 47.0s (**degraded**) | **3/3** wall 109s — `/tmp/e2e_usable_r5.json` |
| R6 (2026-08-26 WS, post sticky/extractive/4GB) | PASS 14.95s (`unacceptable`) | PASS 23.0s (`degraded`) | PASS 10.86s (`ok`) | **3/3 functional**; `/tmp/e2e_ws_usable.json` |

## Measured E2E (full profile, 2026-08-26)

Functional **6/6 pass** after sticky-phase clear + list/read tool-first + Podman 4 GB (`/tmp/e2e_ws_full.json`, wall ~104s). Postgres health `ok` post-run.

| Turn | Result | elapsed | SLO band | Tools |
|------|--------|---------|----------|-------|
| T1 capital (simple) | PASS | 18.24s | **unacceptable** | — |
| T2 GDP (web) | PASS | 22.16s | degraded | `web_search` |
| T3 weather digression (web) | PASS | 12.66s | degraded | `web_search` |
| T4 write note | PASS | 19.48s | ok | `write_workspace_file` |
| T5 list/read note | PASS | 15.46s | ok | `list_workspace_files`, `read_workspace_file` |
| T6 back to GDP (web) | PASS | 15.95s | degraded | `web_search` |

**Gate status:** Full T3/T5/T6 cleared functionally. UI `usable_gate` still **False** because T1 simple remains SLO `unacceptable` (&gt;8s). Next lever: warm simple TTFT (prompt trim / cache), not tool routing.

## Related code

- `src/tools/core_tools.py` — scratch path allow
- `src/agent/tool_sets.py` — `file_ops` / `data_connectors`
- `src/agent/routing/deterministic.py` — narrow toolboxes mid-thread
- `src/agent/core/complex_tool_action.py` — GraphInterrupt + write stop nudge
- `src/agent/core/complex_prompt.py` — prior-turn tool trim
- `src/agent/core/tool_first_web.py` — sticky phase clear + extractive answer
- `src/agent/core/tool_first_list_read.py` — list+read inject
- `src/agent/core/simple.py` / `defaults.yaml` — `simple.max_tokens` 128
- `docker-compose.mvp.yml` — postgres `mem_limit: 768m`
- `scripts/manual/e2e_topic_drift_ws.py` — `--profile usable|full`
