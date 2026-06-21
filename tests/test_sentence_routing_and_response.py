import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Prevent mem0/chroma bootstrapping during tests.
sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.core.graph import build_graph
from src.agent.core.state import AgentState
from src.agent.llm import LLMPool


SIMPLE_CASES = [
    ("Hi there", "simple", "small-local", "SMALL: greeting"),
    ("Hello, how are you?", "simple", "small-local", "SMALL: greeting"),
    ("Thanks for your help!", "simple", "small-local", "SMALL: greeting"),
]

COMPLEX_CASES = [
    (
        "Design a migration strategy from monolith to microservices with rollout phases.",
        "complex-cloud",
        "large-cloud",
        "LARGE: architecture plan",
    ),
    (
        "Write and explain a Python quicksort implementation with complexity analysis.",
        "complex-cloud",
        "large-cloud",
        "LARGE: architecture plan",
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "sentence,expected_route,expected_model,expected_reply", SIMPLE_CASES
)
async def test_sentence_matrix_simple_route_and_response(
    sentence: str, expected_route: str, expected_model: str, expected_reply: str
):
    LLMPool.clear_test_overrides()

    mock_small_llm = AsyncMock()
    mock_small_llm.bind = MagicMock(return_value=mock_small_llm)
    mock_small_llm.ainvoke.return_value = AIMessage(content=expected_reply)

    LLMPool.set_test_overrides({"small": mock_small_llm})
    try:
        app = build_graph().compile()

        with (
            patch("src.agent.nodes.memory.get_profile", return_value={}),
            patch(
                "src.agent.nodes.memory.get_persona_by_id",
                return_value={
                    "id": "default",
                    "name": "Owlynn",
                    "role": "assistant",
                    "tone": "friendly",
                    "instructions": "",
                },
            ),
            patch(
                "src.agent.nodes.memory.get_memory_context_for_prompt", return_value=""
            ),
            patch("src.agent.nodes.memory.record_conversation", return_value=None),
            patch("src.memory.long_term.memory", None),
        ):
            state: AgentState = {
                "messages": [HumanMessage(content=sentence)],
                "thread_id": "route-simple",
            }
            result = await app.ainvoke(
                state,
                config={"configurable": {"thread_id": "route-simple"}},
            )
    finally:
        LLMPool.clear_test_overrides()

    assert result["route"] == expected_route
    assert result["model_used"] == expected_model
    assert result["messages"][-1].content == expected_reply


@pytest.mark.anyio
@pytest.mark.parametrize(
    "sentence,expected_route,expected_model,expected_reply", COMPLEX_CASES
)
async def test_sentence_matrix_complex_route_and_response(
    sentence: str, expected_route: str, expected_model: str, expected_reply: str
):
    LLMPool.clear_test_overrides()

    # Force router classification for non-keyword complex prompts.
    mock_router_llm = AsyncMock()
    mock_router_llm.bind = MagicMock(return_value=mock_router_llm)
    mock_router_llm.ainvoke.return_value = AIMessage(
        content='{"routing": "complex", "confidence": 0.99}'
    )

    mock_bound = AsyncMock()
    mock_bound.bind = MagicMock(return_value=mock_bound)
    mock_bound.ainvoke.return_value = AIMessage(content=expected_reply)
    mock_large_base = MagicMock()
    mock_large_base.bind = MagicMock(return_value=mock_bound)
    mock_large_base.bind_tools = MagicMock(return_value=mock_bound)

    LLMPool.set_test_overrides({"small": mock_router_llm, "cloud": mock_large_base})
    try:
        app = build_graph().compile()

        with (
            patch(
                "src.agent.routing.router._check_cloud_available", return_value=False
            ),
            patch("src.agent.nodes.memory.get_profile", return_value={}),
            patch(
                "src.agent.nodes.memory.get_persona_by_id",
                return_value={
                    "id": "default",
                    "name": "Owlynn",
                    "role": "assistant",
                    "tone": "friendly",
                    "instructions": "",
                },
            ),
            patch(
                "src.agent.nodes.memory.get_memory_context_for_prompt", return_value=""
            ),
            patch("src.agent.nodes.memory.record_conversation", return_value=None),
            patch("src.memory.long_term.memory", None),
        ):
            state: AgentState = {
                "messages": [HumanMessage(content=sentence)],
                "thread_id": "route-complex",
            }
            result = await app.ainvoke(
                state,
                config={"configurable": {"thread_id": "route-complex"}},
            )
    finally:
        LLMPool.clear_test_overrides()

    assert result["route"] == expected_route
    assert result["model_used"] == expected_model
    assert result["messages"][-1].content == expected_reply
