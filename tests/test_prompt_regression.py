import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Mock mem0 before importing project modules that may load long-term memory.
sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.graph import build_graph
from src.agent.nodes.memory import memory_inject_node
from src.agent.state import AgentState
from src.agent.llm import LLMPool


SMALL_PROMPT = "Hi! Reply with exactly: SMALL_OK"
COMPLEX_PROMPT = (
    "Design a 3-phase migration plan from monolith to microservices for a 20-person "
    "engineering team, including risks, rollback strategy, and weekly milestones."
)


@pytest.mark.anyio
async def test_prompt_regression_small_route():
    """
    Verifies a small-path style prompt is answered through the simple node.
    """
    LLMPool.clear_test_overrides()

    mock_simple_llm = AsyncMock()
    mock_simple_llm.bind = MagicMock(return_value=mock_simple_llm)
    mock_simple_llm.ainvoke.return_value = AIMessage(content="SMALL_OK")

    LLMPool.set_test_overrides({"small": mock_simple_llm})
    try:
        app = build_graph().compile()

        with patch("src.agent.nodes.memory.get_profile", return_value={}), \
             patch("src.agent.nodes.memory.get_persona_by_id", return_value={"id": "default", "name": "Owlynn", "role": "assistant", "tone": "friendly", "instructions": ""}), \
             patch("src.agent.nodes.memory.get_memory_context_for_prompt", return_value=""), \
             patch("src.agent.nodes.memory.record_conversation", return_value=None), \
             patch("src.memory.long_term.memory", None):
            state: AgentState = {
                "messages": [HumanMessage(content=SMALL_PROMPT)],
                "thread_id": "prompt-reg-small",
            }
            result = await app.ainvoke(
                state,
                config={"configurable": {"thread_id": "prompt-reg-small"}},
            )
    finally:
        LLMPool.clear_test_overrides()

    assert result["route"] == "simple"
    assert result["model_used"] == "small-local"
    assert result["messages"][-1].content == "SMALL_OK"


@pytest.mark.anyio
async def test_prompt_regression_complex_route():
    """
    Verifies a complex planning prompt routes to the large-model path.
    """
    LLMPool.clear_test_overrides()

    mock_router_llm = AsyncMock()
    mock_router_llm.bind = MagicMock(return_value=mock_router_llm)
    mock_router_llm.ainvoke.return_value = AIMessage(content='{"routing": "complex", "confidence": 0.99}')

    mock_bound = AsyncMock()
    mock_bound.bind = MagicMock(return_value=mock_bound)
    mock_bound.ainvoke.return_value = AIMessage(
        content="Phase 1, Phase 2, Phase 3 with risks and rollback."
    )
    mock_large_base = MagicMock()
    mock_large_base.bind = MagicMock(return_value=mock_bound)
    mock_large_base.bind_tools = MagicMock(return_value=mock_bound)

    LLMPool.set_test_overrides({"small": mock_router_llm, "default": mock_large_base})
    try:
        app = build_graph().compile()

        with patch("src.agent.nodes.memory.get_profile", return_value={}), \
             patch("src.agent.nodes.memory.get_persona_by_id", return_value={"id": "default", "name": "Owlynn", "role": "assistant", "tone": "friendly", "instructions": ""}), \
             patch("src.agent.nodes.memory.get_memory_context_for_prompt", return_value=""), \
             patch("src.agent.nodes.memory.record_conversation", return_value=None), \
             patch("src.memory.long_term.memory", None):
            state: AgentState = {
                "messages": [HumanMessage(content=COMPLEX_PROMPT)],
                "thread_id": "prompt-reg-complex",
            }
            result = await app.ainvoke(
                state,
                config={"configurable": {"thread_id": "prompt-reg-complex"}},
            )
    finally:
        LLMPool.clear_test_overrides()

    assert result["route"].startswith("complex")
    assert result["model_used"] == "medium-default"
    assert "Phase 1" in result["messages"][-1].content


@pytest.mark.anyio
async def test_prompt_regression_memory_injection():
    """
    Verifies memory context returned by personal-assistant memory is injected.
    """
    marker = "preferred deploy region is ap-southeast-1"
    state: AgentState = {
        "messages": [HumanMessage(content="What deploy region do I prefer?")],
        "thread_id": "prompt-reg-memory",
    }

    with patch("src.agent.nodes.memory.get_profile", return_value={"name": "Tim"}), \
         patch("src.agent.nodes.memory.get_persona_by_id", return_value={"id": "default", "name": "Owlynn", "role": "helpful assistant", "tone": "friendly", "instructions": ""}), \
         patch("src.agent.nodes.memory.get_memory_context_for_prompt", return_value=marker), \
         patch("src.memory.long_term.memory", None):
        result = await memory_inject_node(state)

    assert "memory_context" in result
    assert marker in result["memory_context"]
    assert "helpful assistant" in result["persona"]
