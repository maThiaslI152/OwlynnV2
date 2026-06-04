# Tasks: Evaluation Fixes

## 1. Fix Scope Clarification (maps_to: AC-1)
- `files`: `src/agent/hitl/scope_heuristics.py`
- Define `_CREATIVE_SIGNALS = {"story", "poem", "essay", "review", "explain", "why", "describe"}`.
- Update `needs_clarification` to return `False, []` early if any of the creative signals are in the prompt words.

## 2. Fix SearXNG 403 Forbidden (maps_to: AC-2)
- `files`: `src/tools/web_search_enhanced.py`
- Add `headers={"User-Agent": "Owlynn/1.0", "Accept": "application/json"}` to `httpx.AsyncClient` in both `searxng_search` and `searxng_available`.

## 3. Fix Backend Concurrency (One-Turn Lag) (maps_to: AC-3)
- `files`: `src/api/server.py`
- Add `self.run_lock = asyncio.Lock()` to `GraphSession.__init__`.
- In `GraphSession.start_run`, replace `if self.is_running: return` with `async with self.run_lock:`. Use a try/finally block around the internal state execution logic to ensure lock safety.

## 4. Fix Playwright Timeout (maps_to: AC-4)
- `files`: `scripts/run_browser_eval.py`
- Modify `wait_for_response` default timeout argument: `timeout_s: int = 300` (up from 150).

## 5. Verification steps
1. Run `python -m pytest tests/` or manually verify the search and scope nodes.
2. Verify SearXNG is reachable without 403 errors by running the search tool manually.
3. Verify no dropped messages by clicking buttons rapidly in the UI.
