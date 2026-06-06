# CHANGELOG: Task 950 - Codebase Modernization and CI/CD Fixes

## Overview
This document serves as the full documentation for the implementation of Task 950, focusing on code modernization to LangGraph 1.x patterns, test environment stability, deadlock resolution, and CI/CD improvements.

## Implemented Changes

### 1. Test Environment Isolation (`tests/conftest.py`)
- **Issue:** The test suite was hanging indefinitely due to side-effects from importing modules that instantiated LLM connections, specifically hitting the `_preload_llms` function in `src.api.server`.
- **Resolution:** Introduced `OWLYNN_TESTING=1` and `OWLYNN_NO_PRELOAD=1` as mandatory environment variables during tests. This ensures that slow LLM startup routines are bypassed.

### 2. Resolution of Circular Import Deadlocks
- **Issue:** `src.config.audit_log.py` exhibited a circular import deadlock. It attempted to import the `config` object inside the `_sanitize_value` utility method during logger initialization.
- **Resolution:** Hardcoded the truncation limit (`_SANITIZE_MAX_LEN = 500`) to decouple the audit logging system from the dynamic configuration loader. This ensures `audit_log` initializes smoothly without triggering a recursive lock.

### 3. Notebook Tool Hang Resolution
- **Issue:** The `notebook_run` tool was causing tests to hang. It wrote `json.dumps({"action": "reset"}) + "\\n"` instead of the newline character `\n` to the worker process, causing `readline()` in the worker to block indefinitely. Furthermore, the subprocess call used `python3` instead of the current active virtual environment Python.
- **Resolution:**
  - Replaced literal `\\n` with actual newline `\n` in `src.tools.notebook.py`.
  - Switched from calling `python3` to using `sys.executable` to guarantee alignment with the host Python environment.

### 4. Single Source of Truth Enforcement (Config/Models)
- **Issue:** Several endpoints and objects referenced a legacy `medium_models` property instead of relying exclusively on `defaults.yaml` (the Single Source of Truth).
- **Resolution:** 
  - Flattened model variants inside `config_loader.py`.
  - Maintained backward compatibility by retaining the `get_model_config` interface while cleaning up internal API logic to read dynamically rather than storing state in objects like `user_profile.py`.
  - **Rationale:** A comment was added to `src/config/config_loader.py` explaining that we deliberately chose not to completely rewrite the core config loader or the `models.medium` legacy schema. Doing so would risk breaking the React frontend UI and existing API clients.

### 5. HITL Security Proxy Logic Corrections
- **Issue:** The `security_proxy_node` crashed with `UnboundLocalError` when the Execution Policy was set to `auto_approve`. The logic improperly invoked `interrupt(enriched_payload)` when `enriched_payload` was never initialized.
- **Resolution:** Restructured the conditional flow in `src.agent.nodes.security_proxy.py` to only construct and dispatch the HITL payload if human intervention is strictly required, properly bypassing the logic on `auto_approve`. Test mocks for `get_profile` were added to guarantee execution paths are tested correctly.

### 6. Anonymization Placeholders Fixes
- **Issue:** Placeholders changed format from `[CATEGORY_1]` to a deterministic hash `[CATEGORY_hash]`, which broke tests that relied on strict string matching.
- **Resolution:** Updated `PLACEHOLDER_RE` in tests to accommodate an 8-character hex string `[a-f0-9]{8}` and replaced strict `_1` assertions with `.get()` loops.

### 7. CI/CD Environment Modernization
- **Issue:** The pipeline infrastructure was outdated.
- **Resolution:** Migrated `python-ci.yml` entirely to use `uv`, substantially reducing cache misses and package resolution bottlenecks.

## Testing Status
All 800+ tests have been successfully verified locally against these changes via `pytest` without triggering deadlocks, skipped network connections, or `benchmark` filters. The integration is ready for final CI verification.
