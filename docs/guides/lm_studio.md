---
status: active
category: guide
last_updated: 2026-05-31
owner: human
---

# LM Studio Setup

> **Purpose:** Guide for configuring and using LM Studio with Owlynn.


## Models to Download

Owlynn uses a **router** (always loaded) plus one **medium** model for complex local work. Chat image attachments use native multimodal on the medium model — not the nomic embedding model.

### Router (Small, Always Loaded)

- `minicpm5-1b` (or `mlx-community/MiniCPM5-1B-8bit`) — routing, simple answers, chat titles

### Medium (Complex Local Tasks + Vision)

- **Main weights:** `HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive` — load the **Q6_K** GGUF in LM Studio
- **Vision encoder (required for image chat):** `mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf` — load alongside the main GGUF so image attachments work

Without the `mmproj` file, text chat works but **image uploads will fail** at the local VLM step.

### Embeddings (RAG / Memory Only)

- `text-embedding-nomic-embed-text-v1.5-embedding` — Qdrant vector search for **text documents only**
- Chat images are **not** embedded; they go directly to Qwen as `image_url` multimodal input

### Legacy note

Older docs referenced separate vision/longctx model slots and Gemma variants. Current defaults use one Qwen3.5-9B instance for default, vision, and long-context routes (`src/config/defaults.yaml`).

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
