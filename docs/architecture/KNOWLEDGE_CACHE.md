# Knowledge Cache System

> **Last updated:** 2026-06-06
> **Status:** Active
> **Category:** architecture

## Overview

The **Knowledge Cache** is a specialized, fast-access memory layer designed to intercept redundant factual questions from the user and answer them directly from previously stored context, bypassing the need to invoke external tools like `web_search` or `file_ops`.

By securely isolating long-term knowledge on a per-thread and per-project basis, the system ensures that:
1. Agent responses to previously asked queries are lightning-fast.
2. Token usage and external API calls (e.g., SearxNG) are minimized.
3. Information retrieval remains sandboxed to the active workspace to prevent context bleeding.

## Architecture & Flow

The Knowledge Cache is deeply integrated into the state graph of the agent.

1. **Storage (Mem0 / Qdrant):**
   - Facts, URLs, and summaries retrieved from prior interactions are asynchronously stored as vectorized text via the Mem0 abstraction layer backed by Qdrant.
2. **Retrieval (`memory_inject_node`):**
   - Upon a new message, the `memory_inject_node` intercepts the query and performs a semantic search. 
   - The result is populated into the `knowledge_context` state variable.
   - For performance, this context is cached locally using a time-to-live (TTL) approach (managed by `MemoryContextCache`).
3. **Routing (`router_node`):**
   - The small routing LLM determines whether a query is simple or complex. 
   - The router prompt explicitly commands the model: *"If the requested factual information is fully answered by the provided Knowledge Cache, DO NOT include web_search."*
4. **Execution (`complex_llm_node`):**
   - The `complex_llm_node` acts as the primary executor.
   - It receives the `COMPLEX_PROMPT` which directly injects the `{knowledge_context}`.
   - Even if the router accidentally includes toolboxes, the system prompts the complex node: *"If the requested factual information is fully answered by the provided Knowledge Cache or User Memory, DO NOT use web_search. Only use web_search if the stored context is incomplete or outdated."*
   - As a result, the model can natively respond with `Tool calls: []` and provide the answer immediately.

## Tool Discipline & Bypassing Tools

Previously, the system enforced a strict deterministic "Tool Discipline" logic where any complex request mapped to a toolbox (e.g., `web_search`) would physically append an override instruction telling the LLM it "MUST EMIT A VALID JSON TOOL_CALL IN THIS TURN." 

This forced logic has been removed. The agent is now trusted to read its `knowledge_context` block. If the answer exists within the block, the agent is expected to synthesize an answer directly. This guarantees the Knowledge Cache serves its intended function without getting overridden by rigid tool execution rules.

## Cache Invalidation

The `MemoryContextCache` explicitly keys memories to `thread_id:project_id`. When a project changes or new facts are written to long-term memory via the `memory_write_node`, the cache is instantly invalidated to ensure real-time accuracy and semantic coherence.
