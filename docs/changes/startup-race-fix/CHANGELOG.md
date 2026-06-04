# Changelog: Startup Race Fix & Settings Consolidation

> **change:** `startup-race-fix`
> **last_updated:** 2026-06-04

---

## [Unreleased]

- **Fix (server):** Await the background `_preload_llms()` coroutine in the lifespan context manager. This blocks uvicorn from listening/serving client requests on port 8000 until LM Studio preloading and warmup are completed, resolving the startup race condition.
- **Fix (server):** Populate default LLM configuration settings and flatten variants structure in the `/api/unified-settings` endpoint using values from the centralized config loader when user profile overrides are not present. This resolves frontend config rendering bugs and ensures test coverage compatibility.


