## 2026-07-12 — Performance and Stability Improvements

### What
- Refactored `is_on_battery` to `async` in `src/api/power_monitor.py` to prevent event loop blocking in Eco-Mode.
- Lowered `complex.recursion_limit` from 100 to 15 in `src/api/ws/handler.py`.
- Added length constraints to the `learning` (Study) style in `src/agent/response_styles.py`.
- Forcefully close unclosed markdown blocks if a cutoff occurs in `src/agent/core/complex.py`.

### Why
These fixes address various runtime stability and performance issues:
- A synchronous `is_on_battery` check was blocking the main event loop, causing latency spikes when Eco-Mode transitions happened.
- The `recursion_limit` was overly permissive at 100, which allowed buggy agents to waste resources before timing out; 15 is a safer cap.
- Length constraints on the `learning` style prevent overly verbose outputs in Study mode.
- Forcefully closing markdown blocks prevents UI rendering glitches when the LLM gets cut off abruptly mid-block.

### Files
- `src/api/power_monitor.py`
- `src/api/ws/handler.py`
- `src/agent/response_styles.py`
- `src/agent/core/complex.py`
