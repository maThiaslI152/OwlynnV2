# Changelog

## 2026-06-04 - Architecture Refactoring & Stability Optimizations

- **Feature / Fix**: Mitigated the "One-Turn Lag" UI defect by implementing robust `correlation_id` injection in WebSocket messaging.
- **Fix**: Adjusted Mem0 API calls `search()` signature to correctly nest `user_id` inside `filters` dictionary, restoring context memory functionality.
- **Fix**: Blocked `_preload_llms` from racing with `lifespan` initialization, which previously hung application start and failed readiness probes.
- **Performance**: Caped M4 Air token context limits (8k/16k) and memory retrieval size (50 facts) in `defaults.yaml` and `settings.py` to prevent thermal throttling on fanless chassis.
- **Refactor**: Broadened `_REFACTOR_SIGNALS` in `scope_heuristics.py` to include `"improved"` so that standard code enhancement tasks don't mistakenly trigger heavy architectural HITL interventions.
- **Architecture**: Decomposed the monolithic `complex.py` (1.2k lines) node by cleanly carving out `fallback` generation and `formatter` string operations into a new `complex_utils/` utility folder.
- **Architecture**: Dismantled the 2.3k line `server.py` monolith using `libcst`. Separated functionality into domain-specific FastApi routers: `profile.py`, `settings.py`, `memory.py`, `project.py`, `files.py`, `openai.py`, and `ws/handler.py`. Server module successfully imports cleanly with no circular dependencies.
