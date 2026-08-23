# Unified Local-First Model Architecture with Battery Offload & Cloud Policy Switch

**Date:** 2026-08-23
**Status:** Completed & Verified (100% Passing CI — 1,062 Python unit/contract/property tests, 130 Vitest tests)

---

## 1. Overview & Objectives

Refactored Owlynn's model architecture to treat the unified local agentic model (`models.main`) as the primary execution engine for all standard workflows (simple chat, summarization, memory extraction, tool-augmented complex planning, and coherence checks), eliminating the concept of local models as a "fallback".

Introduced a tri-state **Cloud Routing Policy** (`auto`, `local_only`, `cloud_first`) with dynamic battery-awareness (Eco-Mode) that offloads computationally intensive generation to DeepSeek API on battery to conserve host energy and laptop thermals.

---

## 2. Key Changes by Subsystem

### Configuration & User Profile
- **`src/config/settings_constants.py`**: Added `main_llm_base_url`, `main_llm_model_name`, `cloud_routing_mode` (default: `"auto"`).
- **`src/memory/user_profile.py`**: Expanded `VALID_FIELDS` to include `cloud_routing_mode`, `main_llm_base_url`, `main_llm_model_name`, `vision_llm_*`, and `pentest_llm_*`.
- **`src/config/defaults.yaml`**: Clarified unified local model specification and documented cloud offloading parameters.

### Power & Battery Monitor
- **`src/api/power_monitor.py`**:
  - Implemented `is_eco_mode_active()` to check battery/thermal throttling state.
  - Implemented `should_use_cloud_for_power(profile)` to trigger DeepSeek offload when on battery in `"auto"` routing mode.

### Router & Resolution Logic
- **`src/agent/routing/resolver.py` & `src/agent/routing/router.py`**:
  - Refactored `_resolve_complex_route()` to default to `complex-default` (local main model).
  - Implemented `_should_route_to_cloud()`:
    - If `cloud_routing_mode == "local_only"`: forces 100% offline local execution.
    - If `cloud_routing_mode == "cloud_first"`: prioritizes DeepSeek cloud execution.
    - If `cloud_routing_mode == "auto"`: executes locally on AC power; dynamically offloads to `complex-cloud` when on battery/Eco-Mode or when high-tier frontier reasoning (formal proof, deep coding, novel architecture) is requested.

### Execution Layer & LLM Pool
- **`src/agent/llm.py`**:
  - Unified local instance acquisition via `get_main_llm()`.
  - Added backward-compatible aliases for legacy test harnesses (`get_small_llm = get_main_llm`).
  - Added test override fallbacks for `"medium"`, `"complex_local"`, and `"small"`.
- **`src/agent/core/complex.py` & `src/agent/core/complex_executor.py`**:
  - `complex-default` runs directly on `get_main_llm()` with label `"main-local"`.
  - `complex-cloud` invokes `get_cloud_llm()` with automatic fallback to `_invoke_local_fallback` (`"main-local-fallback"`).
  - Maintained pentest isolation on `get_pentest_llm()` (`"pentest-local"`).
- **`src/agent/core/simple.py`**, **`src/agent/nodes/summarize.py`**, **`src/agent/nodes/coherence.py`**:
  - Standardized on `get_main_llm()` with label `"main-local"`.

### WebSocket & Frontend UI
- **`src/api/ws/handler.py`**: Mapped `simple`, `complex-default`, `complex-local` to `"main-local"` in WebSocket `router_info` metadata.
- **`frontend-v2/src/components/shared/CloudSettingsPanel.tsx`**:
  - Added `Cloud Routing Policy` selector (`Auto (Local on AC / Cloud on Battery)`, `Local Only (100% Offline)`, `Cloud First (Prefer DeepSeek)`).
  - Refreshed panel copy to highlight Local-First Architecture.
- **`frontend-v2/src/components/layout/StatusBar.tsx`**: Defaulted status bar model indicator to `"Local"`.

---

## 3. Verification & CI Results

- **Python Tests**: 1,062 passed, 8 skipped, 85 deselected.
- **Audit & Contract Tests**: 22 passed.
- **Vitest Frontend Tests**: 130 passed across 19 test files.
- **Frontend Type Generation**: Zero drift (`protocol.generated.ts` clean).
- **Linters & Type Checkers**: Ruff lint passed, Ruff format passed, Mypy passed (213 source files clean).
