# Web Search Optimization, Routing Fixes, and Document Generation Skill

**Date:** 2026-06-23
**Category:** Enhancement & Bug Fixes

## 1. Web Search Optimization
- **Problem:** Sequential searches (DuckDuckGo followed by Bing) were causing aggregate timeout limits (60s) to be hit, specifically for complex or non-English queries where one provider might hang or rate-limit.
- **Solution:** Modified `src/tools/web_tools.py` to use `asyncio.gather` for concurrent fetching. Now both providers are queried simultaneously, significantly decreasing latency and eliminating timeout stalls.

## 2. Router Fallback Fix
- **Problem:** When the cloud model (`complex-cloud`) was unavailable, the router `_preferred_complex_route` and fallback logic hardcoded `complex-cloud` as the downgrade target, resulting in a "Cloud unavailable" error without ever properly falling back to the default local model.
- **Solution:** Updated `src/agent/routing/router.py` to properly downgrade to `complex-default` when `cloud_available` is false or when a cloud API call fails. 

## 3. Document Writer Skill
- **Problem:** Generating long multi-page documents caused the LLM to condense information into short, 1-page outlines to respect context output limits.
- **Solution:** Created the `Document Writer` skill (`skills/document_writer.md`) that triggers on document creation requests (e.g., "create docx", "write document"). It explicitly instructs the agent to:
  1. Use the `ask_user` tool (HITL) to clarify scope and get approval on an outline.
  2. Generate the document section-by-section to bypass output token constraints.
  3. Compile the sections into a final `.docx` or `.pdf`.
