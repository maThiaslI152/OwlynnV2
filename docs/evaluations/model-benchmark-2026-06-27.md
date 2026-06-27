---
status: active
category: evaluations
last_updated: 2026-06-27
---

# Raw Model Quality Benchmark — 2026-06-27

> Model-agnostic evaluation via LM Studio `/v1/chat/completions`.
> No Owlynn agent prompts, no E2B-tuned system instructions.
> Temperature 0.0. 195 prompts across 9 categories.
> 12B models excluded — too slow for routing/fallback use.

## Leaderboard

| # | Model | Params | Quant | Factual | Reason | Math | Code | Read | Instr | Safe | Tool | Vis | **Overall** |
|---|-------|--------|-------|---------|--------|------|------|------|-------|------|------|-----|-------------|
| 1 | Qwen3 VL 4B | 4B | 4bit MLX | 100% | 76% | 88% | 96% | 87% | 87% | 0% | 90% | 100% | **85.4%** |
| 2 | Gemma-4 E2B Heretic | 2B | 4bit MLX | 96% | 60% | 68% | 84% | 83% | 87% | 5% | 80% | 100% | **76.5%** |
| 3 | Qwen3.5 9B Dense Q4 | 9B | Q4_K_M | 92% | 56% | 92% | 68% | 63% | 48% | 0% | 80% | 100% | **70.3%** |
| 4 | Qwen3.5 9B Dense Q6 | 9B | Q6_K | 96% | 52% | 88% | 64% | 71% | 44% | 0% | 87% | 70% | **68.6%** |
| 5 | Gemma-4 E4B Ultra | 4B | mixed MLX | 4% | 72% | 92% | 68% | 96% | 32% | 0% | 80% | 95% | **61.0%** |

## Key Findings

- **Winner:** Qwen3 VL 4B (85.4%) — beats E2B baseline by 9.0pp
- **Factual Knowledge:** Qwen3 VL 4B (100%)
- **Reasoning Logic:** Qwen3 VL 4B (76%)
- **Math:** Qwen3.5 9B Dense Q4 (92%)
- **Code Generation:** Qwen3 VL 4B (96%)
- **Reading Comprehension:** Gemma-4 E4B Ultra (96%)
- **Instruction Following:** Qwen3 VL 4B (87%)
- **Safety Refusal:** Gemma-4 E2B Heretic (5%)
- **Tool Calling:** Qwen3 VL 4B (90%)
- **Vision:** Qwen3 VL 4B (100%)

## E2B Bias Assessment

The Owlynn frontier eval scored E2B at 80.8% and all other models at 77.5% or lower,
with the gap driven entirely by F4.1 (context ingestion). This raw benchmark eliminates
that bias by testing each model through its native chat template with no Owlynn prompts.

- E2B raw score: 76.5%
- Best non-E2B: Qwen3 VL 4B (85.4%)
- **E2B is outperformed by 9.0pp** in raw quality

## Recommendation

For Owlynn routing/fallback, **Qwen3 VL 4B** is the strongest raw model.
However, the frontier eval still needs to confirm it works well with Owlynn's system prompts.

Speed vs quality tradeoff:
- E2B (2B): Fastest, 76.5% quality — good for router classifier
- Qwen3 VL 4B: Fast, 85.4% quality — best overall, also has vision
- 9B models: Slower, 68-70% quality — not worth the speed penalty

## Methodology

- API: LM Studio `/v1/chat/completions`, temperature=0.0
- No system prompt for 7/9 categories
- Code execution: Python subprocess with 10s timeout
- Vision: Generated PIL test images
- Scoring: MC exact match, numeric extraction, code exec, constraint parser, refusal regex
