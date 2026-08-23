# Changelog — Model Consolidation, MXBAI Embedding & Vision Proxy Upgrades

**Date:** 2026-08-22  
**Status:** Completed & Fully Tested

## Summary of Changes

1. **Unified Local Model (`google/gemma-4-26b-a4b-qat`)**:
   - Consolidated `models.small`, `models.complex_local`, and local fallback to `google/gemma-4-26b-a4b-qat`.
   - Replaces the separate router model with the 26B unified local model for classification, direct replies, memory extraction, chat title generation, and complex local compute.
   - Updated `src/agent/model_swap.py` to prevent redundant unloading when `small_key == pentest_key`.

2. **Vision Proxy Architecture (`baidu.unlimited-ocr`)**:
   - `baidu.unlimited-ocr` configured as the dedicated vision/OCR proxy model in LM Studio.
   - Images and screenshots are transcribed to structured markdown/text before passing context to Gemma 4 26B (local) or DeepSeek V4 (cloud).

3. **Embedding Model & Vector DB (1024-dim MXBAI)**:
   - Upgraded embedding model from 768-dim to `text-embedding-mxbai-embed-large-v1` (1024 dimensions).
   - Dynamic `VECTOR_TYPE = Vector(1024)` in `src/memory/db_models.py`.
   - Created and applied Alembic migration `b2c3d4e5f6a7_update_embedding_dims_1024.py` altering `memory_vectors`, `engagement_vectors`, and `semantic_cache` pgvector columns to `vector(1024)` with cosine IVFFlat indices.
   - Updated `defaults.yaml` and Qdrant collection configurations to 1024 dimensions.

4. **Test Suite Verification**:
   - 1,059 Python unit, property, and integration tests passed.
   - 131 Vitest frontend tests passed.
   - Electron desktop app build and package completed successfully.
