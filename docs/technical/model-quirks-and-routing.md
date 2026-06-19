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

## 2. Cloud Primary: DeepSeek V4 (via API)

All complex reasoning, tool calling, and vision synthesis runs on DeepSeek V4 cloud. No local complex (medium) model is loaded — this eliminates the 2–3 min Qwen response times on M4 Air.

- **Configuration**: `models.cloud` in `defaults.yaml` (`deepseek-v4-flash` default, `deepseek-v4-pro` available)
- **Context**: 1M tokens
- **Vision**: Images are first transcribed by local Qwen3-VL-4B, then DeepSeek synthesizes from transcribed text (text-only API)

See [`DEEPSEEK_V4_INTEGRATION.md`](../architecture/DEEPSEEK_V4_INTEGRATION.md) for cloud path details.

## 3. Configuration Architecture (Single Source of Truth)

All model base URLs, endpoints, temperature settings, and context windows are stored strictly in `src/config/defaults.yaml`. 
We **do not** hardcode temperatures or token limits in node files (`router.py`, `complex.py`), except for deterministic overrides. `config_loader.py` handles the merging of `defaults.yaml`, `.env`, `.env.local`, and profile overrides.

## 4. Routing (Cloud-Primary)

| Route | Model path | When |
|-------|------------|------|
| `simple` | `models.small` (MiniCPM5) | Short Q&A, low tool need |
| `complex-cloud` | `models.cloud` (DeepSeek V4) | All complex reasoning; images via `vision_proxy` → text |

Legacy routes `complex-default`, `complex-vision`, and `complex-longctx` were removed (2026-06). Cloud path details: [`DEEPSEEK_V4_INTEGRATION.md`](../architecture/DEEPSEEK_V4_INTEGRATION.md).

---

## 5. Vision proxy: Qwen3-VL-4B (`qwen3-vl-4b-instruct-c_abliterated-v2-mlx`)

Qwen3-VL is a **full multimodal VLM** for the cloud path. It transcribes visible text and describes UI — DeepSeek synthesizes from the transcription.

### Role split

| Layer | Model | Job |
|-------|--------|-----|
| `vision_proxy` | **Qwen3-VL-4B** on LM Studio | Natural-language transcription (text + UI) |
| `complex-cloud` badge | **DeepSeek V4** | Final answer from transcribed text |

On proxy failure: `complex-cloud` retries with text-only prompt (no local multimodal fallback).

Config: `models.vision_proxy.model_name`, `cloud.vision_prompt_mode: qwen3vl`.

### Qwen3-VL / LM Studio quirks

1. **Prompt = natural language** — System + user messages with `image_url` blocks. No task tokens needed. Chat template with `enable_thinking: false` suppresses reasoning overhead.
2. **Vision output varies** — Plain text or prose descriptions. Parser: `vision_qwen3vl.py`; single call (no retry ladder like Florence needed).
3. **One loaded weights set** — LM Studio serves whatever is loaded. `ensure_vision_vlm_loaded()` uses the native `/api/v1/models/load` API before vision when `cloud.vision_lm_studio_auto_load: true`.
4. **Lazy load** — Qwen3-VL is not startup-preloaded (router + embed are). First image triggers load; client unloads after `vision_idle_unload_seconds` (300s).
5. **No image to cloud** — DeepSeek is text-only; images are stripped after proxy. Eval badge `large-cloud` does not prove VLM ran — check `vision_proxy_model` / transcription content.

### Telemetry (eval + WS)

`model_info` events include `vision_intake_mode` (`proxy` | `fallback`) and `vision_proxy_model` when Qwen3-VL succeeded.

**Last updated:** 2026-06-10
