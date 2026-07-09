---
status: active
category: reference
audience: agent
last_updated: 2026-07-10
owner: ai-agent
---

# Owlynn Project Guide

> **Purpose:** Canonical file map for AI agents. Use this to locate source files, contracts, and tests before making changes.

Related: [`architecture/overview.md`](architecture/overview.md) (system shape), [`STATUS.md`](STATUS.md) (bugs/risks), [`ADR.md`](ADR.md) (decisions).

## Root directory (what belongs here)

| Keep at root | Move elsewhere |
|--------------|----------------|
| `AGENTS.md`, `README.md`, `LICENSE`, `CONTRIBUTING.md` | — |
| `start.sh`, `setup.sh`, `docker-compose.yml` | — |
| `pyproject.toml`, `pytest.ini`, `mypy.ini`, `.ruff.toml`, `requirements-dev.txt`, `uv.lock` | — |
| `mcp_config.json` (+ `.example`) | — |
| `src/`, `tests/`, `frontend-v2/`, `docs/`, `scripts/`, `skills/`, `browser-extension/` | — |
| — | One-off patches → `scripts/archive/` |
| — | Manual live smokes → `scripts/manual/` |
| — | Audit exports → `docs/archive/audits/` |
| — | Eval JSON → `data/` (gitignored) |

Do **not** add new `.py` test or patch scripts at repo root.

---

## Routing and model behavior

| File | Role |
|------|------|
| `src/agent/nodes/router.py` | `router_node()` — classification, keyword bypass, HITL clarification |
| `src/agent/router/classifier.py` | LLM JSON routing classifier |
| `src/agent/router/budget.py` | Token budget tiers and input reserves |
| `src/agent/router/selector.py` | Model/toolbox selection |
| `src/agent/llm.py` | `LLMPool` singleton — router + extraction + cloud slots |
| `src/agent/nodes/simple.py` | Fast simple-path answers (no tools) |
| `src/agent/nodes/complex.py` | Tool-calling cycle, local + cloud paths |
| `src/agent/nodes/complex_utils/cloud_payload.py` | Cloud prompt layers, anonymization, tool-arg compaction on replay (BUG-27) |
| `src/agent/nodes/complex_utils/vision_qwen3vl.py` | Qwen3-VL output parser |
| `src/agent/nodes/complex_utils/vision_*.py` | Vision proxy for cloud image path (Qwen3-VL default) |
| `src/agent/nodes/complex_utils/lm_studio_vision.py` | LM Studio auto-load for vision VLM |
| `src/tools/mcp_client.py` | MCP stdio client; tools merged via `merge_mcp_tools()` |
| `mcp_config.json` | MCP server manifests (see `mcp_config.json.example`) |
| `src/config/defaults.yaml` | Model names, routing, `mcp.*`, `startup.preload` (source of truth) |
| `tests/test_router_properties.py` | Router property tests |
| `tests/test_router_web_intent.py` | Web-intent forcing tests |
| `tests/test_llm_pool.py` | LLM pool tests |

**Current models** (`defaults.yaml`): Unified local model `gemma-4-e2b-heretic-uncensored-mlx` (router, vision proxy, and memory extraction), complex cloud `deepseek-v4-flash`. Startup preloads local unified model + embedding.

## Complex / cloud path

| File | Role |
|------|------|
| `src/agent/nodes/complex.py` | `complex_llm_node()`, `complex_tool_action_node()`, `_resolve_complex_tools()` |
| `src/agent/nodes/complex_utils/cloud_payload.py` | Brief gate, PII scrub, cache metrics, completed write arg compaction |
| `src/agent/nodes/complex_utils/cloud_invoke.py` | Raw API invoke + retries |
| `src/agent/anonymization.py` | PII scrubbing for cloud escalation |
| `tests/test_complex_node_properties.py` | Complex node behavior |
| `tests/test_anonymization*.py` | Anonymization leak tests |
| `tests/test_cloud_*.py` | Cloud payload, circuit breaker, cost |
| `docs/guides/cloud-multi-turn-context.md` | Multi-turn payload + DeepSeek KV cache behavior |

## HITL (human-in-the-loop)

| File | Role |
|------|------|
| `src/agent/hitl/policy.py` | `is_sensitive_call()`, shared policy |
| `src/agent/hitl/context.py` | Interrupt context enrichment |
| `src/agent/nodes/scope_clarify.py` | Vague build/create clarification |
| `src/agent/nodes/plan_review.py` | Sensitive tool plan review |
| `src/agent/nodes/security_proxy.py` | Execution approval gate |
| `tests/test_scope_clarify.py` | Scope clarify tests |
| `tests/test_plan_review.py` | Plan review tests |
| `tests/test_security_proxy.py` | Security proxy tests |

## API / WebSocket

| File | Role |
|------|------|
| `src/api/server.py` | FastAPI app entry |
| `src/api/routes/*.py` | REST endpoints |
| `src/api/routes/config.py` | Settings/Config API |
| `src/api/routes/export.py` | Chat export API |
| `src/api/routes/scheduled_jobs.py` | APScheduler REST API |
| `src/api/scheduler_manager.py` | APScheduler background jobs |
| `src/api/ws/handler.py` | WebSocket streaming, event serialization |
| `src/api/power_monitor.py` | Power state monitor loop (pmset status checks) |
| `src/api/idle_manager.py` | Idle resource watcher (LM Studio unload + StirlingPDF shutdown) |
| `docs/development/CHAT_PROTOCOL.md` | WS event contract |
| `docs/development/API_REFERENCE.md` | REST reference |
| `tests/test_websocket_event_contract.py` | WS contract tests |
| `tests/test_frontend_backend_alignment.py` | Frontend/backend alignment |

## Frontend

| File | Role |
|------|------|
| `frontend-v2/src/App.tsx` | App shell, WebSocket lifecycle, HITL resume |
| `frontend-v2/src/lib/electronBridge.ts` | Electron IPC (Safe Mode, screen assist) |
| `frontend-v2/src/lib/wsClient.ts` | WebSocket client |
| `frontend-v2/src/lib/toolPreamble.ts` | Filter tool-only placeholder text from chat stream |
| `frontend-v2/src/state/useAppStore.ts` | Main Zustand store assembler (combines slices) |
| `frontend-v2/src/state/slices/*.ts` | Modular Zustand state slices (chat, cloud, tools, modes) |
| `frontend-v2/electron/main.ts` | Electron main process |
| `frontend-v2/src/components/AppShell.tsx` | Layout shell |
| `frontend-v2/src/components/SettingsPanel.tsx` | Settings UI |
| `frontend-v2/src/components/CitationsList.tsx` | Citations UI |
| `frontend-v2/src/components/Composer.tsx` | Chat composer (drag-and-drop context) |

## Memory

| File | Role |
|------|------|
| `src/agent/nodes/memory.py` | `memory_inject_lite`, `memory_retrieve`, `memory_write` |
| `src/models/` | PostgreSQL SQLAlchemy models (Project, Chat) |
| `src/memory/` | STM/LTM/personal managers, Mem0/Qdrant, PostgreSQL managers |
| `data/topics.json` | Personal topic decay (runtime data) |
| `docs/features/MEMORY.md` | Memory tier contract |
| `tests/test_memory_nodes.py` | Memory node tests |
| `tests/test_memory_retrieve_gate.py` | Gated retrieval tests |

## Tools

| File | Role |
|------|------|
| `src/agent/tool_sets.py` | `ToolboxRegistry`, tool list resolution |
| `src/tools/` | Tool implementations (`@tool` decorators) |
| `src/agent/tool_reranker.py` | Semantic tool reranking via Nomic embeddings |
| `src/tools/data_connectors.py` | Data connectors (GitHub, YouTube, Obsidian) |
| `docs/features/TOOLS.md` | Tool reference |
| `tests/test_toolbox_registry*.py` | Toolbox tests |
| `tests/test_mcp_tool_binding.py` | MCP merge + HITL prefix tests |
| `tests/test_web_tools.py` | Web search tools |

## Config

| File | Role |
|------|------|
| `src/config/defaults.yaml` | All defaults — edit here first |
| `src/config/config_loader.py` | YAML + env + profile merge |
| `src/config/settings.py` | Workspace roots, paths |

## File intake (PDF)

| File | Role |
|------|------|
| `src/pdf/intake.py` | Unified PDF text extraction (Stirling → OCR → PyMuPDF) |
| `src/integrations/stirling_pdf.py` | StirlingPDF HTTP client (supports on-demand lazy start/idle shutdown) |
| `src/api/file_processor.py` | Workspace watcher — writes `.processed/*.txt` (bypassed on battery) |
| `src/api/shared.py` | Chat attachment inline PDF extraction |
| `src/tools/core_tools.py` | `read_workspace_file` PDF path |
| `docker-compose.yml` | Services definition (Qdrant, Redis, Postgres, StirlingPDF) |
| `tests/test_pdf_intake.py` | Mocked intake tests (no live container in CI) |

## Graph orchestration

| File | Role |
|------|------|
| `src/agent/core/graph.py` | `build_graph()`, conditional edges, HITL routing |
| `docs/architecture/AGENT_FLOW.md` | Node-by-node flow reference |
| `tests/test_graph.py` | Graph wiring tests |
| `tests/test_graph_summarize_wiring.py` | Summarize gate tests |

```
START → memory_inject_lite → router → memory_retrieve → auto_summarize? → simple → memory_write → END
                                                                              → scope_clarify → complex_llm ◄─┐
                                                                                    → plan_review            │
                                                                                    → security_proxy         │
                                                                                    → tool_action ───────────┘
                                                                                    → memory_write → END
```

## Common agent tasks

### Add router keyword bypass

1. Edit `src/agent/nodes/router.py` — `simple_keywords` or `_WEBISH_HINTS`
2. Run `pytest tests/test_router_properties.py tests/test_router_web_intent.py -q`
3. Update [`EXTENDING_AGENT.md`](EXTENDING_AGENT.md) if behavior contract changes

### Add a new tool

1. Implement in `src/tools/<module>.py` with `@tool` decorator
2. Register in `src/agent/tool_sets.py` (`COMPLEX_TOOLS_*` or `ToolboxRegistry`)
3. Run `pytest tests/test_toolbox_registry.py -q`
4. Update [`TOOLS.md`](TOOLS.md) entry points block

### Change a WebSocket event

1. Edit `src/api/ws/handler.py` — `serialize_message()` / emit helpers
2. Update `frontend-v2/src/types/protocol.ts` and consumers in `App.tsx`
3. Run `pytest tests/test_websocket_event_contract.py -q`
4. Update [`CHAT_PROTOCOL.md`](CHAT_PROTOCOL.md) -> `docs/development/CHAT_PROTOCOL.md`

### Fix memory panel / context

1. Trace `src/agent/nodes/memory.py` → `src/memory/`
2. Run `pytest tests/test_memory_nodes.py tests/test_crud_operations.py -q`
3. Check [`debugging/memory.md`](debugging/memory.md) for symptom hints

### Swap a model

1. Edit `src/config/defaults.yaml` — `models.small.model_name` or `models.cloud.model_name`
2. Match LM Studio loaded name exactly
3. Run `pytest tests/test_llm_pool.py -q`

## CI, tests, and evaluation

| Command | Scope |
|---------|--------|
| `./scripts/ci.sh --quick` | Ruff, mypy, **919** pytest (excl. network/benchmark), contract tests, **111** vitest — pre-push default |
| `./scripts/ci.sh` | Above + frontend production build |
| `./scripts/ci.sh --network` | Live DeepSeek tests (`DEEPSEEK_API_KEY` required) |
| `./scripts/ci.sh --benchmarks` | Router/complex/memory benchmarks → `tests/benchmarks/benchmark_report.json` |
| `python scripts/run_local_frontier_eval.py` | ~19-turn mechanical eval — `--profile auto\|local\|cloud`, `--cloud-off`, `--strict-cloud` |
| `python scripts/run_educator_eval.py` | 8-turn UID10667 study session — `--strict-cloud` |
| `python scripts/run_frontier_comparison_eval.py` | Quality A/B vs raw DeepSeek — `--dry-run`, `--limit N` |
| `python scripts/run_browser_eval.py` | 12-turn conversation eval — `--strict-cloud`; per-turn circuit-breaker reset |

**Coverage (unit pytest):** ~57% `src/` (contract-only pass ~22% — subset). **GHA** (`.github/workflows/ci.yml`): Python lint/tests + frontend vitest; Electron build on main push only. Contract/cutover tests are **local-only** per `scripts/ci.sh`.

**Eval artifacts:** `data/frontier_eval_run_data.json`, `data/eval_run_data.json`, report in `docs/evaluations/`. Standard: [`docs/standards/EVALUATION.md`](standards/EVALUATION.md).

### Key test files (post BUG-13..16)

| Area | Tests |
|------|-------|
| Web search synthesis | `tests/test_tool_output_delta.py`, `tests/test_dsml_formatter.py`, `tests/test_fetch_retry_nudge.py` |
| Cloud usage / breakdown | `tests/test_context_breakdown.py`, `tests/test_cloud_*.py`, `tests/test_cloud_payload_integration.py` |
| Strict cloud / eval harness | `tests/test_cloud_strict_mode.py`, `tests/test_frontier_eval_scoring.py` |
| Educator memory | `tests/test_educator_memory.py` |
| Cloud chip (frontend) | `frontend-v2/src/components/__tests__/cloud-usage-chip.test.tsx`, `cloud-settings.test.tsx` |

## Development rules

1. Keep diffs focused to the user request
2. Preserve security proxy / plan_review behavior around tool execution
3. When touching routing, add or update targeted tests
4. Run `./scripts/ci.sh --quick` before push
5. Update the relevant task doc when API/WS/tool contracts change
6. After significant eval runs, add `docs/evaluations/<name>-YYYY-MM-DD.md` and index in `docs/INDEX.md`

## Related

- [`AGENTS.md`](../AGENTS.md) — agent entry point
- [`architecture/overview.md`](architecture/overview.md) — architecture overview
- [`debugging/README.md`](debugging/README.md) — symptom index
- [`standards/coding-style.md`](standards/coding-style.md) — code conventions

## Last updated

2026-06-18 — strict-cloud BUG-27..29; eval harness + cloud_payload compaction
