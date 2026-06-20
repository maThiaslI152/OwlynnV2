---
status: active
category: architecture
last_updated: 2026-06-19
owner: ai-agent
---

# Vision Proxy (Phase 2)

Gemma 4 (heretic-uncensored) acts as a **vision-language sensor** for the text-only DeepSeek cloud path. It transcribes visible text, detects UI elements, and describes visual structure — DeepSeek synthesizes the final answer from the transcription.

## Flow

```text
User image (chat upload or screen crop)
  → vision_proxy (Gemma 4 local VLM, lazy-loaded)
  → natural-language transcription of text + UI
  → formatted block in cloud prompt (image_url stripped)
  → DeepSeek V4
```

## Modules

| Path | Role |
|------|------|
| `src/agent/nodes/complex_utils/vision_proxy.py` | Image interception, VLM call, cache, cloud formatting |
| `src/agent/nodes/complex_utils/vision_qwen3vl.py` | Parse natural-language output into structured blocks |
| `src/agent/nodes/complex_utils/vision_schema.py` | Output contract: text_blocks, ui_elements, subjects, confidence |
| `src/agent/nodes/complex_utils/lm_studio_vision.py` | LM Studio catalog search, auto-load, active-instance check |
| `src/agent/nodes/complex_utils/vision_model_manager.py` | Lazy ChatOpenAI client, idle watchdog (300s unload) |
| `src/agent/nodes/complex.py` | `complex-cloud` + images → proxy; failure → text-only fallback |

## Output contract

Gemma is prompted to transcribe text verbatim and identify UI elements. The parser extracts:

```json
{
  "text_blocks": [{"text": "EVAL_OCR_MARKER", "bbox": null}],
  "ui_elements": [{"role": "button", "label": "Submit"}],
  "subjects": ["image"],
  "confidence": 0.75
}
```

Cloud-visible format:
```
[Image content transcribed by vision sensor]
Visible text: EVAL_OCR_MARKER
confidence=0.75
```

## Model config (`defaults.yaml`)

```yaml
models:
  vision_proxy:
    model_name: "gemma-4-e2b-heretic-uncensored-mlx"
    lm_studio_model_key: "gemma-4-e2b-heretic-uncensored-mlx"
    temperature: 0.1
    max_tokens: 2048
    extra_body:
      chat_template_kwargs:
        enable_thinking: false

cloud:
  vision_prompt_mode: qwen3vl
  vision_qwen3vl_system: "You are an OCR sensor. Output ALL visible text exactly..."
  vision_qwen3vl_user: "Extract the exact text from this image..."
  vision_max_tokens: 2048
  vision_temperature: 0.1
  vision_lm_studio_auto_load: true
```

## Lazy load

`VisionModelManager` holds a dedicated client. Unloads after `cloud.vision_idle_unload_seconds` (default 300s) with no active transcriptions. On proxy failure, `complex-cloud` retries text-only.

Models loaded in LM Studio for production:
- `gemma-4-e2b-heretic-uncensored-mlx` (Unified: router, extraction, vision)
- `text-embedding-nomic-embed-text-v1.5` (0.14 GB) — embeddings

## Screen assist hook (Phase 3)

```python
await transcribe_crop(image_bytes, mime_type="image/png")
```

Used by `src/tools/screen_assist/ax_macos.py` when AX returns no text (512×512 crop).

## Configuration

```yaml
cloud:
  vision_transcription_cache_ttl: 3600
  vision_idle_unload_seconds: 300
  vision_max_tokens: 2048
  vision_prompt_mode: qwen3vl
  vision_lm_studio_auto_load: true
```

## Tests

```bash
PYTHONPATH=. python -m pytest -q \
  tests/test_vision_proxy.py \
  tests/test_vision_schema.py \
  tests/test_vision_proxy_cloud_path.py
```

## Related

- [DEEPSEEK_V4_INTEGRATION.md](./DEEPSEEK_V4_INTEGRATION.md)
- [CLOUD-LLM-ARCHITECTURE.md](../CLOUD-LLM-ARCHITECTURE.md)
