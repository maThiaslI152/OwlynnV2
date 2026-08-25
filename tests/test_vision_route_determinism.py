from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.agent.core.state import AgentState
from src.agent.routing.router import router_node


@pytest.mark.anyio
async def test_vision_route_local_only_stays_default():
    """Default local_only keeps image turns on complex-default when VLM is ready."""
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
            "src.agent.routing.resolver.get_profile",
            return_value={"cloud_routing_mode": "local_only"},
        ),
        patch(
            "src.agent.core.complex_utils.lm_studio_vision.ensure_vision_vlm_loaded",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_load,
    ):
        out = await router_node(state)

    mock_load.assert_called_once()
    assert out["route"] == "complex-default"
    assert out["router_metadata"]["reasoning"] == "image_attachment"
    assert out["router_metadata"]["features"]["task_category"] == "vision"


@pytest.mark.anyio
async def test_vision_route_cloud_first_when_ready():
    """cloud_first + ready VLM routes images to complex-cloud for vision proxy."""
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
            "src.agent.routing.resolver.get_profile",
            return_value={"cloud_routing_mode": "cloud_first"},
        ),
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
async def test_vision_route_unavailable_honors_local_only():
    """When VLM is unavailable, local_only still stays on complex-default."""
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
            "src.agent.routing.resolver.get_profile",
            return_value={"cloud_routing_mode": "local_only"},
        ),
        patch(
            "src.agent.core.complex_utils.lm_studio_vision.ensure_vision_vlm_loaded",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_load,
    ):
        out = await router_node(state)

    mock_load.assert_called_once()
    assert out["route"] == "complex-default"
    assert (
        out["router_metadata"]["reasoning"]
        == "image_attachment_vision_proxy_unavailable"
    )
    assert out["router_metadata"]["features"]["task_category"] == "vision_fallback"


@pytest.mark.anyio
async def test_vision_route_unavailable_falls_back_cloud_when_allowed():
    """When VLM is unavailable and cloud is allowed, fall back to complex-cloud."""
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
            "src.agent.routing.resolver.get_profile",
            return_value={"cloud_routing_mode": "cloud_first"},
        ),
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
    assert out["router_metadata"]["features"]["task_category"] == "vision_fallback"
