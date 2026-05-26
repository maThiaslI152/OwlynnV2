# Changelog: evaluation-fixes

## 2026-06-03 - Implemented Fixes from Conversation Evaluation

- **Feature (protocol/server):** Implemented client-server Message Correlation IDs in the WebSocket protocol. The frontend composer is locked during graph execution, and both the browser client and Playwright monitor wait specifically for response messages containing the matching correlation ID, completely resolving the "One-Turn Lag" concurrency bug.
- **Fix (hitl):** Added `_CREATIVE_SIGNALS` to bypass scope clarification for writing tasks in `src/agent/hitl/scope_heuristics.py` and improved substring matches.
- **Fix (tools):** Added `User-Agent` and `Accept` headers to SearXNG `httpx.AsyncClient` instances in `src/tools/web_search_enhanced.py` to resolve 403 Forbidden errors.
- **Fix (server):** Wrapped `GraphSession._execute` in an `asyncio.Lock()` to correctly queue concurrent messages instead of dropping them, and fixed recursive `_send_ws` call issues.
- **Fix (eval):** Rewrote Playwright evaluation wait logic in `scripts/run_browser_eval.py` to wait for composer textarea enablement (lock release) rather than a naive timer, and updated screenshot captures.
- **Document (eval):** Created the Owlynn Conversation Evaluation Report (v3) at `docs/evaluations/owlynn-conversation-2026-06-03-v3.md` showcasing 100% correctness and synchronization success under fanless Apple Silicon thermal throttling conditions.

