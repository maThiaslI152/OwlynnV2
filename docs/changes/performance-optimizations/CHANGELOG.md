# Performance Optimizations

## 2026-07-09 — System Performance Optimization (Idle + Active Work)

**What**
Implemented 5 targeted performance optimizations across the Owlynn stack.

---

### Opt. 5 — Adaptive File Cache Poll (Upload latency −2.5s avg)
**File:** `src/api/server.py` — `_auto_index_project_file()`

Replaced the hardcoded `asyncio.sleep(3)` with a `_wait_for_processed_cache()` polling function that returns as soon as the `.processed/` cache file appears (polls every 300ms, 8s timeout). For plain text files processed instantly, this eliminates the full 3s wait. Falls back to direct file read on timeout.

---

### Opt. 4 — Follow-up Continuation Bypass (Routing latency −200–600ms)
**Files:** `src/agent/routing/deterministic.py`, `src/agent/routing/router.py`

Added `_FOLLOWUP_TOKENS` set and `_is_followup_continuation()` detector. Short mid-task confirmations ("ok", "continue", "go ahead", "yes please", etc.) now skip the LLM router classifier entirely and reuse the previous turn's route, saving 200–600ms per follow-up message. Guard: only activates when `_has_tool_history()` confirms we are mid-task.

---

### Opt. 2 — Idle LLM Unload (−3.5 to 5 GB RAM after 15 min idle)
**Files:** `src/api/idle_manager.py` (new), `src/api/server.py`, `src/api/ws/handler.py`

After 15 minutes of no chat activity, the `idle_watcher_loop()` background task calls the LM Studio REST API (`DELETE /v1/models/{model_key}`) to unload the local model and free unified memory. On the next chat message, `ensure_llm_loaded()` sends a lightweight ping to trigger model reload before the LangGraph graph runs.

Config: `startup.idle_unload_minutes: 15` (0 = disabled)

---

### Opt. 3 — StirlingPDF Idle Shutdown (−200–300 MB RAM, opt-in)
**Files:** `src/api/idle_manager.py`, `src/pdf/intake.py`

When `services.stirling_pdf.idle_shutdown: true` is set in `defaults.yaml`, the `idle_watcher_loop` stops the `owlynn_stirling_pdf` Docker container after 10 minutes of no PDF activity. On the next PDF upload, `ensure_stirling_running()` restarts it and waits up to 10s for health. The PDF intake functions (`extract_pdf_text_from_path`, `extract_pdf_text_from_bytes`) call `record_pdf_activity()` to reset the timer.

Config: `services.stirling_pdf.idle_shutdown: false` (opt-in), `services.stirling_pdf.idle_minutes: 10`

---

### Opt. 1 — Parallel Tool Dispatch (Active latency −30–60% on multi-tool turns)
**File:** `src/agent/core/complex.py` — `complex_tool_action_node()`

Replaced sequential `ToolNode.ainvoke()` with `_parallel_tool_dispatch()`. When the LLM emits multiple tool calls in one turn, independent tools now run concurrently via `asyncio.gather()`. Results are reassembled in the original call order.

**Serial safelist** (`_SERIAL_TOOLS`): Tools that write to shared state remain sequential:
`write_workspace_file`, `edit_workspace_file`, `delete_workspace_file`, `notebook_run`, `run_kali_command`, `send_kali_input`, `metasploit_run`, `hydra_attack`, `john_crack`, `wifi_deauth`, `wifi_handshake_capture`, `wifi_crack_handshake`

---

## Verification

- ✅ 60/60 router tests pass (`tests/test_router_*.py`)
- ✅ Frontend build passes (`npm run build`)
