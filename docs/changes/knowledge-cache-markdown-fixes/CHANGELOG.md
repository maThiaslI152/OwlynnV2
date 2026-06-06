# Knowledge Cache Fixes and Markdown Reduction

> **Date:** 2026-06-06

## Summary

This update fixes an issue where the `complex_llm` node forced a tool call even when the answer was already present in the agent's Knowledge Cache. Additionally, strict system prompts have been added to drastically reduce markdown formatting usage across all models to save on token output costs.

## Changes

1. **Knowledge Cache Logic Fix**: Removed the rigid `_TOOL_CALL_DISCIPLINE` override block in `complex.py` that forced tool calls when a toolbox (e.g. `web_search`) was present. The complex node now properly respects the `knowledge_context` cache injection.
2. **Knowledge Cache Documentation**: Added comprehensive documentation for the Knowledge Cache architecture in `docs/architecture/KNOWLEDGE_CACHE.md`.
3. **Markdown Reduction Constraints**: Appended new guidelines to `COMPLEX_PROMPT` (in `complex.py`) and `SIMPLE_PROMPT` (in `simple.py`) instructing the models to "Minimize markdown formatting (headers, bolding, heavy bullet lists) to save output tokens. Use plain text where possible."
4. **Evaluation Updates**: Updated the Frontier Evaluation script (`scripts/run_local_frontier_eval.py`) to strictly test that the agent outputs exactly 0 tools when retrieving from memory, ensuring the Knowledge Cache works end-to-end.
5. **Unit Tests**: Updated `test_memory_nodes.py` to assert against the new tuple format returned by `MemoryContextCache`.
