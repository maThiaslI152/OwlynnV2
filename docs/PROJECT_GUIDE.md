---
status: active
category: reference
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# Owlynn Project Guide

> **Purpose:** Canonical file map for AI agents. Use this to locate source files, contracts, and tests before making changes.

Related: [`architecture/overview.md`](architecture/overview.md) (system shape), [`STATUS.md`](STATUS.md) (bugs/risks), [`ADR.md`](ADR.md) (decisions).

---

## Routing and model behavior

| File | Role |
|------|------|
| `src/agent/nodes/router.py` | `router_node()` — classification, keyword bypass, HITL clarification |
| `src/agent/router/classifier.py` | LLM JSON routing classifier |
| `src/agent/router/budget.py` | Token budget tiers and input reserves |
| `src/agent/router/selector.py` | Model/toolbox selection |
| `src/agent/llm.py` | `LLMPool` singleton — small + medium + cloud slots |
| `src/agent/nodes/simple.py` | Fast simple-path answers (no tools) |
| `src/agent/nodes/complex.py` | Tool-calling cycle, local + cloud paths |
| `src/agent/nodes/complex_utils/cloud_payload.py` | Cloud prompt layers, anonymization |
| `src/agent/nodes/complex_utils/cloud_invoke.py` | DeepSeek client, tool strict mode |
| `src/agent/nodes/complex_utils/vision_florence.py` | Florence OCR parser |
| `src/agent/nodes/complex_utils/vision_*.py` | Vision proxy for cloud image path (Florence default) |
| `src/tools/mcp_client.py` | MCP stdio client; tools merged via `merge_mcp_tools()` |
| `mcp_config.json` | MCP server manifests (see `mcp_config.json.example`) |
| `src/config/defaults.yaml` | Model names, routing, `mcp.*`, `startup.preload` (source of truth) |
| `tests/test_router_properties.py` | Router property tests |
| `tests/test_router_web_intent.py` | Web-intent forcing tests |
| `tests/test_llm_pool.py` | LLM pool tests |

**Current models** (`defaults.yaml`): router `minicpm5-1b`, fallback complex `qwen3.5-9b-uncensored-hauhaucs-aggressive@q6_k`, vision proxy `florence-2-base-nsfw-v2-ext-mlx`, cloud `deepseek-v4-flash`. Startup preloads router + embedding only when cloud escalation is enabled.

## Complex / cloud path

| File | Role |
|------|------|
| `src/agent/nodes/complex.py` | `complex_llm_node()`, `complex_tool_action_node()`, `_resolve_complex_tools()` |
| `src/agent/nodes/complex_utils/cloud_payload.py` | Brief gate, PII scrub, cache metrics |
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
| `src/api/ws/handler.py` | WebSocket streaming, event serialization |
| `docs/CHAT_PROTOCOL.md` | WS event contract |
| `docs/API_REFERENCE.md` | REST reference |
| `tests/test_websocket_event_contract.py` | WS contract tests |
| `tests/test_frontend_backend_alignment.py` | Frontend/backend alignment |

## Frontend

| File | Role |
|------|------|
| `frontend-v2/src/App.tsx` | App shell, WebSocket lifecycle, HITL resume |
| `frontend-v2/src/lib/electronBridge.ts` | Electron IPC (Safe Mode, screen assist) |
| `frontend-v2/src/lib/wsClient.ts` | WebSocket client |
| `frontend-v2/src/state/useAppStore.ts` | Zustand store |
| `frontend-v2/electron/main.ts` | Electron main process |
| `frontend-v2/src/components/AppShell.tsx` | Layout shell |

## Memory

| File | Role |
|------|------|
| `src/agent/nodes/memory.py` | `memory_inject_lite`, `memory_retrieve`, `memory_write` |
| `src/memory/` | STM/LTM/personal managers, Mem0/Qdrant |
| `data/topics.json` | Personal topic decay (runtime data) |
| `docs/MEMORY.md` | Memory tier contract |
| `tests/test_memory_nodes.py` | Memory node tests |
| `tests/test_memory_retrieve_gate.py` | Gated retrieval tests |

## Tools

| File | Role |
|------|------|
| `src/agent/tool_sets.py` | `ToolboxRegistry`, tool list resolution |
| `src/tools/` | Tool implementations (`@tool` decorators) |
| `docs/TOOLS.md` | Tool reference |
| `tests/test_toolbox_registry*.py` | Toolbox tests |
| `tests/test_mcp_tool_binding.py` | MCP merge + HITL prefix tests |
| `tests/test_web_tools.py` | Web search tools |

## Config

| File | Role |
|------|------|
| `src/config/defaults.yaml` | All defaults — edit here first |
| `src/config/config_loader.py` | YAML + env + profile merge |
| `src/config/settings.py` | Workspace roots, paths |

## Graph orchestration

| File | Role |
|------|------|
| `src/agent/graph.py` | `build_graph()`, conditional edges, HITL routing |
| `docs/AGENT_FLOW.md` | Node-by-node flow reference |
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
4. Update [`CHAT_PROTOCOL.md`](CHAT_PROTOCOL.md)

### Fix memory panel / context

1. Trace `src/agent/nodes/memory.py` → `src/memory/`
2. Run `pytest tests/test_memory_nodes.py tests/test_crud_operations.py -q`
3. Check [`debugging/memory.md`](debugging/memory.md) for symptom hints

### Swap a model

1. Edit `src/config/defaults.yaml` — `models.small.model_name` or `models.medium.model_name`
2. Match LM Studio loaded name exactly
3. Run `pytest tests/test_llm_pool.py -q`

## Development rules

1. Keep diffs focused to the user request
2. Preserve security proxy / plan_review behavior around tool execution
3. When touching routing, add or update targeted tests
4. Run `./scripts/ci.sh --quick` before push
5. Update the relevant task doc when API/WS/tool contracts change

## Related

- [`AGENTS.md`](../AGENTS.md) — agent entry point
- [`architecture/overview.md`](architecture/overview.md) — architecture overview
- [`debugging/README.md`](debugging/README.md) — symptom index
- [`standards/coding-style.md`](standards/coding-style.md) — code conventions

## Last updated

2026-06-10 — agent-first documentation overhaul
