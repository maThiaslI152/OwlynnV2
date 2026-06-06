# native-vision-intake — Changelog

## Task 1 — Attachment normalizer

- Added `src/api/attachment_intake.py` with `normalize_file_attachment`, `VISION_INTAKE_MIMES`.
- Refactored `build_message_content` and WS file save to use normalizer.

## Task 2 — Frontend MIME + UI

- Composer sends `type`; image thumbnail chips.
- `ChatMessage.attachments` with previews in message bubbles.

## Task 3 — RAG exclusion

- `file_processor` skips vision extensions without callback.
- `notify_file_processed` and `VectorLifecycleManager` guard vision files.

## Task 4 — Vision proxy hardening

- `process_vision_messages` returns `(messages, ok)`; failure keeps `image_url`.
- `complex.py` falls back to `complex-vision`; logs `vision_intake_mode`.

## Task 5 — Tests & docs

- Python: `test_attachment_intake`, `test_file_processor_images`, `test_lm_studio_compat_vision`, `test_vision_proxy`.
- Frontend: AppShell image thumbnail regression test.
- Docs: `lm_studio.md`, `dev-startup.md`, `CHAT_PROTOCOL.md`.

## Follow-up — skip router HITL for images

- Early deterministic route in `router.py`: image attachments → `complex-vision` without router clarification popup.
- HITL resolution path re-applies `_resolve_complex_route` when images present (defensive).

## Follow-up — cloud image path (Qwen proxy → DeepSeek)

- `_resolve_complex_route`: image + frontier/long-context + cloud available → `complex-cloud` (not forced local vision).
- `complex.py` `vision_proxy` runs on `complex-cloud`, transcribes via Qwen, merges text into prompt for DeepSeek.
- On proxy failure, falls back to `complex-vision` direct multimodal.

## Follow-up — stop web-search loops on image tasks

- Router image toolbox: `file_ops` + `memory` only (no web_search/deep_research).
- `complex.py`: vision-specific tool guidance; strip web tools on vision routes.
- `scope_clarify`: skip web_search_suggested bypass when image attached.

## Follow-up — LM Studio WebP vision fix

- LM Studio rejects `image/webp` in `image_url` blocks (`url must be base64 encoded image`).
- `lm_studio_safe_image_payload` converts WebP/GIF to JPEG at attachment intake.
- `normalize_messages_for_lm_studio` rewrites existing multimodal blocks before local invoke.
- Text-only fallbacks strip `image_url` blocks so medium-default does not 400-loop.

## Follow-up — Knowledge panel chunk spam

- RAG indexing was registering each chunk as `filename#chunkN` in project.files (looked like duplicates in UI).
- `index_knowledge_document`: one UI row per source file; chunks stored in Mem0 only.
- Migrate/collapse legacy chunk rows on load; frontend also groups by base filename.

## auto-improve loop 2 — Knowledge panel test coverage

- Frontend: regression tests for chunk-row collapse, `workspace_ref` drag payload, and double-click attach in `ProjectKnowledgePanel`.
- Hoist `electronBridge` mock in extended component tests (removes Vitest nested-mock warning).

## auto-improve loop 3 — Shared knowledge file collapse helper

- Extract `knowledgeFiles.ts` (base-name + collapse) used by `ProjectKnowledgePanel`.
- Unit tests mirror Python `test_knowledge_file_list` collapse behavior.
