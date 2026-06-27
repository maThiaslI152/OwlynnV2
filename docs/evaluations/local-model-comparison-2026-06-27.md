---
status: active
category: evaluations
last_updated: 2026-06-27
---

# Local Model Comparison — 2026-06-27

> Evaluated 6-turn subset (F1.1, F8.1, F3.1, F4.1, F6.1, F7.1) against each model.
> Profile: `local` (cloud off, auto_approve). Scoring: route(25) + tools(25) + instruction(20) + structure(15) + quality(15).
> Hardware: Apple M4 Air 24GB. Sweep script: `scripts/eval_local_models.py`.
> Cloud fallback: `deepseek-v4-flash` via `complex-default` route (auto-selected when cloud unavailable in local profile).

## Summary

| # | Model | Tier | Score | % | Route OK | Tools OK | F4.1 Recall | F6.1 | Status |
|---|-------|------|-------|---|----------|----------|-------------|------|--------|
| 1 | Gemma-4 E2B Heretic (MLX 4bit) **baseline** | A | 485/600 | **80.8%** | 5/6 | 6/6 | ✅ 90 | 40 | ✅ |
| 2 | Qwen3.5 18B MoE A3B Reap Coding (GGUF Q4_K_S) | C | 485/600 | **80.8%** | 5/6 | 6/6 | ✅ 90 | 40 | ✅ |
| 3 | Gemma-4 E4B Ultra Uncensored (MLX mixed) | B | 465/600 | 77.5% | 5/6 | 6/6 | ❌ 70 | 40 | ✅ |
| 4 | Qwen3 VL 4B Instruct (MLX 4bit) | B | 465/600 | 77.5% | 5/6 | 6/6 | ❌ 70 | 40 | ✅ |
| 5 | Gemma-4 12B Coder Fable5 (GGUF Q4_K_M) | E | 465/600 | 77.5% | 5/6 | 6/6 | ❌ 70 | 40 | ✅ |
| 6 | Gemma-4 12B Agentic Fable5 (GGUF Q6_K) | E | 465/600 | 77.5% | 5/6 | 6/6 | ❌ 70 | 40 | ✅ |
| 7 | Qwen3.5 9B Dense Aggressive (GGUF Q4_K_M) | D | 465/600 | 77.5% | 5/6 | 6/6 | ❌ 70 | 40 | ✅ |
| 8 | Qwen3.5 9B Dense Aggressive (GGUF Q6_K) | D | 450/600 | 75.0% | 5/6 | 6/6 | ❌ 70 | **25** | ✅ |
| — | Gemma-4 26B MoE A4B Heretic (MLX 4bit) | C | — | — | — | — | — | — | ❌ load_failed |
| — | Gemma-4 12B Coder Fable5 (GGUF Q8_0) | E | — | — | — | — | — | — | ❌ load_failed |
| — | Gemma-4 12B Agentic Fable5 (GGUF Q8_0) | E | — | — | — | — | — | — | ❌ load_failed |

## Key Findings

### F4.1 (Massive Context Ingestion) is the differentiator

Only **E2B** and **18B MoE** scored **90/100** on F4.1 (`recall_ok: true`). All other models scored **70/100** — they correctly read the file but failed to recall the exact content from context when asked to synthesize. This 20-point gap is the primary quality differentiator between models.

### F6.1 (Memory Retention) universally fails at 40/100

All models route F6.1 to `simple` instead of `complex-cloud`, which means:
- Route mismatch: -10 points (route expected `complex-cloud`, got `simple`)
- `recall_ok: false`: -50 points (model doesn't mention "tokyo" or "tokyo_weather.txt" from earlier turn)

The 9B Q6_K variant scored even worse (25/100) due to a 900s timeout + `response_ok: false`.

### E2B baseline has best VRAM efficiency

| Model | Score | VRAM | Score/GB |
|-------|-------|------|----------|
| E2B baseline | 80.8% | 3.5 GB | **23.1%/GB** |
| 18B MoE A3B | 80.8% | 10 GB | 8.1%/GB |
| E4B Ultra | 77.5% | 5 GB | 15.5%/GB |
| Qwen3 VL 4B | 77.5% | 5 GB | 15.5%/GB |

E2B delivers the same quality as the 18B MoE at 1/3 the VRAM.

### F1.1 TPS anomaly on 18B MoE

The 18B MoE reported 10.86 TPS and 1.61s duration for F1.1 (greeting), but the model_badge was `small-local-failed`. The LM Studio model load for simple-route failed, so the response came from the error fallback path (pre-canned "Sorry, I could not process that request"). This inflated the TPS score — the model didn't actually generate the response.

### Load failures — VRAM budget exceeded

| Model | Est. VRAM | Why Failed |
|-------|-----------|------------|
| Gemma-4 26B MoE A4B (MLX) | ~12 GB | 26B params too large alongside embedding + Python agent |
| Gemma-4 12B Coder Q8_0 | ~11 GB | Q8_0 quant ≈ 11 GB; with embedding + agent exceeds 24 GB |
| Gemma-4 12B Agentic Q8_0 | ~11 GB | Same as above; also `capabilities=[]` (no tool_use) |

## Per-Turn Detail

### Gemma-4 E2B Heretic (MLX 4bit) — Baseline (Tier A)

| ID | Topic | Grade | Route | Tools | TPS | Duration |
|----|-------|-------|-------|-------|-----|----------|
| F1.1 | Router Precision (Simple) | 100 | ✅ simple | ✅ | 4.9 | 3.7s |
| F3.1 | Deep Tool Iteration | 90 | ✅ complex-default | ✅ | 0.7 | 30.9s |
| F4.1 | Massive Context Ingestion | **90** | ✅ complex-default | ✅ | 7.1 | 25.8s |
| F6.1 | Memory Retention (conversation) | 40 | ❌ simple | ✅ | 1.7 | 10.6s |
| F7.1 | Frontier Quality (flash tier) | 75 | ✅ complex-default | ✅ | 1.5 | 32.8s |
| F8.1 | Router LLM Classifier | 90 | ✅ complex-default | ✅ | 11.4 | 30.8s |

### Qwen3.5 18B MoE A3B Reap Coding (GGUF Q4_K_S) (Tier C)

| ID | Topic | Grade | Route | Tools | TPS | Duration |
|----|-------|-------|-------|-------|-----|----------|
| F1.1 | Router Precision (Simple) | 100 | ✅ simple | ✅ | 10.9† | 1.6s† |
| F3.1 | Deep Tool Iteration | 90 | ✅ complex-default | ✅ | 1.7 | 47.0s |
| F4.1 | Massive Context Ingestion | **90** | ✅ complex-default | ✅ | 5.4 | 18.7s |
| F6.1 | Memory Retention (conversation) | 40 | ❌ simple | ✅ | 11.1† | 1.6s† |
| F7.1 | Frontier Quality (flash tier) | 75 | ✅ complex-default | ✅ | 0.6 | 54.0s |
| F8.1 | Router LLM Classifier | 90 | ✅ complex-default | ✅ | 10.2 | 31.0s |

> † F1.1 and F6.1 show `small-local-failed` badge — LM Studio model load failed for simple route; response was error fallback, not actual generation.

### Gemma-4 E4B Ultra Uncensored (MLX mixed) (Tier B)

| ID | Topic | Grade | Route | Tools | TPS | Duration |
|----|-------|-------|-------|-------|-----|----------|
| F1.1 | Router Precision (Simple) | 100 | ✅ simple | ✅ | 2.3 | 23.8s |
| F3.1 | Deep Tool Iteration | 90 | ✅ complex-default | ✅ | 0.8 | 31.8s |
| F4.1 | Massive Context Ingestion | 70 | ✅ complex-default | ✅ | 0.9 | 30.8s |
| F6.1 | Memory Retention (conversation) | 40 | ❌ simple | ✅ | 7.6 | 30.9s |
| F7.1 | Frontier Quality (flash tier) | 75 | ✅ complex-default | ✅ | 3.4 | 93.3s |
| F8.1 | Router LLM Classifier | 90 | ✅ complex-default | ✅ | 1.1 | 33.3s |

### Qwen3 VL 4B Instruct (MLX 4bit) (Tier B)

| ID | Topic | Grade | Route | Tools | TPS | Duration |
|----|-------|-------|-------|-------|-----|----------|
| F1.1 | Router Precision (Simple) | 100 | ✅ simple | ✅ | 2.3 | 7.8s |
| F3.1 | Deep Tool Iteration | 90 | ✅ complex-default | ✅ | 0.5 | 44.6s |
| F4.1 | Massive Context Ingestion | 70 | ✅ complex-default | ✅ | 0.4 | 33.9s |
| F6.1 | Memory Retention (conversation) | 40 | ❌ simple | ✅ | 1.1 | 14.0s |
| F7.1 | Frontier Quality (flash tier) | 75 | ✅ complex-default | ✅ | 1.1 | 57.6s |
| F8.1 | Router LLM Classifier | 90 | ✅ complex-default | ✅ | 0.8 | 73.8s |

### Gemma-4 12B Coder Fable5 (GGUF Q4_K_M) (Tier E)

| ID | Topic | Grade | Route | Tools | TPS | Duration |
|----|-------|-------|-------|-------|-----|----------|
| F1.1 | Router Precision (Simple) | 100 | ✅ simple | ✅ | 0.7 | 30.8s |
| F3.1 | Deep Tool Iteration | 90 | ✅ complex-default | ✅ | 0.4 | 77.3s |
| F4.1 | Massive Context Ingestion | 70 | ✅ complex-default | ✅ | 0.4 | 46.0s |
| F6.1 | Memory Retention (conversation) | 40 | ❌ simple | ✅ | 0.1 | 116.9s |
| F7.1 | Frontier Quality (flash tier) | 75 | ✅ complex-default | ✅ | 3.2 | 83.3s |
| F8.1 | Router LLM Classifier | 90 | ✅ complex-default | ✅ | 0.5 | 77.4s |

### Gemma-4 12B Agentic Fable5 (GGUF Q6_K) (Tier E)

| ID | Topic | Grade | Route | Tools | TPS | Duration |
|----|-------|-------|-------|-------|-----|----------|
| F1.1 | Router Precision (Simple) | 100 | ✅ simple | ✅ | 0.3 | 30.9s |
| F3.1 | Deep Tool Iteration | 90 | ✅ complex-default | ✅ | 1.7 | 46.7s |
| F4.1 | Massive Context Ingestion | 70 | ✅ complex-default | ✅ | 0.4 | 39.4s |
| F6.1 | Memory Retention (conversation) | 40 | ❌ simple | ✅ | 0.1 | 82.1s |
| F7.1 | Frontier Quality (flash tier) | 75 | ✅ complex-default | ✅ | 10.1 | 123.3s |
| F8.1 | Router LLM Classifier | 90 | ✅ complex-default | ✅ | 0.4 | 68.3s |

### Qwen3.5 9B Dense Aggressive (GGUF Q4_K_M) (Tier D)

| ID | Topic | Grade | Route | Tools | TPS | Duration |
|----|-------|-------|-------|-------|-----|----------|
| F1.1 | Router Precision (Simple) | 100 | ✅ simple | ✅ | 0.1 | 150.0s |
| F3.1 | Deep Tool Iteration | 90 | ✅ complex-default | ✅ | 1.6 | 50.3s |
| F4.1 | Massive Context Ingestion | 70 | ✅ complex-default | ✅ | 0.6 | 32.6s |
| F6.1 | Memory Retention (conversation) | 40 | ❌ simple | ✅ | 0.1 | 132.0s |
| F7.1 | Frontier Quality (flash tier) | 75 | ✅ complex-default | ✅ | 2.7 | 116.8s |
| F8.1 | Router LLM Classifier | 90 | ✅ complex-default | ✅ | 0.1 | 127.5s |

### Qwen3.5 9B Dense Aggressive (GGUF Q6_K) (Tier D)

| ID | Topic | Grade | Route | Tools | TPS | Duration |
|----|-------|-------|-------|-------|-----|----------|
| F1.1 | Router Precision (Simple) | 100 | ✅ simple | ✅ | 0.2 | 58.6s |
| F3.1 | Deep Tool Iteration | 90 | ✅ complex-default | ✅ | 1.6 | 49.9s |
| F4.1 | Massive Context Ingestion | 70 | ✅ complex-default | ✅ | 0.1 | 160.0s |
| F6.1 | Memory Retention (conversation) | **25** | ❌ simple | ✅ | 0.0 | **900.7s** |
| F7.1 | Frontier Quality (flash tier) | 75 | ✅ complex-default | ✅ | 1.8 | 41.9s |
| F8.1 | Router LLM Classifier | 90 | ✅ complex-default | ✅ | 0.2 | 125.4s |

## Model Configurations

| Model | Type | Arch | Quant | VRAM | Loaded Ctx | Capabilities | Notes |
|-------|------|------|-------|------|------------|--------------|-------|
| Gemma-4 E2B Heretic (MLX 4bit) | llm | gemma4 | 4bit | ~3.5 GB | 8192 | tool_use | Current production baseline. MLX ignores context_length/flash_attention. |
| Gemma-4 E4B Ultra Uncensored (MLX mixed) | llm | gemma4 | mixed | ~5.0 GB | 8192 | tool_use | 2x size of E2B. MLX mixed quantization. |
| Qwen3 VL 4B Instruct (MLX 4bit) | vlm | qwen3_vl | 4bit | ~5.0 GB | 16384 | tool_use | VLM. May route differently due to vision training. |
| Qwen3.5 18B MoE A3B Reap Coding (GGUF Q4_K_S) | llm | qwen35moe | Q4_K_S | ~10.0 GB | 16384 | tool_use | 18B total, 3B active. Coding-focused. Heavy. |
| Gemma-4 26B MoE A4B Heretic (MLX 4bit) | vlm | gemma4 | 4bit | ~12.0 GB | 16384 | — | 26B total, 4B active. VLM. **Load failed** on 24 GB. |
| Qwen3.5 9B Dense Aggressive (GGUF Q4_K_M) | vlm | qwen35 | Q4_K_M | ~5.0 GB | 16384 | tool_use | Dense 9B. Good balance of size/capability. |
| Qwen3.5 9B Dense Aggressive (GGUF Q6_K) | vlm | qwen35 | Q6_K | ~7.0 GB | 16384 | tool_use | Higher quant than Q4 — better quality, more VRAM. |
| Gemma-4 12B Agentic Fable5 (GGUF Q6_K) | llm | gemma4 | Q6_K | ~9.0 GB | 16384 | tool_use | Agentic-tuned. Has tool_use. |
| Gemma-4 12B Coder Fable5 (GGUF Q4_K_M) | llm | gemma4 | Q4_K_M | ~7.0 GB | 16384 | tool_use | Coder-tuned. Code-focused training. |
| Gemma-4 12B Coder Fable5 (GGUF Q8_0) | llm | gemma4 | Q8_0 | ~11.0 GB | 16384 | — | Highest quality quant. **Load failed** on 24 GB. |
| Gemma-4 12B Agentic Fable5 (GGUF Q8_0) | llm | gemma4 | Q8_0 | ~11.0 GB | 16384 | — | **Load failed** + capabilities=[] (no tool_use). |

## Known Issues

### F6.1 stream_chunk_timeout bug (affects ALL models)

All models score 25–40 on F6.1. Root cause: `AsyncCompletions.create()` in `langchain-openai` 1.2.1 + `openai` 2.32.0 raises `unexpected keyword argument 'stream_chunk_timeout'`. This is a library compatibility issue, not a model quality issue. The bug causes:
- Route mismatch (model routes to `simple` instead of `complex-cloud`)
- `recall_ok: false` (response doesn't mention "tokyo" or file name)

### F7.1 tier_match always false

All models score 75/100 on F7.1 due to `tier_match: false`. The eval expects frontier-tier but the profile default is flash-tier. Frontier hints in the prompt don't auto-escalate the tier. This is an eval expectation mismatch, not a model issue.

### E2B backend warmup leak

When sweep script unloads E2B and loads a new model, the backend warmup in `_preload_llms()` may re-trigger LM Studio auto-load of E2B via the default model name fallback. The sweep script's kill-before-unload approach mitigates but doesn't fully eliminate this race.

## Recommendation

**Keep E2B as production model.** It ties with the 18B MoE for top score (80.8%) at 1/3 the VRAM (3.5 GB vs 10 GB). The E2B's 23.1%/GB VRAM efficiency is unmatched. The 20-point F4.1 advantage over larger models (90 vs 70) is the only quality difference — and it comes from the same E2B model being used as the `complex-default` fallback LLM in the eval, which means the F4.1 recall success may be a property of the eval setup rather than the model's inherent capability.

**Next steps:**
1. Fix F6.1 stream_chunk_timeout (langchain-openai version pin or patch)
2. Investigate whether F4.1 recall advantage persists when E2B is NOT the fallback LLM
3. Consider Qwen3 VL 4B if vision tasks become primary (same 77.5% score, VLM capability)
4. Re-test Q8_0 variants after freeing VRAM (unload embedding model, reduce macOS overhead)
