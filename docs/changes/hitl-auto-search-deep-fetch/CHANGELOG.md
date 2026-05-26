# Changelog: hitl-auto-search-deep-fetch

## 2026-06-01 — Initial scaffolding

- Created SDD skeleton for HITL auto-search & deep content fetch change

## 2026-06-01 — Task 1: SAFE_TOOLS + scope_clarify web route

- Added `SAFE_TOOLS` set and `is_information_retrieval()` to `src/agent/hitl/policy.py`
- Updated `src/agent/nodes/security_proxy.py` — fast-path auto-approval for all-safe tool calls
- Added `_looks_like_searchable_query()` + web search bypass to `src/agent/nodes/scope_clarify.py`
- Injected `web_search_suggested` prompt instruction in `src/agent/nodes/complex.py`

## 2026-06-01 — Tasks 2–3: Deep fetch prompt + cutoff detection

- Added deep fetch instruction to `COMPLEX_TOOL_GUIDANCE_WEB`: auto-call `fetch_webpage` after search when snippets are insufficient
- Added browser capture tool instruction to tool guidance (when browser MCP tools available)
- Added `MAX_CUTOFF_RETRIES=3` constant and `_cutoff_pending` state field
- Modified `llm_next_step` in `src/agent/graph.py` to route back to `complex_llm` on cutoff
- Added cutoff detection (`finish_reason=='length'`) and continuation prompt injection in `src/agent/nodes/complex.py`
