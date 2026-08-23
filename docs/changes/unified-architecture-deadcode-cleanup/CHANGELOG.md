# Changelog: Unified Local Architecture & Dead Code Cleanup

**Date:** 2026-08-23  
**Status:** Completed  

---

## 1. Overview

Eliminated dead code and legacy artifacts from the former split "small-complex" model architecture. Unified configuration dotpaths, scheduler primitives, node invocations, and settings API endpoints around the **Unified Local Model Architecture** (`gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m`), providing 0ms mode transitions and clean, maintainable model pipelines.

---

## 2. Key Changes

### Configuration & Settings
- **`src/config/config_loader.py`**:
  - Updated `_ENV_FALLBACKS` and `_PROFILE_OVERRIDE_MAP` to map `SMALL_LLM_*` aliases directly to `models.main.*`.
  - Updated `_DEFAULT_PROPERTIES` to track active model keys (`models.main.*`, `models.vision.*`, `models.pentest.*`, `models.cloud.*`, `models.embedding.*`).
- **`src/config/settings_constants.py`**:
  - Updated `_ADVANCED_SETTINGS_DEFAULTS.max_tokens` to query `models.main.max_tokens` (default 8,192) instead of obsolete `models.standard.small.max_tokens`.
- **`src/api/routes/settings.py`**:
  - Updated `GET /api/unified-settings` `llm_fields` dictionary to resolve active keys (`main_llm_base_url`, `main_llm_model_name`, `pentest_llm_model_name`, `vision_llm_model_name`, `embedding_llm_model_name`, `cloud_llm_base_url`, `cloud_llm_model_name`), eliminating dead `models.medium.*` lookups.

### Model Pool & Scheduler
- **`src/agent/local_llm_scheduler.py`**:
  - Renamed internal state and context managers from `_foreground_medium` to `_foreground_main`, `foreground_main_slot`, `background_main_slot`, `wrap_main_for_foreground`, and `invoke_main_background` (preserving backward-compatible aliases for legacy callers).
- **`src/agent/llm.py`**:
  - Cleaned up docstrings and unified `get_complex_local_llm()` to return the configured main unified local model.
- **`src/agent/model_swap.py`**:
  - Updated `_main_model_key()` to query `models.main.lm_studio_model_key`. Fast-pathed model swapping to 0ms when `main` and `pentest` use the same model engine.

### Core Nodes & Toolsets
- **`src/agent/core/simple.py`**:
  - Replaced legacy `get_model_config("small")` lookups with `get_model_config("main")`.
- **`src/agent/core/complex_prompt.py`**:
  - Removed unused legacy `COMPLEX_PROMPT` template (preserved active `COMPLEX_PROMPT_STABLE`).
- **`src/agent/core/complex_executor.py`**:
  - Fixed missing `HumanMessage` import and converted stop tokens to query `get_model_config("main")`.
- **`src/agent/tool_sets.py`**:
  - Removed duplicate `"study"` dictionary entry in `TOOLBOX_REGISTRY`.

---

## 3. Verification

- **Python Unit Tests**: 1,063 passed (100% passing).
- **Audit/Contract Tests**: 22 passed.
- **Mypy Static Type Checking**: Passed (213 source files checked).
- **Ruff Lint & Format**: Passed (383 files checked).
- **Frontend Vitest Suite**: 130 passed (19 test files).
- **Desktop Application**: Packaged and installed to `/Volumes/KNV3_1TB/Applications/Owlynn.app`.
