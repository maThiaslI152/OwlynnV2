# Model Quirks & Routing Setup

**Date:** August 2026  
**Last updated:** 2026-08-24

This document details the local LLM routing stack, model-specific quirks, and the reasoning behind our configuration choices.

---

## 1. Unified Local Architecture

Owlynn is standardized on the **Unified Local Architecture**:

1. **Main Local Model (`gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m`)**:
   - Single unified local engine handling routing classification, direct simple responses, chat titles, background memory extraction, local complex reasoning fallback, and offline pentest mode (90% tool accuracy, 53 tok/s).
   - Config: `models.main` & `models.pentest` in `defaults.yaml`.

2. **Vision Model (`baidu.unlimited-ocr`)**:
   - Dedicated vision and OCR transcription proxy. Transcribes text/UI from images before passing structured text to the reasoning engine.
   - Config: `models.vision` in `defaults.yaml`.

3. **Embedding Model (`text-embedding-mxbai-embed-large-v1`)**:
   - 1024-dimensional dense vector embeddings for PostgreSQL pgvector (`memory_vectors`, `semantic_cache`, `engagement_vectors`).
   - Config: `models.embedding` in `defaults.yaml`.

4. **Pentest Mode (Zero-Latency Switching)**:
   - Evaluated winner for local tool execution with 90% tool-use accuracy. Also supports `gemma-4-12b-coder-fable5-composer2.5-v1@q4_k_m` (84.1% overall).
   - Config: `models.pentest` in `defaults.yaml`.

---

## 2. Cloud Primary: DeepSeek V4 (via API)

All complex multi-step reasoning, tool calling, and synthesis runs on DeepSeek V4 cloud when configured.

- **Configuration**: `models.cloud` in `defaults.yaml` (`deepseek-v4-flash` default, `deepseek-v4-pro` available)
- **Context**: 1M tokens
- **Vision**: Images are first transcribed by `baidu.unlimited-ocr`, then DeepSeek synthesizes from transcribed text (text-only API)

See [`DEEPSEEK_V4_INTEGRATION.md`](../architecture/DEEPSEEK_V4_INTEGRATION.md) for cloud path details.

## 3. Configuration Architecture (Single Source of Truth)

All model base URLs, endpoints, temperature settings, and context windows are stored strictly in `src/config/defaults.yaml`. 
We **do not** hardcode temperatures or token limits in node files (`router.py`, `complex.py`), except for deterministic overrides. `config_loader.py` handles the merging of `defaults.yaml`, `.env`, `.env.local`, and profile overrides.

Model name accessors in `ConfigLoader` provide a single point of reference:
- `config.get_main_model_name()` — unified local model
- `config.get_vision_model_name()` — vision proxy model
- `config.get_embedding_model_name()` — embedding model
- `config.get_pentest_model_name()` — pentest model
- `config.get_cloud_model_name()` — cloud model

Changing models = edit `defaults.yaml` only.

## 4. Routing (Cloud-Primary & Local-Capable)

| Route | Model path | When |
|-------|------------|------|
| `simple` | `models.main` (Gemma 4 12B Agentic) | Short Q&A, low tool need |
| `complex-cloud` | `models.cloud` (DeepSeek V4) | Complex reasoning; images via `vision_proxy` → text |
| `complex-default` | `models.main` (Gemma 4 12B Agentic) | Local fallback when cloud is unavailable or offline mode |

---

## 5. Vision proxy: baidu.unlimited-ocr

`baidu.unlimited-ocr` serves as the OCR/VLM proxy for the reasoning path. It transcribes text and describes image/UI context — DeepSeek / Main LLM synthesizes from the transcription.

### Role split

| Layer | Model | Job |
|-------|--------|-----|
| `vision_proxy` | **baidu.unlimited-ocr** on LM Studio | OCR & natural-language transcription (text + UI) |
| `complex-cloud` / `complex-default` | **DeepSeek V4** / **Gemma 4 12B Agentic** | Final answer from transcribed text |

On proxy failure: `complex-cloud` retries with text-only prompt.

Config: `models.vision.model_name`.

---

## 6. Gemma 4 12B Agentic quirks (local path)

Model: `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q4_k_m` (`models.main` / `models.pentest`).

| Quirk | Mitigation in Owlynn |
|-------|---------------------|
| Emits `<think>` blocks | Stripped in `formatter.py` (`_strip_thinking_tags`) on complex and simple paths |
| Tool-happy (90% tool accuracy) — loops tools instead of writing prose | Category web budgets (`complex.web_tool_budgets`), `complex.max_web_tool_rounds`, forced synthesis (`tools_for_invoke = None`), `COMPLEX_TOOL_GUIDANCE_WEB_LOCAL` |
| Weak output synthesis (~74%) / multi-step completion (~69%) | `_fallback_for_blank_response`, one synthesis retry (`needs_web_synthesis_retry`, `_looks_like_prose_tool_stall`), coherence retry on local route |
| Text-only (no native vision) | `_invoke_local_path` / `_invoke_pentest_path` sanitize `image_url` blocks to `[Image attached by user]` |
| Gemma stop tokens (`<end_of_turn>`, etc.) | Passed via `models.main.stop` / `models.pentest.stop` in `_invoke_local_path` and `_invoke_pentest_path` (not `_invoke_cloud_path`) |
| Prose tool stall ("I will now search…") | `_looks_like_prose_tool_stall` triggers one local synthesis retry with tools unbound |
| Multi-hop `notebook_run` for charts stalls turns | Local path uses **HTML + offline Chart.js via `write_workspace_file`** for default charts (`/vendor/chart.umd.min.js`, no CDN); `notebook_run` only when user explicitly asks for matplotlib/PNG |
| MTP speculative decode crashes on newer builds | Upstream regression in llama.cpp `gemma4-assistant` loader (`invalid vector subscript` on b9702+). **Verified working on `llama.cpp b9553` (commit `9e3b928fd`)** with `MTP/gemma-4-12B-it-MTP-Q8_0.gguf` accelerating throughput from ~88 tok/s to ~180 tok/s. Use `./scripts/run_llama_server.sh` for in-project high-throughput serving. |
| Author-tuned sampling params | Configured in `defaults.yaml` (`top_p: 0.95`, `top_k: 64`, `repeat_penalty: 1.1`, `flash_attention: true`, `temperature: 0.1`). |
| KV cache: no synthetic `HumanMessage` mid-turn | Web/fetch nudges appended to `ToolMessage.content`; synthesis hints via volatile suffix (`build_volatile_suffix`) |

### Local prompt patterns

- **Normal complex (`complex-default`)**: `COMPLEX_TOOL_GUIDANCE_WEB_LOCAL` — "Use web_search once, then synthesize" instead of exhaustive multi-tool research loops.
- **Forced synthesis hop**: `COMPLEX_TOOL_GUIDANCE_LOCAL_SYNTHESIS` injected into volatile suffix when web budget is exhausted.
- **Local-first toolbox**: `_toolbox_for_local_first` picks a narrow set (live-data → `web_search` only; else lean `web_search`+`memory`+`productivity`) — never implicit `["all"]`.
- **Tool rerank**: Shared `_rerank_tools_for_invoke` caps the bind list before invoke **and** context telemetry (`bound_tool_count` / Schemas). Local top_k = `complex.local_tool_rerank_top_k` (default 8); second pass in `_invoke_local_path` is a no-op when already ≤ min_count.
- **Kali tools**: Gated to pentest scenario only (`KALI_SCREEN_ASSIST_TOOLS` excluded from `COMPLEX_TOOLS_WITH_WEB`). Screen-assist / ipynb also omitted from the lean `"all"` catalog (named toolboxes only).

### Context window

`models.main.context_window` is **16384** (16k) for 24GB Mac RAM safety. Pentest slot may advertise 32k in LM Studio but complex local path caps against `models.main.context_window`.
