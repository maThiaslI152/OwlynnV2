from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.agent.core.state import AgentState
from src.agent.routing.router import router_node


@pytest.mark.anyio
async def test_vision_route_with_florence_ready():
    """If Florence is ready and cloud is available, route to complex-cloud with vision reasoning."""
    state: AgentState = {
        "messages": [
            HumanMessage(
                content=[
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abc"},
                    },
                ]
            )
        ],
        "web_search_enabled": True,
    }

    with (
        patch("src.agent.routing.router._check_cloud_available", return_value=True),
        patch(
            "src.agent.core.complex_utils.lm_studio_vision.ensure_vision_vlm_loaded",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_load,
    ):
        out = await router_node(state)

    mock_load.assert_called_once()
    assert out["route"] == "complex-cloud"
    assert out["router_metadata"]["reasoning"] == "image_attachment_cloud_proxy"
    assert out["router_metadata"]["features"]["task_category"] in (
        "vision_cloud",
        "vision_fallback",
    )


@pytest.mark.anyio
async def test_vision_route_with_florence_unavailable_falls_back():
    """If Florence fails to load/is unavailable, fallback to complex-cloud vision_fallback."""
    state: AgentState = {
        "messages": [
            HumanMessage(
                content=[
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abc"},
                    },
                ]
            )
        ],
        "web_search_enabled": True,
    }

    with (
        patch("src.agent.routing.router._check_cloud_available", return_value=True),
        patch(
            "src.agent.core.complex_utils.lm_studio_vision.ensure_vision_vlm_loaded",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_load,
    ):
        out = await router_node(state)

    mock_load.assert_called_once()
    assert out["route"] == "complex-cloud"
    assert (
        out["router_metadata"]["reasoning"]
        == "image_attachment_vision_proxy_unavailable"
    )
    assert out["router_metadata"]["features"]["task_category"] in (
        "vision_cloud",
        "vision_fallback",
    )
