# Model Quirks & Routing Setup

**Date:** June 2026  
**Context:** Migration to LangChain/LangGraph patterns (`migrate-deepseekv4`)  

This document details the local LLM routing stack, model-specific quirks, and the reasoning behind our configuration choices.

---

## 1. The Local Unified Model: Gemma-4-E2B

The project uses `gemma-4-e2b-heretic-uncensored-mlx` (via LM Studio) as the local unified model slot (`models.small`). It serves as the router, simple answer engine, vision proxy, and memory extractor.

### Why Gemma-4-E2B?
- **High Reasoning-to-Size Ratio:** The 2B parameter Gemma-4-E2B provides exceptional tool-routing logic and structured JSON classification for its class.
- **Clean "No-Think" mode:** Gemma outputs direct classification answers when thinking mode is disabled, enabling tight JSON routing schema outputs without VRAM thrashing.

### Known Quirks & Safety Nets
- **Thinking Tags:** We preserve the fallback extraction logic in `parse_routing()` and the safety strip: `re.sub(r"<think>.*?</think>", "", content)` to ensure robust JSON parsing even if any model experiences spontaneous thinking mode.

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
| `simple` | `models.small` (Gemma-4-E2B) | Short Q&A, low tool need |
| `complex-cloud` | `models.cloud` (DeepSeek V4) | All complex reasoning; images via `vision_proxy` → text |

Legacy routes `complex-default`, `complex-vision`, and `complex-longctx` were removed (2026-06). Cloud path details: [`DEEPSEEK_V4_INTEGRATION.md`](../architecture/DEEPSEEK_V4_INTEGRATION.md).

---

## 5. Vision proxy: Gemma-4-E2B (`gemma-4-e2b-heretic-uncensored-mlx`)

Gemma-4-E2B serves as the VLM proxy for the cloud path. It transcribes text and describes image/UI context — DeepSeek synthesizes from the transcription.

### Role split

| Layer | Model | Job |
|-------|--------|-----|
| `vision_proxy` | **Gemma-4-E2B** on LM Studio | Natural-language transcription (text + UI) |
| `complex-cloud` | **DeepSeek V4** | Final answer from transcribed text |

On proxy failure: `complex-cloud` retries with text-only prompt (no local multimodal fallback).

Config: `models.small.model_name` (used for routing, vision, and extraction).

### VLM / LM Studio quirks

1. **Prompt = natural language** — System + user messages with `image_url` blocks.
2. **Vision output varies** — Plain text or prose descriptions. Parser: `vision_qwen3vl.py` (which parses text/UI output); single call.
3. **No image to cloud** — DeepSeek is text-only; images are stripped after proxy.

### Telemetry (eval + WS)

`model_info` events include `vision_intake_mode` (`proxy` | `fallback`) and `vision_proxy_model` when the VLM succeeded.

**Last updated:** 2026-06-22
