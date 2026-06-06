# Requirements — native-vision-intake

## User story

As a user attaching images in chat, I want thumbnails in the UI and the model to receive native multimodal `image_url` input (not RAG embedding or broken base64), with cloud routes using local vision transcription before DeepSeek.

## Acceptance criteria

- [x] **AC-1:** Data URLs without explicit `type` normalize to valid `image_url` blocks (PNG/JPEG/WebP/GIF).
- [x] **AC-2:** Image files skip `file_processor` and Qdrant auto-index; workspace save still occurs.
- [x] **AC-3:** Chat UI shows image thumbnails in composer chips and user message bubbles.
- [x] **AC-4:** `complex-cloud` + image uses `vision_proxy`; proxy failure falls back to `complex-vision`.
- [x] **AC-5:** Docs describe Qwen main GGUF + `mmproj` and nomic embed scope.
