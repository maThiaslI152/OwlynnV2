"""
Inference Truncation & Auto-Summarization Validation Script.

Executes sequential conversational turns through the LangGraph agent until
active token usage crosses the 85% threshold, triggering the auto_summarize_node,
compacting conversation history with structured summary headers, and continuing inference.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage

from src.agent.core.graph import build_graph, summarize_gate
from src.agent.core.state import AgentState
from src.agent.llm import LLMPool
from src.agent.nodes.summarize import (
    _SUMMARIZE_THRESHOLD,
    _estimate_messages_tokens,
    auto_summarize_node,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inference_truncation_test")


async def run_inference_truncation_test():
    print("=" * 70)
    print("Owlynn Context Truncation & Auto-Summarization Inference Test")
    print("=" * 70)

    # 1. Configure a constrained context window for observable threshold crossing
    context_window = 2000
    threshold = int(_SUMMARIZE_THRESHOLD * context_window)
    print(f"\n[Config] Context Window: {context_window} tokens | Compaction Threshold (85%): {threshold} tokens")

    # 2. Setup mock responses for LLM pool
    mock_summary_response = AIMessage(
        content=(
            "## Topics Discussed\n"
            "- Multi-tier architecture design and database migrations\n"
            "- API gateway routing and security hardening\n\n"
            "## Decisions\n"
            "- Standardized on 4-model architecture (main, vision, pentest, embedding)\n\n"
            "## Facts\n"
            "- Vector dimensions updated to 1024 dims for MXBAI\n"
        )
    )

    mock_llm = AsyncMock()
    mock_llm.bind = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke.return_value = AIMessage(content="Understood, I am tracking this project.")
    
    # Mock summarizer LLM response
    mock_summary_llm = AsyncMock()
    mock_summary_llm.ainvoke.return_value = mock_summary_response

    LLMPool.set_test_overrides({
        "main": mock_llm,
        "small": mock_llm,
        "summarize": mock_summary_llm,
    })

    # 3. Simulate multi-turn inference building up context
    messages = []
    
    print("\n--- Phase 1: Progressive Multi-Turn Inference ---")
    
    turn = 0
    current_tokens = 0
    # Generate turns until exceeding threshold (with at least 12 turns so older messages exist)
    while turn < 12 or current_tokens <= threshold:
        turn += 1
        human_text = (
            f"Turn {turn}: We are discussing module architecture specification #{turn}.\n"
            f"Here are the engineering constraints and code details for component {turn}:\n"
            f"```python\n"
            f"class HighAvailabilityComponent_{turn}:\n"
            f"    def __init__(self, cluster_id: str, replica_count: int = 5):\n"
            f"        self.cluster_id = f'node-{{cluster_id}}-{turn}'\n"
            f"        self.replica_count = replica_count\n"
            f"        self.state_cache = {{'active': True, 'version': {turn}}}\n\n"
            f"    async def execute_task(self, payload: dict) -> dict:\n"
            f"        # Process transactions with strict idempotency\n"
            f"        return {{'status': 'success', 'turn': {turn}, 'hash': hex(hash(str(payload)))}}\n"
            f"```\n"
            f"Please register this architecture decision and ensure cluster failover policies."
        )
        ai_text = (
            f"Acknowledged module #{turn} specification.\n"
            f"HighAvailabilityComponent_{turn} registered successfully. Failover policies configured:\n"
            f"- Quorum consistency across {turn * 2} replica shards\n"
            f"- Health checks active at interval 2500ms\n"
            f"- Automatic checkpoint sync enabled with PostgreSQL backend."
        )
        messages.append(HumanMessage(content=human_text, id=f"msg_turn_{turn}_user"))
        messages.append(AIMessage(content=ai_text, id=f"msg_turn_{turn}_ai"))
        
        current_tokens = _estimate_messages_tokens(messages)
        pct = (current_tokens / context_window) * 100
        print(f"  Turn {turn:2d}: {len(messages):2d} messages | Estimated active tokens: {current_tokens:4d} / {context_window} ({pct:5.1f}%)")

    total_tokens_before = _estimate_messages_tokens(messages)
    print(f"\nTotal tokens before compaction: {total_tokens_before} (Threshold: {threshold})")
    assert total_tokens_before > threshold, f"Tokens {total_tokens_before} should exceed threshold {threshold}"

    # 4. Check summarize_gate decision
    state_before: AgentState = {
        "messages": messages,
        "active_tokens": total_tokens_before,
        "context_window": context_window,
        "thread_id": "test-truncation-thread",
    }
    
    gate_decision = summarize_gate(state_before)
    print(f"\n[Gate Check] summarize_gate(state) -> '{gate_decision}' (Triggered: {gate_decision == 'auto_summarize'})")
    assert gate_decision == "auto_summarize", f"Expected auto_summarize, got {gate_decision}"

    # 5. Execute auto_summarize_node
    print("\n--- Phase 2: Executing Auto-Summarization & Compaction ---")
    with patch("src.agent.nodes.summarize.get_small_llm", return_value=mock_summary_llm):
        summarize_result = await auto_summarize_node(state_before)

    assert summarize_result, "auto_summarize_node should return state updates"
    emitted_messages = summarize_result.get("messages", [])
    
    remove_count = sum(1 for m in emitted_messages if isinstance(m, RemoveMessage))
    system_summaries = [m for m in emitted_messages if isinstance(m, SystemMessage)]
    
    print(f"  [Result] Emitted {len(emitted_messages)} message modifications:")
    print(f"    - RemoveMessage directives: {remove_count} older messages compacted")
    print(f"    - SystemMessage compaction headers injected: {len(system_summaries)}")

    assert remove_count > 0, "Older messages should be removed/compacted"
    assert len(system_summaries) >= 1, "A structured summary header must be injected"

    print("\n[Injected Summary Header Content]:")
    print("-" * 50)
    print(system_summaries[0].content)
    print("-" * 50)

    # 6. Apply compaction updates to conversation history
    # Simulate LangGraph state reducer (applying RemoveMessage by id and appending new SystemMessage)
    removed_ids = {m.id for m in emitted_messages if isinstance(m, RemoveMessage)}
    compacted_history = [m for m in messages if getattr(m, "id", None) not in removed_ids]
    compacted_history = system_summaries + compacted_history

    tokens_after = _estimate_messages_tokens(compacted_history)
    tokens_saved = total_tokens_before - tokens_after
    pct_saved = (tokens_saved / total_tokens_before) * 100

    print(f"\n--- Phase 3: Post-Compaction Analysis ---")
    print(f"  Messages count: {len(messages)} -> {len(compacted_history)}")
    print(f"  Active tokens:  {total_tokens_before} -> {tokens_after} ({pct_saved:.1f}% reduction, {tokens_saved} tokens freed)")
    print(f"  Context ratio:  {(tokens_after / context_window)*100:.1f}% of context window")

    # 7. Verify subsequent inference turn works with compacted state
    print("\n--- Phase 4: Follow-Up Inference on Compacted Context ---")
    followup_msg = HumanMessage(content="What was the decision made regarding vector dimensions?")
    compacted_history.append(followup_msg)
    
    followup_state: AgentState = {
        "messages": compacted_history,
        "active_tokens": _estimate_messages_tokens(compacted_history),
        "context_window": context_window,
        "thread_id": "test-truncation-thread",
    }
    
    gate_decision_after = summarize_gate(followup_state)
    print(f"  [Subsequent Turn Gate Check] summarize_gate(post_state) -> '{gate_decision_after}'")
    assert gate_decision_after == "router", "Compacted state should be below threshold and route directly to router"

    # 8. Execute full LangGraph graph run on overflowing state
    print("\n--- Phase 5: Full LangGraph Graph Execution (End-to-End) ---")
    app = build_graph().compile()
    
    with (
        patch("src.agent.nodes.memory.get_memory_context_for_prompt", return_value=""),
        patch("src.agent.nodes.memory.record_conversation", return_value=None),
        patch("src.memory.long_term.memory", None),
        patch("src.agent.nodes.summarize.get_small_llm", return_value=mock_summary_llm),
    ):
        graph_input: AgentState = {
            "messages": messages,
            "active_tokens": total_tokens_before,
            "context_window": context_window,
            "thread_id": "test-graph-truncation-thread",
        }
        
        graph_output = await app.ainvoke(
            graph_input,
            config={"configurable": {"thread_id": "test-graph-truncation-thread"}},
        )
        
        print(f"  [Full Graph Result]:")
        print(f"    - Route executed: {graph_output.get('route')}")
        print(f"    - Final response: {graph_output['messages'][-1].content}")
        print(f"    - Final message count in graph: {len(graph_output.get('messages', []))}")
        print(f"    - Summarized tokens recorded: {graph_output.get('summarized_tokens')}")
    
    print("\n" + "=" * 70)
    print("SUCCESS: End-to-end inference truncation and compaction verified!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_inference_truncation_test())
