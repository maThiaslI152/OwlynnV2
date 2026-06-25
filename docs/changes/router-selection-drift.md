# Router Selection Drift Fix

**Date:** June 2026

## Overview
This update refines the `gemma-4-e2b` router's pre-classification keyword gates and system prompt to prevent casual conversational chatter and simple acknowledgments from unnecessarily triggering the complex/cloud pipeline, which historically resulted in wasted tokens and increased latency.

## Key Changes

### 1. Pre-classification Keyword Gates
- **Expanded Casual Chatter Recognition:** Evolved the deterministic `_greeting_phrases` block in `src/agent/routing/router.py` into a broader `_casual_chatter_phrases` collection containing acknowledgments (e.g., `"ok"`, `"cool"`, `"got it"`, `"awesome"`, `"makes sense"`).
- **Conversational Regex Update:** Updated the deterministic `_casual_chatter_pattern` to intercept short conversational praises (e.g., `"you're awesome"`, `"that is cool"`) and route them immediately to the `simple` path, bypassing the LLM entirely.

### 2. Prompt and Heuristic Refinements
- **LLM Prompt Definition:** Explicitly redefined the `simple` classification constraint within `ROUTER_PROMPT` to include "casual chatter, acknowledgements (ok, got it, cool), and short conversational praises".
- **Question Heuristic Relaxation:** Relaxed the deterministic question override heuristic (which forces any input with a question mark into the `complex` path). Conversational questions like `"what do you think?"`, `"are you sure?"`, and `"make sense?"` are now safely exempted.

### 3. Documentation Cleanup
- **Deprecated Model References:** Removed the final outdated references to the legacy `minicpm5-1b` router model in `docs/FUTURE_WORKS.md`, fully aligning the documentation with the recent `gemma-4-e2b` architecture consolidation.
