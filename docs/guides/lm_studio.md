---
status: active
category: guide
last_updated: 2026-05-31
owner: human
---

# LM Studio Setup

> **Purpose:** Guide for configuring and using LM Studio with Owlynn.


## Models to Download

Owlynn uses a **router** (always loaded) plus an **extraction** model for background memory. Complex reasoning is handled entirely by DeepSeek V4 cloud — no local complex model needed.

### Router (Always Loaded)

- `minicpm5-1b` (or `mlx-community/MiniCPM5-1B-8bit`) — routing, simple answers, chat titles

### Extraction (Background memory, lazy-loaded)

- `gemma-4-e2b-heretic-uncensored-mlx` — background memory extraction (STM → LTM writes, idle-deferred)
- Config: `models.extraction` in [`defaults.yaml`](../../src/config/defaults.yaml)

### Vision proxy (Cloud + image path — Qwen3-VL-4B)

- **`qwen3-vl-4b-instruct-c_abliterated-v2-mlx`** — lazy-loaded on first image; **full multimodal VLM** (describes images, transcribes text, identifies UI)
- On proxy failure: `complex-cloud` retries text-only (no local multimodal fallback)
- Config: `models.vision_proxy` in [`defaults.yaml`](../../src/config/defaults.yaml)

### Embeddings (RAG / Memory Only)

- `text-embedding-nomic-embed-text-v1.5-embedding` — Qdrant vector search for **text documents only**
- Chat images go through Qwen3-VL-4B vision proxy → DeepSeek text (not local multimodal)

### Legacy note

Older docs referenced separate vision/longctx model slots, Qwen 9B medium models, and Gemma variants. Current architecture is cloud-primary: only `minicpm5-1b` (router) and `gemma-4-e2b` (extraction) run locally in LM Studio. All complex reasoning goes to DeepSeek V4 cloud.

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

2026-06-07 — Qwen3.5 + mmproj vision setup; nomic embed scope clarified
