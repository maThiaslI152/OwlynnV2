# Changelog: Heavy Local Orchestrator

## 2026-08-11 — Transition to Heavy Local Orchestrator

**What:**
- Bypassed the multi-LLM classification in `src/agent/routing/router.py`. The system now instantly defaults to the `complex` route for all interactions, eliminating the token overhead and latency of routing via a smaller LLM.
- Updated `defaults.yaml` to promote the heavy local model (`gemma4-12b-qat-uncensored-hauhaucs-balanced@q4_k_m`) to the `small` slot. This unifies background tasks (memory extraction) and primary tool execution under the same 12B engine.
- Decoupled vision processing from the `small` slot. Added a dedicated `vision` model slot pointing to `baidu.Unlimited-OCR-GGUF` for strict OCR/vision analysis.
- Rewrote the vision system prompt (`vision_qwen3vl_system`) in `defaults.yaml` to be unbiased and comprehensive, instructing the model to describe visual scenes rather than restricting it to raw text extraction.
- Modified `src/api/server.py` to support explicitly preloading the `vision` model at application startup.

**Why:**
- On high-memory hardware (e.g., M4 Mac with 24GB unified memory), using a small 4B router model unnecessarily segments capabilities and wastes Time-To-First-Token. Running everything through a single, powerful 12B model provides better reliability and reduces architectural complexity while staying entirely local.
- The default Qwen 3 VL system prompt was too restrictive for general vision tasks (like interpreting cartoons or diagrams), so we relaxed it for broader usage.
- Separating the vision model allowed us to leverage Baidu OCR specifically for image uploads without interfering with text orchestration.

**Files:**
- `src/agent/routing/router.py`
- `src/config/defaults.yaml`
- `src/api/server.py`
- `src/agent/core/complex_utils/lm_studio_vision.py`
- `src/agent/core/complex_utils/vision_model_manager.py`
