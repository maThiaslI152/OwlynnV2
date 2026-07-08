---
status: active
category: guide
last_updated: 2026-06-27
owner: human
---

# LM Studio Setup

> **Purpose:** Guide for configuring and using LM Studio with Owlynn.


## Models to Download

Owlynn uses a single **local unified model** (`gemma-4-e2b-heretic-uncensored-mlx`) which acts as the router, simple path executor, vision proxy VLM, background memory extraction tool, and cloud fallback for complex reasoning when DeepSeek V4 is unavailable.

### Local Unified Model (Always Loaded)

- `gemma-4-e2b-heretic-uncensored-mlx` — handles routing, simple answers, chat titles, vision proxy (image transcription), background memory extraction, and cloud fallback. 4B params, 4-bit quantization, ~5 GB VRAM.
- Config: `models.small` in [`defaults.yaml`](../../src/config/defaults.yaml)
- **Important:** Set LM Studio `n_ctx` to 65536 or higher for this model.

### Embeddings (RAG / Memory Only)

- `text-embedding-nomic-embed-text-v1.5-embedding` — Qdrant vector search for **text documents only**
- Chat images go through the unified local model vision proxy → DeepSeek text (no cloud image upload).

### Legacy note

Older docs referenced separate vision/longctx model slots, Qwen 9B medium models, Florence-2/Gemma 4 E2B vision proxies, and Gemma variants. Current architecture is cloud-primary with a single unified local model (`gemma-4-e2b-heretic-uncensored-mlx`) and nomic embedding. Complex reasoning goes to DeepSeek V4 cloud, with local fallback when cloud is unavailable.

## Jinja Template Issues — `No user query found in messages`

LM Studio applies the model's **Jinja chat template** to the `/v1/chat/completions` payload. Some model templates (e.g., legacy Qwen 3.x variants no longer in use) expect a normal **user** role in the message list. Owlynn mitigates this in two ways:

1. **Router** uses a `HumanMessage` (not system-only) for routing.
2. **`lm_studio_fold_system`** (default **on** in profile defaults): system instructions are **prepended into the first user message** so the API sees a clear user turn. Disable in `data/user_profile.json` if your backend requires a separate system role:

   ```json
   "lm_studio_fold_system": false
   ```

## If errors persist

- Update **LM Studio** to the latest build.
- Prefer **`lmstudio-community`** GGUF variants when available.
- In **My Models → model settings → Prompt Template**, try a fixed template or one from community presets.

## Related

- [`docs/README.md`](../README.md) — project documentation map

## Last updated

2026-06-27 — Updated unified local model to Gemma 4 E2B; nomic embed scope clarified
