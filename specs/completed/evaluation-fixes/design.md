# Design: Evaluation Fixes

## Overview
This change addresses four separate bugs discovered during the June 3rd evaluation run.

## Proposed Changes

### 1. Scope Heuristics (`src/agent/hitl/scope_heuristics.py`)
- Add a list of `_CREATIVE_SIGNALS` (e.g., "story", "poem", "essay", "review", "explain", "why").
- Update the `needs_clarification` function to return `False` immediately if any of these signals are present in the prompt.

### 2. SearXNG Backend (`src/tools/web_search_enhanced.py`)
- The `httpx.AsyncClient` initialization in `searxng_search` and `searxng_available` will include HTTP headers: `{"User-Agent": "Owlynn/1.0", "Accept": "application/json"}` to bypass basic bot-blocking at the SearXNG proxy layer.

### 3. Backend Concurrency (`src/api/server.py`)
- In `GraphSession.start_run`, instead of returning immediately if `self.is_running` is True, we will use an `asyncio.Lock()` to serialize execution.
- We will replace `if self.is_running: return` with `async with self.run_lock:`, allowing multiple rapid websocket events (like a sequence of `user_input` and `tool_approval`) to queue gracefully instead of being dropped.

### 4. Browser Eval Timeout (`scripts/run_browser_eval.py`)
- Update `wait_for_response` timeout from `150` to `300` seconds to allow longer generation times for the medium LLM.

## Risks
- Serializing `GraphSession` runs ensures no dropped messages, but if a graph run legitimately hangs, subsequent requests on the same thread will pile up. This is acceptable as it preserves consistency.
