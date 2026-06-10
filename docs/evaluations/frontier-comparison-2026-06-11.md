---
status: completed
category: evaluation
audience: agent
last_updated: 2026-06-10
owner: ai-agent
---

# Frontier Comparison — Owlynn vs Raw DeepSeek V4

**Eval version:** `2026-06-11-comparison`  
**Run:** 2026-06-10 15:41:00  
**Profile:** cloud  
**Artifact:** `data/frontier_comparison_run_data.json`

## Executive summary

### Chat (equal footing — headline quality)

| Owlynn wins | Baseline wins | Ties |
|-------------|---------------|------|
| 1 | 0 | 0 |

### Capability (differentiation — task success)

| Owlynn wins | Baseline wins | Ties |
|-------------|---------------|------|
| 0 | 1 | 0 |

- Owlynn mean task_success (capability): **2.0**
- Baseline mean task_success (capability): **3.0**
- Position-flip rate (methodology health): **0.0**
- Tie rate: **0.0**

## Per-prompt results

| ID | Category | Winner | Flip | Rationale (order 1) |
|----|----------|--------|------|---------------------|
| C1 | chat | owlynn | False | Response A provides a more structured and detailed comparison, including a clear table of trade-offs and a concise verdi |
| K1 | capability | baseline | False | Response B attempts to provide specific mid-2026 developments with cited sources, directly addressing the user's request |

## Where Owlynn lost to raw chat

- No chat-category losses in this run.

## Where Owlynn won

- **C1** (Technical Explanation, chat)

## Capability differentiation

- **K1** — Owlynn task_success=2.0, Baseline task_success=3.0, tools=['web_search', 'deep_research']

## Prioritized improvements

1. Fix tool-call text leaks (`<tool_call>`) — judge penalizes clarity; blocks tool execution
2. Simple-path empty replies — hurts chat category vs baseline
3. Ensure ToolActivityCard / WS telemetry aligns with user-visible outcomes
4. Vision route: assert via task_category, not route badge
5. Memory gate: greetings should stay on simple path (M4-style negative control)

## Methodology & fairness

- Baseline: raw DeepSeek V4 **flash**, system prompt: "You are a helpful assistant."
- Owlynn: full system (router, memory, tools, RAG, same flash tier for cloud)
- Judge: DeepSeek V4 **pro**, blind A/B labels, dual-order (swap cancels position bias)
- Chat prompts scored head-to-head; capability prompts include task_success dimension

## Related

- [`docs/standards/EVALUATION.md`](../standards/EVALUATION.md)
- [`scripts/run_frontier_comparison_eval.py`](../../scripts/run_frontier_comparison_eval.py)
- Mechanical regression: [`scripts/run_local_frontier_eval.py`](../../scripts/run_local_frontier_eval.py)
