---
status: active
category: standards
last_updated: 2026-06-04
owner: ai-agent
---

# Local Frontier Evaluation Standard

> **Purpose:** Document the automated evaluation framework used to test the 3-tier local LLM router and deep tool usage constraints on an Apple Silicon M4 environment.

## Overview

The `run_local_frontier_eval.py` script replaces manual testing with an automated, browser-based evaluation. The suite is specifically designed to simulate heavy-duty "Frontier" user workloads while adhering to the hardware constraints (24GB RAM, thermal throttling) of a fanless M4 MacBook Air.

## Test Topics

The evaluation script runs 5 core topics to stress-test the local inference architecture:

1. **Router Precision (Simple):** Verifies the `0.8b` small model correctly intercepts greetings and bypasses the complex tools path.
2. **Router Precision (Complex):** Verifies requests like code reviews trigger the deterministic bypass to the `9b` medium model.
3. **Massive Context Ingestion:** Tests the system's ability to read and analyze massive local files without breaching the `16k` context limit.
4. **Sustained Multi-step Reasoning:** Requires the generation of complex, multi-file code (React + CSS) to test token budget tracking and cutoff continuation.
5. **Deep Tool Iteration:** Validates that the local model can correctly chain tools (e.g., `web_search` -> `write_workspace_file`) instead of just outputting prose.

## Evaluation Mechanism

Because cloud escalation (DeepSeek API) is often disabled, this evaluation does **not** rely on an LLM-as-a-judge approach. Instead, it relies on strict rule-based grading:

1. **DOM Orchestration Scraping:** Playwright scrapes the `.model-badge`, `.route-badge`, `.orchestration-gauge-value`, and `.tool-name` UI elements during execution.
2. **Rule-based Assertions:** The script checks the scraped data against expected routing paths and expected tools. For example, if a web search prompt does not invoke `web_search`, the turn fails.
3. **Turn Grading:** Each turn is graded out of 100 points (50 points for correct route, 50 points for correct tool invocation).

## Hardware Monitoring (TPS)

The script calculates an **Approximate Tokens Per Second (TPS)** value for each interaction.
- *Calculation:* `(Response Length / 4 chars per token) / Total Duration`
- *Purpose:* Over the 30+ minute evaluation window, developers must monitor the TPS score. A drastic drop in TPS during later turns indicates severe thermal throttling on the M4 chassis, indicating that the `max_tokens` or `context_window` configurations in `defaults.yaml` may need tightening.

## Running the Evaluation

**Prerequisites:**
- LM Studio must be running with both the `0.8b` and `9b` models loaded.
- The FastAPI backend (`python -m src.api.server`) and Vite frontend (`npm run dev`) must be running.

**Execution:**
```bash
python3 scripts/run_local_frontier_eval.py
```

**Artifacts Produced:**
- `data/frontier_eval_run_data.json`: Raw telemetry, latency, TPS, and automated grading scores.
- `assets/frontier_eval_screenshots/`: Step-by-step UI screenshots.
- **MANDATORY:** After every significant evaluation run, the results must be summarized and permanently recorded as a markdown file in the `docs/evaluations/` directory (e.g., `docs/evaluations/local-frontier-eval-YYYY-MM-DD.md`) and indexed in `docs/INDEX.md`.
