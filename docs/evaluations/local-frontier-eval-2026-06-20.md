# Local Frontier Eval Report — 2026-06-20

**Date:** 2026-06-20
**Score:** 1715/1900 (90.26%)
**Status:** Pipeline issues fixed, minor non-deterministic failures in F3/F4/F6.

## Overview
This evaluation run targeted the remaining test failures related to file processing and tool attribution, specifically in the `FF2.1` (Format DOCX) and `FF3.1` (Format XLSX) turns, which were previously scoring 85/100 due to hallucinated context and premature test completion.

## Key Fixes Landed

### 1. Eval Script Race Condition (`ws_idle` vs `is_graph_busy`)
**Symptom:** `FF3.1` (Format XLSX) executed `notebook_run` to parse a spreadsheet, but the eval script terminated the test before the agent could return the final output.
**Fix:** The test harness relied on a flaky DOM state (`is_graph_busy`). The logic in `wait_for_turn_complete` was updated to strictly trust the `ws_idle` WebSocket event.

### 2. DOCX Inline Context Extraction Cutoff
**Symptom:** `FF2.1` (Format DOCX) hallucinated the evaluation marker from an earlier PDF test.
**Fix:** The injection threshold for `.docx` and `.doc` files was reduced to 10 characters from 50, ensuring short evaluation markers are properly passed to the agent.

### 3. Cloud Brief Truncation
**Symptom:** Large documents attached to user messages were truncated by the `cloud_brief` gatekeeper.
**Fix:** Removed the 500-character limit on `last_user_message` in `cloud_brief.py`. Cache keys in `cloud_payload.py` were updated to invalidate when new messages arrive.

### 4. Frontend Silent Errors
**Symptom:** Unhandled promise rejections failed silently.
**Fix:** Replaced silent console warnings with `react-hot-toast` notifications.

## Analysis of Failures
The overall score of 90.26% reflects cascading failures caused by `F3.1` (Deep Tool Iteration) where DeepSeek-v4 split tool calls across two turns. The `new_chat_before` flags have been restored to isolate these tests in future runs. All core file ingestion tests (`FF1.1`, `FF2.1`, `FF3.1`, `FF4.1`) now achieve a perfect 100/100 score.
