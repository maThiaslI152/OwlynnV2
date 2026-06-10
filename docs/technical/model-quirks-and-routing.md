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

---

## 5. Vision proxy: Florence-2 (`florence-2-base-nsfw-v2-ext-mlx`)

Florence is **OCR-only** for the cloud path. It never answers the user — DeepSeek synthesizes from Florence’s text block.

### Role split (do not conflate with Qwen)

| Layer | Model | Job |
|-------|--------|-----|
| `vision_proxy` | **Florence-2** on LM Studio | Task-token OCR (`<OCR>`, `<OCR_WITH_REGION>`) |
| `complex-cloud` badge | **DeepSeek V4** | Final answer from transcribed text |
| `complex-default` fallback | **Qwen 9B + mmproj** | Only when Florence proxy **fails** — not the designed path |

Config: `models.vision_proxy.model_name`, `cloud.vision_prompt_mode: florence` (never `json_chat` in production).

### Florence / LM Studio quirks

1. **Prompt = task token only** — First user content must be `<OCR>` or `<OCR_WITH_REGION>`, not chat instructions. Chat templates that expect dialogue break OCR.
2. **Greedy, short output** — `temperature: 0`, `top_p: 1`, `vision_max_tokens: 512`. Long generations are wasted on OCR and invite hallucination.
3. **One loaded weights set** — LM Studio serves whatever is loaded. If Qwen is active, Florence API calls fail or return garbage. `ensure_florence_loaded()` uses the native `/api/v1/models/load` API before OCR when `cloud.vision_lm_studio_auto_load: true`.
4. **Output shapes vary** — Plain text, Python dict literals, or `<OCR_WITH_REGION>` region maps. Parser: `vision_florence.py`; retry ladder: primary `<OCR>` → `<OCR_WITH_REGION>` → `<OCR>`.
5. **Lazy load** — Florence is not startup-preloaded (router + embed are). First image triggers load; client unloads after `vision_idle_unload_seconds` (300s).
6. **No image to cloud** — DeepSeek is text-only; images are stripped after proxy. Eval badge `large-cloud` does not prove Florence ran — check `vision_proxy_model` / OCR marker.

### Telemetry (eval + WS)

`model_info` events include `vision_intake_mode` (`proxy` | `fallback`) and `vision_proxy_model` when Florence succeeded.

**Last updated:** 2026-06-10
