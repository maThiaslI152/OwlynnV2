# Local Cloud Model Resolution Fix (2026-06-23)

## Problem

The automated evaluation scripts (`scripts/run_extension_eval_automated.py` and others) attempt to use a local LM Studio instance as the "Cloud LLM" by setting `CLOUD_LLM_MODEL_NAME` to a local model like `gemma-4-e2b-heretic-uncensored-mlx`.

However, when running the `complex-cloud` fallback path in `src/agent/core/complex.py`, the agent was failing silently with a `Cloud unavailable — please try again or disable complex reasoning.` message.

Under the hood, this was caused by `_resolve_cloud_model_name()` in `src/agent/llm.py`. The resolution logic was ignoring both the environment variables and the user profile overrides whenever the default tier `"flash"` was requested. Instead, it was returning the hardcoded string `"deepseek-v4-flash"` from the fallback `config.get("models.cloud.tiers")`. 

Because `deepseek-v4-flash` was not downloaded or loaded in the local LM Studio instance, LM Studio rejected the request with a `400 Bad Request` (Model not found).

## Solution

1. **Fixed Model Resolution Order**: Modified `_resolve_cloud_model_name()` in `src/agent/llm.py` to correctly prioritize the environment and user profile overrides (`config.get("models.cloud.model_name")` and `profile.get("cloud_llm_model_name")`) over the hardcoded `tiers.get("flash")`.
2. **Improved Error Logging**: Updated the `except` block in `src/agent/core/complex.py` to log the actual `e.response.text` body when a `400 Bad Request` occurs, providing immediate visibility into model rejection errors.
3. **Frontend Test Waits**: Updated `scripts/run_local_frontier_eval.py` to wait for `.workspace-project-item` instead of the outdated `.connection-label`, fixing a `TimeoutError` caused by frontend DOM changes.

## Impact
Automated tests now correctly use the local model via LM Studio as the cloud target without raising `CloudUnavailableError` or generating false 400 Bad Requests. The EX6 track successfully executes the `get_active_browser_screenshot` tool with the local cloud mock.
