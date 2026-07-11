---
status: active
category: changelog
audience: agent
last_updated: 2026-07-10
---

# Phase 5: Ollama Integration

## 2026-07-10 — Added Ollama as an alternative local LLM provider

### What

We added support for Ollama as an alternative local LLM provider alongside LM Studio.

- Added `models.provider` key in `defaults.yaml` which accepts `"lm_studio"` (default) or `"ollama"`.
- Ollama configuration defaults to `http://127.0.0.1:11434/v1` base URL.
- The system now routes requests for small/fallback models and the dedicated pentest model dynamically to the correct provider port (1234 for LM Studio, 11434 for Ollama).
- Reconfigured `mem0` embedder in `long_term.py` to use Ollama when active.
- Routed Nomic embedding API calls to the correct provider endpoint in `tool_reranker.py`.
- Bypassed LM Studio specific behavior (idle model unload, model swap logic, and vision model loading) when using Ollama.

### Why

LM Studio has been the default backend, but Ollama provides a popular, lightweight alternative for running local models on macOS/Linux. By abstracting the provider layer, we give users the flexibility to choose their preferred backend while preserving all of OwlynnV2's local capabilities (routing, semantic search, vision proxy, pentest mode). Bypassing LM Studio-specific logic ensures stability and prevents errors when Ollama is active.

### Files

- `src/config/defaults.yaml` — Config schema additions
- `src/agent/llm.py` — Dynamic routing
- `src/memory/long_term.py` — Embedder reconfiguration
- `src/agent/tool_reranker.py` — Embedding API endpoint routing
- `src/api/idle_manager.py` — Idle unload bypass
- `src/agent/model_swap.py` — Model swap logic bypass
- `src/agent/core/complex_utils/lm_studio_vision.py` — Vision model load bypass
