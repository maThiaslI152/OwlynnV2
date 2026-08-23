---
status: active
category: guide
last_updated: 2026-08-23
owner: human
---

# LM Studio Setup

> **Purpose:** Guide for configuring and using LM Studio with Owlynn.

## Models to Load

Owlynn is standardized on the **Unified Local Architecture**:

### 1. Main Local Model (Always Loaded — Unified Engine)

- `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m` — unified local engine handling routing classification, direct simple answers, chat titles, background memory extraction, local reasoning fallback, and offline pentest mode.
- Config: `models.main` & `models.pentest` in [`defaults.yaml`](../../src/config/defaults.yaml)
- **Important:** Set LM Studio `n_ctx` to 32768, `flash_attention: true`, and disable simple draft speculative decoding.

### 2. Vision Model (Lazy Loaded)

- `baidu.unlimited-ocr` — dedicated vision transcription and OCR proxy.
- Config: `models.vision` in [`defaults.yaml`](../../src/config/defaults.yaml)

### 3. Embedding Model (Always Loaded)

- `text-embedding-mxbai-embed-large-v1` (1024 dims) — PostgreSQL pgvector (`memory_vectors`, `semantic_cache`, `engagement_vectors`) search and web RAG.
- Config: `models.embedding` in [`defaults.yaml`](../../src/config/defaults.yaml)

### 4. Pentest Mode (Zero-Latency Switching)

- Uses the active `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m` (90% tool accuracy, 53 tok/s). Also supports `gemma-4-12b-coder-fable5-composer2.5-v1@q4_k_m`.
- Config: `models.pentest` in [`defaults.yaml`](../../src/config/defaults.yaml)

### Cloud Escalation

- `DeepSeek V4` (`deepseek-v4-flash` default, `deepseek-v4-pro` optional) for heavy complex multi-step reasoning via cloud API.

## Jinja Template Issues — `No user query found in messages`

LM Studio applies the model's **Jinja chat template** to the `/v1/chat/completions` payload. Owlynn handles template compatibility via:

1. **Router** uses a `HumanMessage` for routing.
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

2026-08-22 — Standardized on 4-model taxonomy (Gemma 4 26B main, baidu.unlimited-ocr vision, MXBAI 1024-dim embedding, Gemma 4 12B Coder pentest).
