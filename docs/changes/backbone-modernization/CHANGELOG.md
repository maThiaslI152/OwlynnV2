# Changelog: Backbone Modernization, Prompt Cache Preservation & Architecture Cleanup

**Date:** 2026-08-22  
**Status:** Completed  
**Author:** AI Agent (Antigravity)  

---

## 1. Context & Motivation

Owlynn's backend orchestration was evaluated against production agent patterns from **Hermes** (`/Volumes/KNV3_1TB/project/Hermes`), identifying several architectural opportunities:
1. **Monolithic Complexity**: `src/agent/core/complex.py` was an 1,846-LOC monolith mixing prompt building, model invocation, tool execution, and cutoff recovery.
2. **KV Prompt Cache Invalidation**: Mid-turn tool error recovery injected synthetic `HumanMessage` prompts into conversation history, breaking DeepSeek/Claude prompt caching and violating message role alternation. Tool lists were also bound in arbitrary order.
3. **Context Compaction Gaps**: Context summarization did not prune bloated historical tool outputs before invoking the small local summarizer, and compacted history lacked anti-hallucination reference tags.
4. **Static Tool Definitions**: Tools were statically resolved without prerequisite service gating (`check_fn`) or dynamic discovery.
5. **Dependency Bloat**: Core dependencies included unneeded packages (`alphashape`, `streamlit`, `posthog`, `testcontainers`, `trimesh`, `unclecode-litellm`).

---

## 2. Changes Made

### A. Dependency Modernization & Cleanup (`pyproject.toml`, `requirements.txt`)
- Pruned dead legacy dependencies (`alphashape`, `contourpy`, `cycler`, `fonttools`, `kiwisolver`, `posthog`, `rtree`, `shapely`, `streamlit`, `streamlit-sortables`, `testcontainers`, `trimesh`, `unclecode-litellm`).
- Bumped core pins: `cryptography>=50.0.0`, `mcp>=2.0.0`, `httpx2>=2.7.0`.
- Structured optional dependencies into clean groups (`docs`, `browser`, `viz`).

### B. Decomposed `complex.py` Monolith into 4 Targeted Modules
- **`src/agent/core/complex.py`** (~100 LOC Facade): Thin LangGraph node coordinator facade exporting `complex_llm_node` and `complex_tool_action_node`.
- **`src/agent/core/complex_prompt.py`**: Stable vs. volatile prompt templates, date-stripped stable prefixes, deterministic alphabetical tool sorting, and context budget calculations.
- **`src/agent/core/complex_executor.py`**: Cloud LLM invocation, fallback chains, thinking configuration, and cutoff continuation.
- **`src/agent/core/complex_tool_action.py`**: Parallel tool dispatch, sequential barrier for state-mutating tools (`_SERIAL_TOOLS`), tool output bounding (`_MAX_TOOL_OUTPUT_CHARS = 20000`), and in-place `ToolMessage` hint enrichment.

### C. KV Prompt Cache Preservation
- Replaced synthetic `HumanMessage("[Internal reminder] ...")` injections with in-place hint enrichment on `ToolMessage(content="...")`.
- Deterministically sorted all tool definitions alphabetically before binding to LLMs.
- Ensured strict role alternation (`system -> user -> assistant -> tool -> assistant`).

### D. 3-Tier Context Window Compaction (`src/agent/nodes/summarize.py`)
- **Stage 1 (Pre-Pass Pruning)**: Pruned tool outputs exceeding 400 characters prior to summarization.
- **Stage 2 (Reference-Only Snapshot Header)**: Injected `[CONTEXT COMPACTION — REFERENCE ONLY]` and `## Historical Task Snapshot` headers to prevent LLM re-execution hallucinations.
- **Stage 3 (Tail Protection)**: Maintained turn counting while protecting recent dialogue context.

### E. Dynamic Tool Registry (`src/tools/registry.py`)
- Created `ToolRegistry` with `@registry.register(name, toolbox, check_fn=...)`.
- Implemented 60-second TTL caching for service prerequisite checks (`check_fn`).
- Added long-lived persistent event loop (`_get_tool_loop()`) for robust sync-to-async bridging.
- Added bounded error output truncation (`_MAX_TOOL_ERROR_CHARS = 2048`).
- Integrated `TOOLBOX_REGISTRY` into global `registry`.

### F. Fine-Grained Cloud Error Classification (`src/agent/cloud/error_classifier.py`)
- Implemented `FailoverReason` enum (`rate_limit`, `quota`, `context_length`, `auth`, `server_error`, `timeout`, `unknown`).
- Added `classify_cloud_error(exc)` and `jittered_backoff(attempt)` to avoid thundering-herd retry storms.

---

## 3. Files Changed & Created

| Path | Role |
|------|------|
| `pyproject.toml` | Bumped cryptography, mcp, httpx2; pruned dead deps; added optional groups |
| `requirements.txt` | Cleaned and pinned core requirements |
| `src/agent/core/complex.py` | Refactored into thin coordinator facade |
| `src/agent/core/complex_prompt.py` | [NEW] Prompt builder, guidance strings, deterministic tool sorting |
| `src/agent/core/complex_executor.py` | [NEW] Cloud & fallback invocation, cutoff continuation |
| `src/agent/core/complex_tool_action.py` | [NEW] Parallel tool dispatch, output bounding, ToolMessage hint enrichment |
| `src/agent/core/__init__.py` | [NEW] Package init for agent core |
| `src/agent/nodes/summarize.py` | Upgraded with tool output pre-pruning and reference-only snapshot header |
| `src/tools/registry.py` | [NEW] Dynamic tool registry with check_fn gating and persistent event loop |
| `src/agent/tool_sets.py` | Auto-registered all toolbox tools into global `ToolRegistry` |
| `src/agent/cloud/error_classifier.py` | [NEW] Fine-grained error classification and jittered backoff |
| `src/api/file_processor.py` | Made `main_loop` optional in `FileWatcherHandler.__init__` |
| `scripts/ci.sh` | Added automatic `.venv` activation and extended format check to tests/ |
| `src/agent/core/checkpointer.py` | Hardened PostgreSQL saver against non-Postgres URLs in test runs |
| `src/memory/long_term.py` | Fixed `_run_async` thread deadlock via ThreadPoolExecutor |
| `src/memory/project.py` | Made `remove_knowledge` natively await `_async_delete` |
| `tests/test_websocket_event_contract.py` | Eliminated AnyIO TestClient portal deadlocks and updated mock targets |
| `AGENTS.md` | Updated task routing, KV Cache rules, and changelog |
| `docs/architecture/overview.md` | Updated architecture overview and module table |
| `docs/features/TOOLS.md` | Updated tool architecture and entry points |
| `docs/features/MEMORY.md` | Updated memory architecture for pgvector and extraction queue |
| `docs/INDEX.md` | Updated manifest version (22) and timestamps |

---

## 4. CI Audit & Test Hardening

1. **WebSocket Test Deadlock Elimination** (`tests/test_websocket_event_contract.py`):
   - Corrected mock patch target to `src.api.controllers.graph_session.GraphSession.start_run`.
   - Used dedicated `crud_client = TestClient(client.app)` instances for interleaved REST calls while WebSockets are connected, eliminating portal acquisition locks.
   - Refactored `cleanup_projects_via_api` fixture to invoke `project_manager.delete_project` directly.
2. **Main-Thread Asyncio Deadlock Prevention** (`src/memory/long_term.py` & `src/memory/project.py`):
   - Re-engineered `_run_async()` with `concurrent.futures.ThreadPoolExecutor` when called inside an active event loop thread.
   - Updated `remove_knowledge()` to natively `await _async_delete()`.
3. **Checkpointer & Database Pool Hardening** (`src/agent/core/checkpointer.py` & `src/api/controllers/graph_session.py`):
   - Guarded `_get_pool()` and `get_postgres_saver()` against SQLite database URLs.
4. **Pentest Retrieval Async Safety** (`src/agent/nodes/memory.py` & `src/tools/core_tools.py`):
   - Added `await` to `get_active_engagement()`, `get_engagement_context()`, `get_findings_summary()`, and `list_findings()`.
   - Added coroutine unwrapping to `recall_memories`.

---

## 5. Verification Matrix (100% Green)

The complete CI pipeline (`./scripts/ci.sh`) was executed and passed with zero errors:

| Check | Scope | Result |
|-------|-------|:------:|
| **Python Linter** | `ruff check src/ tests/` | **PASS (0 errors)** |
| **Python Formatter** | `ruff format --check src/ tests/` | **PASS (379 files clean)** |
| **Static Type Analysis** | `mypy src/ --ignore-missing-imports` | **PASS (211 source files, 0 errors)** |
| **Python Unit & Property Tests** | `pytest -m "not network and not benchmark"` | **PASS (1,064 tests)** |
| **Audit & Contract Tests** | `test_websocket_event_contract.py`, `test_frontend_cutover_serving.py` | **PASS (22 tests)** |
| **Frontend Type Drift** | `npm run generate:types` | **PASS (No drift)** |
| **Frontend Linter** | `npm run lint` | **PASS (0 errors)** |
| **Frontend Vitest Suite** | `npx vitest run` | **PASS (19 files, 131 tests)** |
| **Production & Electron Build** | `npm run build` | **PASS (DMG & ZIP generated)** |
