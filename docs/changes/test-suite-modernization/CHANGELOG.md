# Test Suite Modernization & Unified Architecture Alignment

**Date:** 2026-08-23
**Status:** Completed & Verified (100% Passing CI — 1,068 Python unit/contract/property tests, 131 Vitest tests)

---

## 1. Overview & Objectives

Following the architectural migration to the Unified Local-First Model Architecture, this refactoring audited and modernized the entire test suite across unit, contract, property-based, benchmark, standalone, and frontend test suites.

Eliminated obsolete test fixtures, replaced deprecated monkeypatches and mock targets with canonical `get_main_llm()` and `main_llm_*` configuration fields, modernized model provenance badges, removed dead state schema properties (`current_medium_model`), and added test coverage for the new `cloud_routing_mode` setting in frontend Vitest.

---

## 2. Key Changes by Test Suite

### LLM Pool & Model Configuration
- **`tests/test_llm_pool.py`**:
  - Updated test profile to use canonical `main_llm_base_url` and `main_llm_model_name`.
  - Added unit test cases for `LLMPool.get_main_llm()`, `LLMPool.get_fallback_llm()`, and `LLMPool.get_pentest_llm()`.
  - Verified `LLMPool.clear()` resets all slots including `_main_llm`, `_fallback_llm`, and `_pentest_llm`.
- **`tests/test_websocket_model_key_updates.py`**:
  - Modernized `_FakeAgent` to read `main_llm_model_name` from profile.
  - Tested profile updates against `main_llm_model_name` with assertions on emitted `model_info` WebSocket events.
- **`tests/test_unified_settings.py`**:
  - Updated field assertions to include `main_llm_base_url`, `main_llm_model_name`, and `cloud_routing_mode`.

### LangGraph Nodes & State Properties
- **`tests/test_complex_node_properties.py`**:
  - Updated valid route domains to `complex-default` and `complex-cloud`.
  - Aligned route-to-model mapping (`complex-default` -> `"main-local"`, `complex-cloud` -> `"large-cloud"`).
  - Added property assertions verifying `complex-default` invokes `get_main_llm()` directly while `complex-cloud` invokes cloud path.
- **`tests/test_model_badge_properties.py`**:
  - Updated `KNOWN_MODELS` with canonical values: `"main-local"`, `"large-cloud"`, `"main-local-fallback"`, `"pentest-local"`.
  - Verified badge class mapping (`main-local` -> `model-badge-small`, `large-cloud` -> `model-badge-cloud`, `*-fallback` -> `model-badge-fallback`).
- **`tests/test_conversation_continuity.py` & `tests/test_conversation_continuity_properties.py`**:
  - Removed dead state key (`current_medium_model`) from `AgentState` test fixtures.
  - Verified multi-turn message history preservation across `main-local`, `large-cloud`, and fallback turns.
- **`tests/test_auto_summarize_threshold_properties.py` & `tests/test_protected_message_preservation_properties.py` & `tests/test_summarize_node.py`**:
  - Updated `src/agent/nodes/summarize.py` to directly call `get_main_llm()`.
  - Updated test mock patches to `@patch("src.agent.nodes.summarize.get_main_llm")`, preventing unmocked live network calls during Hypothesis property runs.
- **`src/agent/nodes/coherence.py` & `tests/test_response_coherence.py`**:
  - Updated coherence node to invoke `get_main_llm()` and modernized test monkeypatches.
- **`tests/test_router_integration.py` & `tests/test_router_hitl_choices.py` & `tests/test_memory_orchestration_smoke.py`**:
  - Patched `get_main_llm` in router integration and memory smoke tests.

### Startup Preloading & Standalone Scripts
- **`tests/test_startup_preload.py`**:
  - Refactored to test unified startup preload behavior: preloading `LLMPool.get_main_llm()` on AC power, and skipping heavy preloads on battery in Eco-Mode.
- **`tests/standalone/test_lm_studio_model_load_unload.py`**:
  - Replaced hardcoded legacy models with `config.get_main_model_name()` and `config.get_pentest_model_name()`.

### Benchmarks
- **`tests/benchmarks/conftest.py`**:
  - Updated `ProfileBuilder` with `main_llm_base_url`, `main_llm_model_name`, `cloud_routing_mode`.
- **`tests/benchmarks/test_llm_pool_benchmark.py`**:
  - Modernized concurrent pool access benchmark to measure `LLMPool.get_main_llm()`.

### Frontend Vitest Suite
- **`frontend-v2/src/components/__tests__/cloud-settings.test.tsx`**:
  - Added test case verifying `Cloud Routing Policy` selector renders and updates `cloud_routing_mode` via `PUT /api/unified-settings`.

---

## 3. Verification & CI Results

- **Python Tests**: **1,068 passed**, 8 skipped.
- **Audit & Contract Tests**: **22 passed**.
- **Frontend Vitest Tests**: **131 passed** across 19 test files.
- **Ruff Lint & Format**: Clean across all 383 source and test files.
- **Mypy Type Checking**: Clean across all 213 source files.
- **WS Payload Drift**: 0 drift (`protocol.generated.ts` is up to date).
