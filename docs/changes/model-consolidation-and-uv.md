# Model Consolidation & uv Migration

**Date:** June 2026

## Overview
This update simplifies the local AI model architecture by consolidating multiple redundant model tiers into a single `models.small` profile and dramatically speeds up local environment setup by replacing standard `pip` and `venv` with the blazing-fast `uv` package manager.

## Key Changes

### 1. Model Consolidation
- **Unified Profile:** Removed the standalone `vision_proxy` and `extraction` config blocks from `defaults.yaml` and the `LLMPool`.
- **Delegation:** `get_extraction_llm()` now directly delegates to the standard `models.small` pool (`gemma-4-e2b-heretic-uncensored-mlx`).
- **Capacity:** Bumped the `models.small` context window to 8192 tokens to comfortably support concurrent reasoning, vision routing, and extraction workflows on the same model.
- **Cleanup:** Eradicated all leftover references to deprecated models (`MiniCPM5`, `minicpm5-1b`, `lfm2.5-1.2b`) across the router, summarizer, and configuration modules.

### 2. uv Migration
- **Script Rewrite:** Fully migrated `setup.sh` and `start.sh` to leverage `uv`.
- **Speed:** Environment creation and dependency installation via `setup.sh` now uses `uv venv` and `uv sync`, reducing setup times from minutes to seconds.
- **Simplicity:** `start.sh` now launches the backend using `uv run python -m uvicorn`, completely eliminating the need to manually execute `source .venv/bin/activate`.

### 3. CI and Test Improvements
- **Frontend Linting:** Addressed strict `react-hooks/set-state-in-effect` violations that were silently degrading the CI pipeline within React effect hooks in `AppShell`, `MemoryPanel`, `StudyPanel`, and `ProjectKnowledgePanel`.
- **Backend Tests:** Refactored runtime profile tests in `test_unified_settings.py` to assert against the newly unified model pool.
