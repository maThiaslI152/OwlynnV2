"""GraphInterrupt from ask_user must not become system_error ToolMessages."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphInterrupt


@pytest.mark.asyncio
async def test_tool_action_reraises_graph_interrupt():
    from src.agent.core.complex_tool_action import complex_tool_action_node

    state = {
        "messages": [
            HumanMessage(content="clarify?"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user",
                        "args": {"question": "Which format?"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
        ],
        "web_search_enabled": True,
        "route": "complex-default",
        "router_metadata": {},
        "selected_toolboxes": ["all"],
    }

    async def _boom(*_a, **_k):
        raise GraphInterrupt(())

    fake_node = MagicMock()
    fake_node.ainvoke = AsyncMock(side_effect=_boom)

    with (
        patch(
            "src.agent.core.complex_tool_action._resolve_complex_tools",
            return_value=[],
        ),
        patch(
            "src.agent.core.complex_tool_action.ToolNode",
            return_value=fake_node,
        ),
        pytest.raises(GraphInterrupt),
    ):
        await complex_tool_action_node(state)
