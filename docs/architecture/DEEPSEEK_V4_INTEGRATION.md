# DeepSeek V4 Architecture Inversion: Implementation Details

**Date:** 2026-06-07
**Status:** Implemented

This document summarizes the architectural shifts made to integrate DeepSeek V4 as the primary cloud workhorse while repurposing local models as fast, lightweight routers and pre-processors.

---

## 1. Local Router as a "Planner"
Previously, the system relied heavily on local models to process requests end-to-end, escalating to the cloud only occasionally. This logic has been **inverted**:
- The local Qwen model (`models.medium`) now acts primarily as the **Router & Planner**.
- We updated the `ROUTER_PROMPT` to not only categorize the message but also generate a strict JSON `execution_plan`.
- This `execution_plan` (e.g., `"1. Use web_search to find X, 2. Run Python code Y"`) is seamlessly injected into the context of DeepSeek V4.
- DeepSeek V4 acts as the high-capacity "Workhorse," strictly executing the plan provided by the local router.

## 2. Vision-to-Text Proxy
DeepSeek V4 is highly capable but does not natively process images. To resolve this, we implemented a **Vision Proxy**:
- When a user uploads an image and the request is routed to `complex-cloud`, the proxy (`src/agent/nodes/complex_utils/vision_proxy.py`) intercepts the message.
- The proxy spins up the local Qwen Vision model to perfectly transcribe the image in detail.
- It then injects this rich transcription directly into the text prompt sent to DeepSeek. DeepSeek now "sees" the image through the eyes of the local model without triggering multimodal API errors.

## 3. DeepSeek V4 API Optimization
We optimized the cloud API calls to match DeepSeek's best practices:
- **Strict JSON mode**: We enabled `strict=True` inside LangChain's `bind_tools`. This forces DeepSeek to output structurally perfect JSON arguments for tool calls, effectively eliminating tool hallucination.
- **Thinking Mode**: Enabled `<think>` logic via the `extra_body` payload (`thinking_mode: true`) to ensure DeepSeek V4 engages in advanced reasoning before outputting tool executions.

## 4. Context Window & File Attachment Expansion
Because DeepSeek V4 supports massive context windows:
- We expanded the `CLOUD_CONTEXT` limit in `defaults.yaml` to **1 Million Tokens**.
- We updated `build_message_content()` in `src/api/shared.py` so that any text, code, or CSV files uploaded by the user are **inlined directly into the prompt**.
- Previously, the agent was forced to read uploaded files via the `read_workspace_file` tool. Now, it has instantaneous access to the entire file contents natively in its context.

## 5. Deterministic PII Anonymizer
To protect user privacy when data is sent to the cloud:
- The PII Anonymizer previously replaced sensitive data (emails, API keys) with incrementing counters (e.g., `[EMAIL_1]`).
- This was updated to use **Deterministic SHA-256 Hashing** (e.g., `[EMAIL_a4f2b9]`).
- This guarantees that the exact same API key or email gets the exact same placeholder across multi-turn stateless API calls, ensuring DeepSeek's context remains consistent.

## 6. Note on LangGraph Orchestration
During this integration, we considered updating the core `src/agent/graph.py` to use LangGraph 1.2+ implicit `Command(goto=...)` objects. However, we opted to explicitly retain the `add_conditional_edges` architecture. 

The current orchestration layer handles highly complex fallback loops (e.g., rate limits, tool denials, circuit breakers, and HITL security gates). Keeping the state machine topology explicitly visible and centralized in `graph.py` is safer and more reliable than burying the routing logic implicitly inside 15+ individual nodes. 
