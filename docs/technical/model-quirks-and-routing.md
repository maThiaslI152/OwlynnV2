# Model Quirks & Routing Setup

**Date:** June 2026  
**Last updated:** 2026-06-27

This document details the local LLM routing stack, model-specific quirks, and the reasoning behind our configuration choices.

---

## 1. The Local Unified Model: Gemma 4 E2B

The project uses `gemma-4-e2b-heretic-uncensored-mlx` (via LM Studio) as the local unified model slot (`models.small`). It serves as the router, simple answer engine, vision proxy, and memory extractor.

### Why Gemma 4 E2B?
- **Multimodal native:** 4B parameter VLM with native vision support — no separate vision model needed.
- **Strong tool calling:** Reliable `tool_use` capability for structured tool invocations.
- **Good reading comprehension:** Outperforms previous models on context ingestion tasks (F4.1 recall).
- **Compact:** ~5 GB VRAM (MLX 4-bit quantization), fits comfortably on M4 Air 24 GB alongside embedding model.

### Known Quirks & Safety Nets
- **Thinking Tags:** Qwen uses `<thinking>` and `<think>` tags (in addition to plaintext "Thinking Process:" format). We strip all three formats in `formatter.py:_strip_thinking_tags()` and `router.py` to ensure clean JSON routing output.
- **No `enable_thinking` toggle:** Unlike Gemma, Qwen does not use `chat_template_kwargs: enable_thinking`. Thinking is controlled via prompt instructions and post-processing strips.

---

## 2. Cloud Primary: DeepSeek V4 (via API)

All complex reasoning, tool calling, and vision synthesis runs on DeepSeek V4 cloud. No local complex model is loaded.

- **Configuration**: `models.cloud` in `defaults.yaml` (`deepseek-v4-flash` default, `deepseek-v4-pro` available)
- **Context**: 1M tokens
- **Vision**: Images are first transcribed by local Gemma 4 E2B, then DeepSeek synthesizes from transcribed text (text-only API)

See [`DEEPSEEK_V4_INTEGRATION.md`](../architecture/DEEPSEEK_V4_INTEGRATION.md) for cloud path details.

## 3. Configuration Architecture (Single Source of Truth)

All model base URLs, endpoints, temperature settings, and context windows are stored strictly in `src/config/defaults.yaml`. 
We **do not** hardcode temperatures or token limits in node files (`router.py`, `complex.py`), except for deterministic overrides. `config_loader.py` handles the merging of `defaults.yaml`, `.env`, `.env.local`, and profile overrides.

Model name accessors in `ConfigLoader` provide a single point of reference:
- `config.get_small_model_name()` — unified local model
- `config.get_cloud_model_name()` — cloud model
- `config.get_embedding_model_name()` — embedding model

Changing models = edit `defaults.yaml` only.

## 4. Routing (Cloud-Primary)

| Route | Model path | When |
|-------|------------|------|
| `simple` | `models.small` (Gemma 4 E2B) | Short Q&A, low tool need |
| `complex-cloud` | `models.cloud` (DeepSeek V4) | All complex reasoning; images via `vision_proxy` → text |
| `complex-default` | `models.small` (Gemma 4 E2B) | Local fallback when cloud is unavailable |

Cloud path details: [`DEEPSEEK_V4_INTEGRATION.md`](../architecture/DEEPSEEK_V4_INTEGRATION.md).

---

## 5. Vision proxy: Gemma 4 E2B

Gemma 4 E2B serves as the VLM proxy for the cloud path. It transcribes text and describes image/UI context — DeepSeek synthesizes from the transcription.

### Role split

| Layer | Model | Job |
|-------|--------|-----|
| `vision_proxy` | **Gemma 4 E2B** on LM Studio | Natural-language transcription (text + UI) |
| `complex-cloud` | **DeepSeek V4** | Final answer from transcribed text |

On proxy failure: `complex-cloud` retries with text-only prompt (no local multimodal fallback).

Config: `models.small.model_name` (used for routing, vision, and extraction).

### VLM / LM Studio quirks

1. **Prompt = natural language** — System + user messages with `image_url` blocks.
2. **Vision output varies** — Plain text or prose descriptions. Parser: `vision_qwen3vl.py` (which parses text/UI output); single call.
3. **No image to cloud** — DeepSeek is text-only; images are stripped after proxy.

### Telemetry (eval + WS)

`model_info` events include `vision_intake_mode` (`proxy` | `fallback`) and `vision_proxy_model` when the VLM succeeded.
