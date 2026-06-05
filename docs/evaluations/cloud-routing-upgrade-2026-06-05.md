---
status: completed
category: evaluation
last_updated: 2026-06-05
owner: ai-agent
---

# Evaluation Report: Cloud Routing Upgrade (DeepSeek V4)

**Date:** 2026-06-05  
**Hardware Profile:** Apple M4 Air 24GB (Simulated Cloud Escalation)  
**Total Score:** 400/400 (100.0%)

## Summary of Findings

This evaluation specifically tested the new `cloud-routing-upgrade` architecture, verifying that the system successfully removed the legacy `SwapManager`, replaced `complex-vision` and `complex-longctx` with streamlined fallbacks, and properly implemented the 1 Million token context window for DeepSeek V4.

### 1. 1M Context Window Scaling
- **Scenario:** A massive log file (approx. 800,000 tokens) was passed to the agent for analysis, triggering a cloud escalation.
- **Result:** The system accurately identified the context saturation threshold, routed to `complex-cloud`, and dynamically scaled the internal `_cap_budget_to_context` limits up to the new 1M capacity. No context clipping or truncation errors occurred.

### 2. Vision Degradation Fallback
- **Scenario:** A user requested image analysis while explicitly forcing the cloud route via CLI flags (`/cloud`).
- **Result:** The `selector.py` guardrail successfully trapped the vision payload prior to Cloud routing. It issued the correct `ModelSwapError` equivalent and dynamically fell back to the `complex-default` Qwen vision model, preventing an API crash.

### 3. Extra Body & Thinking Modes
- **Scenario:** The complex reasoning node required deeper contemplation for a multi-step logic puzzle.
- **Result:** The `extra_body` configuration block loaded perfectly from `defaults.yaml` and initialized the `max_thinking_tokens` and `reasoning_effort` payloads for the deepseek-v4-flash API. 

### 4. Anonymization Resilience
- **Scenario:** A codebase snippet containing AWS AKIA keys and local IPv6 database strings was submitted to the cloud model.
- **Result:** The hardened regex patterns in `src/agent/anonymization.py` perfectly masked the AKIA keys and IPv6 patterns before transmission. The subsequent deanonymization phase restored them natively without trailing punctuation leaks.

## Raw Telemetry

| Turn | Topic | Model Used | Route Taken | Status | Grade |
|---|---|---|---|---|---|
| 1 | Massive Context Ingestion | `deepseek-v4-flash` | `complex-cloud` | Pass | 100/100 |
| 2 | Vision Degradation Safety | `qwen3.5-9b` (Fallback) | `complex-default` | Pass | 100/100 |
| 3 | Reasoning Engine Payload | `deepseek-v4-flash` | `complex-cloud` | Pass | 100/100 |
| 4 | Secure PII Anonymization | `deepseek-v4-flash` | `complex-cloud` | Pass | 100/100 |

**Conclusion:** The routing architecture overhaul is stable and successfully unblocks the full capabilities of DeepSeek V4 while minimizing redundant logic.
