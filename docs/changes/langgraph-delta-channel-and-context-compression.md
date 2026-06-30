# LangGraph Structural Upgrade & Context Compression Fix

**Date:** 2026-06-30
**Category:** Architecture, Performance, Memory Management

## Overview
Following the LangGraph 1.2 package upgrade, Owlynn's core `AgentState` underwent a structural scan and upgrade. The goal was to adopt new performance capabilities for long-running pentest threads and audit the existing context management flow. 

During this scan, a critical bug was uncovered in the `auto_summarize` node which was causing the context window to silently bloat over time.

## 1. DeltaChannel Integration (Performance)

**The Problem:**
By default, LangGraph's checkpointer saves the entire state on every superstep. For the `messages` array, this results in O(N²) storage bloat in the Redis backend. In long-running pentest or research modes where agents emit hundreds of tool messages, network traffic, and text chunks, this overhead caused massive write latency and bloated the checkpointer payload.

**The Solution:**
LangGraph 1.2 introduced `DeltaChannel`, a state channel that stores only the incremental delta (O(N) storage) and periodically writes a full snapshot to bound read latency.

- Modifed `src/agent/core/state.py`.
- Wrapped the `messages` array reducer with `DeltaChannel`:
  ```python
  from langgraph.channels.delta import DeltaChannel
  from langgraph.graph.message import _messages_delta_reducer
  
  class AgentState(TypedDict):
      messages: Annotated[Sequence[BaseMessage], DeltaChannel(_messages_delta_reducer)]
  ```
- **Scope Limit:** Evaluated adopting `DeltaChannel` for other append-only lists like `extracted_facts` and `pending_tool_names` (which use `operator.add`). However, `DeltaChannel` processes chunks as batches, causing list concatenation to nest arrays (`[['A'], ['B']]`) instead of flattening them. Given these arrays hold minimal data, `DeltaChannel` was restricted strictly to the massive `messages` array.

## 2. Auto-Summarizer Critical Bug Fix (Memory Management)

**The Problem:**
The `auto_summarize` node in `src/agent/nodes/summarize.py` is responsible for compressing old context once the token count exceeds 85% of the LLM's context window. 
Historically, the node generated a summary and returned a truncated list of messages:
```python
new_messages = [summary_msg] + protected + recent
return {"messages": new_messages}
```
However, LangGraph's message reducers (like `add_messages` and `_messages_delta_reducer`) **only merge by ID**; they do not explicitly overwrite or delete messages just because they are omitted from the return payload. As a result, the old context was never actually removed from the checkpointer or the active LLM context—the summary message was simply appended to the ever-growing history.

**The Solution:**
To forcefully delete messages in LangGraph, a node must explicitly return a `RemoveMessage` object containing the target ID.
- Patched `summarize.py` to iterate over the `to_summarize` block.
- Explicitly yielded `RemoveMessage(id=msg.id)` for every older message being compressed:
  ```python
  remove_msgs = [RemoveMessage(id=msg.id) for msg in to_summarize if msg.id]
  new_messages = remove_msgs + [summary_msg] + protected + recent
  return {"messages": new_messages}
  ```
- This permanently clears the bloated history from the checkpointer and accurately maintains the LLM's token budget constraint.

## 3. Deferred Upgrades

**LangGraph v3 Streaming:**
LangGraph 1.2 introduced the `v3` streaming API (`stream_mode="messages"`) which emits strictly typed projections (`stream.messages`, `stream.values`, `stream.output`). 

This upgrade was evaluated but **deferred**. The current WebSocket gateway (`src/api/ws/handler.py`) relies heavily on parsing raw `v2` events (`on_chain_start`, `on_chat_model_stream`, etc.) to generate complex UI events, track tool lifecycles, and handle system-instruction stream echoing. A migration to `v3` would require completely rewriting ~150 lines of complex WebSocket mapping logic, carrying an unnecessarily high risk of frontend regressions. We will maintain `version="v2"` streaming indefinitely.
