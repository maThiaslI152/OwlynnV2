# Design — native-vision-intake

## Architecture

```
Composer (type + data URL)
  → ws/handler normalize + save
  → build_message_content → image_url blocks
  → router → complex-vision | complex-cloud
  → Qwen direct multimodal | vision_proxy → DeepSeek
```

## Key modules

| Module | Role |
|--------|------|
| `src/api/attachment_intake.py` | MIME inference, data-URL strip, vision MIME allowlist |
| `src/api/shared.py` | `build_message_content` multimodal assembly |
| `src/api/file_processor.py` | Skip vision extensions (no RAG plaintext) |
| `src/memory/vector_lifecycle.py` | Refuse vision file indexing |
| `src/agent/nodes/complex_utils/vision_proxy.py` | Cloud-only image → text transcription |
| `frontend-v2` | `ChatMessage.attachments`, thumbnail UI |

## RAG vs UI

Images: **no** nomic embed; **yes** workspace file + chat thumbnails.
