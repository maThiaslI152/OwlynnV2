---
status: completed
category: evaluation
audience: agent
last_updated: 2026-06-19
owner: ai-agent
---

# Local Frontier Evaluation — 2026-06-19 (strict-cloud run)

**Script:** `scripts/run_local_frontier_eval.py`  
**Profile:** `cloud` (escalation ON, DeepSeek key valid, strict cloud mode ON)  
**Score:** **1680 / 1900 (88.42%)** — 19 turns, 0 skipped  
**Duration:** ~55 min  
**Artifact:** `data/frontier_eval_run_data.json`

## What changed in this eval

- **Strict Cloud Mode** — All local Qwen fallback mechanisms were disabled.
- **Dynamic Settings** — Clarifications were set to auto-approve, and scope/plan HITL prompts were disabled for automated evaluation.

---

## Turn Results

| Turn | Topic / Topic ID | Score | Route (Expected) | Route (Actual) | Key Notes / Failure Reasons |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **F1.1** | Router Precision (Simple) | **90/100** | `simple` | `simple` ✓ | Greeting bypassed via keyword bypass |
| **F2.1** | Router Precision (Complex) | **50/100** | `complex-cloud` | `simple` ✗ | **Failed:** Timed out. Scraped previous turn metadata due to Playwright sending race condition. |
| **F3.1** | Deep Tool Iteration | **100/100** | `complex-cloud` | `complex-cloud` ✓ | Executed `web_search` and `write_workspace_file` correctly |
| **F4.1** | Massive Context Ingestion | **100/100** | `complex-cloud` | `complex-cloud` ✓ | Read `docs/STATUS.md` and synthesized details |
| **F5.1** | Sustained Reasoning | **90/100** | `complex-cloud` | `complex-cloud` ✓ | Timed out on graph idle, but generated response correctly |
| **F6.1** | Memory Retention (conversation) | **100/100** | `complex-cloud` | `complex-cloud` ✓ | Recalled Tokyo weather details without web search |
| **F7.1** | Frontier Quality (flash tier) | **100/100** | `complex-cloud` | `complex-cloud` ✓ | proof sketch correct; timed out graph idle |
| **F7.2** | Frontier Pro tier path | **100/100** | `complex-cloud` | `complex-cloud` ✓ | Correctly ran on DeepSeek V4 Pro tier |
| **F8.1** | Router LLM Classifier | **100/100** | `complex-cloud` | `complex-cloud` ✓ | MiniCPM5 classifier routed open-ended prompt |
| **F9.1** | Vision Proxy (OCR) | **80/100** | `complex-cloud` | `complex-cloud` ✓ | **Failed:** Timed out. Local Qwen-VL model loading took too long. |
| **M1.1** | Memory Session Seed | **90/100** | `complex-cloud` | `complex-cloud` ✓ | Codeword `ZEBRA-42` successfully written |
| **M1.2** | Memory Session Recall | **100/100** | `complex-cloud` | `complex-cloud` ✓ | Recalled `ZEBRA-42` correctly (timed out graph idle) |
| **M2.1** | LTM Cross-Thread Recall | **100/100** | `complex-cloud` | `complex-cloud` ✓ | Recalled codeword in new chat thread via Qdrant/Mem0 |
| **M4.1** | Memory Retrieval Gate (neg) | **90/100** | `simple` | `simple` ✓ | Skip retrieval gate negative control passed |
| **W1.1** | File Watcher | **25/100** | `complex-cloud` | `simple` ✗ | **Failed:** Timed out. Scraped previous turn metadata due to Playwright sending race condition. |
| **FF1.1**| Format PDF | **100/100** | `complex-cloud` | `complex-cloud` ✓ | Read PDF marker successfully |
| **FF2.1**| Format DOCX | **85/100** | `complex-cloud` | `complex-cloud` ✓ | Read Word document marker |
| **FF3.1**| Format XLSX | **85/100** | `complex-cloud` | `complex-cloud` ✓ | Read Spreadsheet marker |
| **FF4.1**| Format CSV | **100/100** | `complex-cloud` | `complex-cloud` ✓ | Read CSV marker successfully |

---

## Findings & Architectural Gaps

### 1. Scorer Progress Logging Silence Bug
During 15-minute timeout windows (turns `F9.1`, `M1.2`, `W1.1`), the console and log files stayed completely silent instead of printing progress logs.
* **Analysis:** Inside the busy loop of `wait_for_turn_complete`, if the WebSocket goes idle (`ws_idle=True`) but no assistant message is seen yet, the script executes a `continue` statement. This skips the progress print block at the bottom of the loop, keeping it silent for 900 seconds.
* **Impact:** Harder to diagnose hangs or delays without console feedback.

### 2. Message Sending Race Condition
Both `F2.1` and `W1.1` timed out and scored poorly because the browser automation did not successfully click and submit the message.
* **Analysis:** Both occurred immediately after a `simple` greeting turn in a thread. Playwright fills the textarea and clicks `.composer-send` after a static 500ms sleep. If the React frontend lags during local model transitions, the click registers before state binding completes, causing React to treat the input as empty and ignore the submission.
* **Impact:** Creates false failures on complex turns because previous turn content is scraped.

### 3. Vision Proxy Model Load Timeouts
* **Analysis:** The Qwen3-VL 4B model (`qwen3-vl-4b-instruct-c_abliterated-v2-mlx`) is loaded on demand in LM Studio when an image is first dropped (`F9.1`). Swapping local models took longer than the timeout threshold.

---

## Recommended Follow-Ups

1. **Logging Silence Fix:** Update `wait_for_turn_complete` in `scripts/run_local_frontier_eval.py` to move the status log print block before the `continue` statement. Also, wrap Playwright's `page.evaluate()` calls inside the polling loop with `asyncio.wait_for(...)` to protect the runner from frozen browser environments.
2. **Robust Message Submission:** Modify `send_message()` in `scripts/run_local_frontier_eval.py` to wait for the submit button to become active, click it, and verify that the textarea value is cleared (or fallback to pressing `Enter`) to avoid React state-binding race conditions.
3. **Model Warmup Config:** Add `vision_proxy` to the `startup.preload` list in `src/config/defaults.yaml` during evaluation runs so that the local Qwen-VL model is loaded and warm beforehand.
