---
status: active
category: architecture
last_updated: 2026-06-09
owner: ai-agent
---

# Vision Proxy (Phase 2)

Local VLM acts as an **OCR/layout sensor** for the text-only DeepSeek cloud path. Output is structured JSON — no conversational prose.

## Flow

```text
User image (chat or screen crop)
  → vision_proxy (local VLM, lazy-loaded)
  → JSON: text_blocks, ui_elements, subjects
  → formatted block in cloud prompt (image_url stripped)
  → DeepSeek V4
```

## Modules

| Path | Role |
|------|------|
| `src/agent/nodes/complex_utils/vision_proxy.py` | Transcribe, cache, lazy manager |
| `src/agent/nodes/complex_utils/vision_schema.py` | JSON parse + cloud formatting |
| `src/agent/nodes/complex.py` | `complex-cloud` + images → proxy; failure → `complex-default` |

## Output contract

```json
{
  "text_blocks": [{"text": "exact OCR line", "bbox": null}],
  "ui_elements": [{"role": "button", "label": "Submit"}],
  "subjects": ["terminal", "form"],
  "confidence": 0.92
}
```

Cloud-visible text is a dense bullet block — never raw `image_url` to DeepSeek.

## Lazy load

`VisionModelManager` holds a dedicated Florence-2 client (`models.vision_proxy`). Unloads after `cloud.vision_idle_unload_seconds` (default 300s) with no active transcriptions. Qwen9B+mmproj remains for `complex-default` local multimodal fallback only.

## Screen assist hook (Phase 3)

```python
await transcribe_crop(image_bytes, mime_type="image/png")
```

Used by `src/tools/screen_assist/ax_macos.py` when AX returns no text (512×512 crop). See [screen-assist-phase3.md](../guides/screen-assist-phase3.md).

## Configuration

```yaml
cloud:
  vision_transcription_cache_ttl: 3600
  vision_idle_unload_seconds: 300
  vision_max_tokens: 2048
```

## Tests

```bash
PYTHONPATH=$(pwd) python -m pytest -q \
  tests/test_vision_proxy.py \
  tests/test_vision_schema.py \
  tests/test_vision_proxy_cloud_path.py
```

## Related

- [DEEPSEEK_V4_INTEGRATION.md](./DEEPSEEK_V4_INTEGRATION.md)
- [CLOUD-LLM-ARCHITECTURE.md](../CLOUD-LLM-ARCHITECTURE.md)
