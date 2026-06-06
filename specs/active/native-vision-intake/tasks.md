# Tasks — native-vision-intake

## Implementation

- [x] **Task 1:** `attachment_intake.py` + refactor `build_message_content` / ws handler
- [x] **Task 2:** Frontend MIME + `ChatMessage.attachments` + thumbnail UI
- [x] **Task 3:** Skip RAG for vision files (`file_processor`, `files.py`, `vector_lifecycle`)
- [x] **Task 4:** Harden `vision_proxy` + complex route fallback + audit `vision_intake_mode`
- [x] **Task 5:** Tests + docs (`lm_studio.md`, `dev-startup.md`, `CHAT_PROTOCOL.md`)

## verify_steps

- [x] `pytest tests/test_attachment_intake.py tests/test_file_processor_images.py tests/test_lm_studio_compat_vision.py tests/test_vision_proxy.py -m "not network"`
- [x] `./scripts/ci.sh --quick`
