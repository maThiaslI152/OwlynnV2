# Qwen3-VL-4B Vision Proxy Upgrade (2026-06-19)

## Summary

Replaced Florence-2 with **Qwen3-VL-4B** (`qwen3-vl-4b-instruct-c_abliterated-v2-mlx`) as the vision proxy VLM. Florence-2 was incompatible with the current LM Studio version (MLX-format load rejected via API). Qwen3-VL-4B is a full multimodal VLM that loads correctly and provides better image understanding.

## Why

- Florence-2 MLX format rejected by LM Studio API (`/api/v1/models/load` returned 500)
- Florence was OCR-only (task tokens); Qwen3-VL is full multimodal (text + UI + description)
- Qwen3-VL uses standard OpenAI-compatible `image_url` messages — no task tokens needed
- 3.0 GB model fits comfortably in M4 Air 24GB alongside router + extraction + embeddings

## Changes

### Source (11 files)

| File | Change |
|------|--------|
| `defaults.yaml` | `models.vision_proxy` → Qwen3-VL config; `vision_prompt_mode: qwen3vl`; tuned prompts; 2048 max_tokens |
| `lm_studio_vision.py` (new) | Replaces `lm_studio_florence.py`. Catalog search for Qwen3-VL key; `ensure_vision_vlm_loaded()` |
| `vision_qwen3vl.py` (new) | Parses Qwen3-VL natural-language output into structured text_blocks/ui_elements schema |
| `vision_proxy.py` | Single-call VLM (no Florence retry ladder). `_build_vlm_messages()` uses system+user+image_url |
| `vision_model_manager.py` | Removed Florence guard + `stream_chunk_timeout` bug. Generalized to any vision VLM |
| `vision_schema.py` | Updated VLM prompts for verbatim transcription. `format_vision_for_cloud()` format updated |
| `complex.py` | `_vision_telemetry()` → `configured_vision_model_name`. Vision guidance for DeepSeek uses `[Image content transcribed]` block |
| `router.py` | Updated import to `lm_studio_vision` |
| `config_loader.py` | Comment updated |

Legacy kept: `vision_florence.py` for `vision_prompt_mode: florence` backward compat.

### Tests (1 file)

| File | Change |
|------|--------|
| `test_lm_studio_florence.py` | Updated to test `lm_studio_vision` with Qwen3-VL catalog keys |
| `test_router_web_intent.py` | Import path → `lm_studio_vision` |
| `test_vision_route_determinism.py` | Import path → `lm_studio_vision` |
| `test_vision_florence_parser.py` | Added Qwen3-VL parser import |

### Docs (16 files)

| File | Change |
|------|--------|
| `architecture/VISION_PROXY.md` | Full rewrite for Qwen3-VL |
| `architecture/DEEPSEEK_V4_INTEGRATION.md` | All 6 Florence references → Qwen3-VL |
| `architecture/overview.md` | Vision proxy description |
| `STATUS.md` | Model config table + eval trajectory |
| `PERFORMANCE_SLOS.md` | Memory budget: 6.9GB → 9.1GB; Qwen3-VL added to degradation ladder |
| `CLOUD-LLM-ARCHITECTURE.md` | Vision proxy module references |
| `PROJECT_GUIDE.md` | Module list + current models |
| `CHAT_PROTOCOL.md` | Image processing description |
| `COMPETITIVE_FEATURE_ANALYSIS.md` | Vision proxy description |
| `COMPLETENESS_REVIEW.md` | Vision proxy + F9.1 status |
| `ADR.md` | Vision proxy preload |
| `standards/EVALUATION.md` | Allowed models |
| `guides/dev-startup.md` | Vision model in LM Studio checklist |
| `guides/lm_studio.md` | Vision proxy section |
| `guides/cloud-multi-turn-context.md` | Image processing |
| `technical/model-quirks-and-routing.md` | Full vision section rewrite |

### Deleted

- `src/agent/nodes/complex_utils/lm_studio_florence.py` (replaced by `lm_studio_vision.py`)

## Verification

- **F9.1 (Vision Proxy)**: **100/100** — Qwen3-VL transcribes "EVAL_OCR_MARKER" from eval fixture, DeepSeek synthesizes correctly
- **F1.1 (Router Simple)**: 90/100 — consistent
- **F9.1 time**: 6-15s (was 6-80s with Florence)
- **CI**: ruff + format + lint ✓, mypy ✓, vision tests ✓
- **LM Studio**: 4 models loaded — MiniCPM5 (1.1GB) + Gemma (3.4GB) + Qwen3-VL (3.0GB) + Embed (0.14GB) = **7.5 GB total**
- **Known eval issues** (pre-existing, not regression): F2.1/W1.1 transient routing to simple

## Configuration

```yaml
models:
  vision_proxy:
    model_name: "qwen3-vl-4b-instruct-c_abliterated-v2-mlx"
    lm_studio_model_key: "qwen3-vl-4b-instruct-c_abliterated-v2-mlx"
    temperature: 0.1
    max_tokens: 2048

cloud:
  vision_prompt_mode: qwen3vl
  vision_qwen3vl_system: "You are an OCR sensor. Output ALL visible text exactly..."
  vision_qwen3vl_user: "Extract the exact text from this image..."
```

## Related

- [`docs/evaluations/cloud-only-pivot-eval-2026-06-19.md`](../../docs/evaluations/cloud-only-pivot-eval-2026-06-19.md)
- [`docs/architecture/VISION_PROXY.md`](../../docs/architecture/VISION_PROXY.md)
- [`docs/changes/cloud-only-pivot/CHANGELOG.md`](../cloud-only-pivot/CHANGELOG.md)
- [Model: LethalDonkey/Qwen3-VL-4B-Instruct-c_abliterated-v2-MLX-4bit](https://huggingface.co/LethalDonkey/Qwen3-VL-4B-Instruct-c_abliterated-v2-MLX-4bit)
