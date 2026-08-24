---
status: active
category: changelog
audience: agent
last_updated: 2026-08-24
owner: ai-agent
---

# Changelog: Local Tool Bind Cap (TTFT)

> **Purpose:** Narrow local-first toolboxes, slim the `"all"` catalog, and make context telemetry count post-rerank schemas.

## 2026-08-24 — Optimize local tool binding

### What

- **Local-first routing** (`_toolbox_for_local_first`): keyword helpers for screen/files/viz; live-data / webish hints (including `latest`, `newest`, `current version`, `release`, `changelog`, `update of`) → `["web_search"]`; otherwise lean default `["web_search", "memory", "productivity"]`. Never implicit `["all"]`.
- **Lean `"all"` catalog**: `COMPLEX_TOOLS_WITH_WEB` / `NO_WEB` drop screen-assist and ipynb tools; named `screen_assist` / `data_viz` toolboxes still include them.
- **Rerank before telemetry**: `_rerank_tools_for_invoke` caps the bind list before invoke and `enrich_token_usage_with_breakdown`; `bound_tool_count` matches the post-rerank list.
- **Schemas in context chip**: breakdown category `schemas` folded into `input_estimated` / `total_used`; CloudUsageChip shows a **Schemas** row.

### Why

Local-first turns previously hardcoded `selected_toolboxes=["all"]` (~36 tools), then reranked to 8 at invoke while UI telemetry still reported the pre-rerank catalog (~11k schema tokens). That inflated TTFT cost and hid the real prefill mix (~system + ~8 schemas).

### Files

- `src/agent/routing/router.py`, `deterministic.py`
- `src/agent/tool_sets.py`
- `src/agent/core/complex.py`, `complex_utils/context_breakdown.py`
- `frontend-v2/src/components/shared/CloudUsageChip.tsx`, `lib/cloudUsage.ts`, `state/types.ts`
- Tests: `test_router_web_intent.py`, `test_toolbox_registry.py`, `test_tool_skill_limit_optimization.py`, `test_context_breakdown.py`, `cloud-usage-chip.test.tsx`
- Docs: `docs/features/TOOLS.md`, `docs/development/EXTENDING_AGENT.md`, `docs/architecture/AGENT_FLOW.md`, `docs/technical/model-quirks-and-routing.md`
