# Model Quirks & Routing Setup

**Date:** June 2026  
**Context:** Migration to LangChain/LangGraph patterns (`migrate-deepseekv4`)  

This document details the local LLM routing stack, model-specific quirks, and the reasoning behind our configuration choices.

---

## 1. The Router: MiniCPM5-1B

The project uses `openbmb/MiniCPM5-1B` (via MLX 8-bit `mlx-community/MiniCPM5-1B-8bit`) as the small router model. It replaces the previous `qwen3.5-0.8b`.

### Why MiniCPM5-1B?
- **Standard Llama Architecture**: Works seamlessly with LM Studio auto-detection without requiring custom kernels.
- **SOTA Performance**: Extremely capable 1B parameter model that beats larger models on agentic/tool-calling benchmarks.
- **Clean "No-Think" mode**: Unlike `qwen3.5-0.8b`, which frequently leaks `reasoning_content` and consumes our token budget before outputting JSON, MiniCPM5 outputs direct answers when its thinking mode is disabled. This allowed us to shrink `router_llm.max_tokens` from 512 to 256.

### Known Quirks & Safety Nets
- **Hybrid-Think Leakage**: Even with `enable_thinking: false` passed via `chat_template_kwargs`, MiniCPM5 will sometimes spontaneously enter "think mode" if not explicitly constrained by the prompt or if running via a local inference engine that overrides API parameters.
- **Why we didn't rewrite the parser**: Instead of trying to force LM Studio Jinja templates to drop the thinking blocks (which is fragile across different versions), we kept the existing regex extraction logic in `parse_routing()` and added a safety strip: `re.sub(r"<think>.*?</think>", "", content)`. This guarantees clean JSON extraction even if the model outputs a 4-second internal monologue.

---

## 2. The Worker: Qwen3.5-9B-Uncensored (HauhauCS Aggressive)

The `medium` model is used for complex local execution. We use the `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive` (Q6_K) variant.

### Configuration (`defaults.yaml`)
- **Temperature**: `0.7`
- **Top-P**: `0.8` (Note: We use `top_p` instead of `top_k` based on optimal parameters for non-thinking mode)
- **Context Window**: `16384` (Practical limit for M4 Air; going up to 32K causes significant performance degradation).

### Known Quirks & Safety Nets
1. **The "Thinking" Leak**: Similar to MiniCPM5, it may emit internal reasoning despite `enable_thinking: false`. 
   - *Mitigation*: We use `_strip_thinking_tags()` in `complex_utils/formatter.py` to strip out any leaked XML reasoning tags before the content reaches the user UI.
2. **The Blank Response**: If Qwen gets stuck in a thinking loop and outputs *nothing* but reasoning (which then gets stripped), it returns an empty string. 
   - *Mitigation*: The `_fallback_for_blank_response()` in `fallback.py` synthesizes a safe fallback message. If it was parsing a tool output (like `web_search`), it intelligently surfaces the raw tool output so the UI thread doesn't appear dead.
3. **LM Studio System Prompt Crash**: LM Studio Jinja templates can fail with "No user query found in messages" if only a system message is provided.
   - *Mitigation*: We set `fold_system: true` in `defaults.yaml`. In `lm_studio_compat.py`, this cleanly folds the system instructions into the first `HumanMessage` wrapped in `[SYSTEM INSTRUCTIONS BEGIN]`. This bypasses the bug without breaking the model's alignment.
4. **Boilerplate Disclaimers**: Due to its training data, this uncensored variant may still append generic legal/medical disclaimers. We do not attempt to strip these out programmatically to avoid accidentally stripping actual content.

---

## 3. Configuration Architecture (Single Source of Truth)

All model base URLs, endpoints, temperature settings, and context windows are stored strictly in `src/config/defaults.yaml`. 
We **do not** hardcode temperatures or token limits in node files (`router.py`, `complex.py`), except for deterministic overrides. `config_loader.py` handles the merging of `defaults.yaml`, `.env`, `.env.local`, and profile overrides.

Non-M4 timeout/token overrides live under `models.standard` in `defaults.yaml` (merged into `models.small` / `models.medium` at load time).

---

## 4. Routing (3 routes)

| Route | Model path | When |
|-------|------------|------|
| `simple` | `models.small` (MiniCPM5) | Short Q&A, low tool need |
| `complex-default` | `models.medium` (Qwen 9B) | Local tool loops, multimodal images |
| `complex-cloud` | `models.cloud` (DeepSeek V4) | Frontier reasoning; images via `vision_proxy` → text |

Legacy routes `complex-vision` and `complex-longctx` were removed (2026-06). Cloud path details: [`DEEPSEEK_V4_INTEGRATION.md`](../architecture/DEEPSEEK_V4_INTEGRATION.md).

**Last updated:** 2026-06-07
