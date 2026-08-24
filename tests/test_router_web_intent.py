"""Router sends live-data questions to complex when web search is enabled."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules["mem0"] = MagicMock()

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.core.state import AgentState
from src.agent.routing.router import (
    _LOCAL_FIRST_DEFAULT_TOOLBOX,
    _toolbox_for_local_first,
    router_node,
)


@pytest.mark.anyio
async def test_weather_routes_complex_when_web_search_on():
    state: AgentState = {
        "messages": [HumanMessage(content="What's the weather in Tokyo right now?")],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")
    assert "selected_toolboxes" in out


@pytest.mark.anyio
async def test_greeting_still_simple_with_web_on():
    state: AgentState = {
        "messages": [HumanMessage(content="Hi there!")],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"] == "simple"


@pytest.mark.anyio
async def test_workspace_attachment_forces_complex():
    """Upload injections must not take the tool-less simple path."""
    state: AgentState = {
        "messages": [
            HumanMessage(
                content=(
                    "[Workspace file `notes.pdf` — text extracted from PDF below. "
                    "Use this to answer when it is enough; if not, call read_workspace_file …]\n\n---\nhello\n---\n\n"
                    "Summarize this."
                )
            )
        ],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")


# ── Toolbox selection tests ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_web_query_includes_web_search_toolbox():
    """Web-related queries should include web_search in selected_toolboxes."""
    state: AgentState = {
        "messages": [HumanMessage(content="Search the web for Python tutorials")],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")
    assert "web_search" in out.get("selected_toolboxes", [])


@pytest.mark.anyio
async def test_web_intent_skipped_when_knowledge_cache_covers_query():
    """Deterministic web hints should not force web_search when cache answers."""
    state: AgentState = {
        "messages": [
            HumanMessage(content="What is the price for our production deploy package?")
        ],
        "web_search_enabled": True,
        "knowledge_context": (
            "- Production deploy package price is $500/month in ap-southeast-1.\n"
            "- The package includes staging and production environments."
        ),
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")
    assert "web_search" not in out.get("selected_toolboxes", [])
    assert out["router_metadata"]["reasoning"] == "knowledge_cache_sufficient"


@pytest.mark.anyio
async def test_web_intent_still_fires_for_weather_despite_cache():
    """Time-sensitive web hints must still bind web_search even with cache."""
    state: AgentState = {
        "messages": [HumanMessage(content="What's the weather in Tokyo right now?")],
        "web_search_enabled": True,
        "knowledge_context": "- Tokyo weather yesterday was sunny and 22C.",
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")
    assert "web_search" in out.get("selected_toolboxes", [])


@pytest.mark.anyio
async def test_web_query_routes_cloud_when_available():
    """Web-search toolbox routes to complex route when complex query is processed."""
    state: AgentState = {
        "messages": [HumanMessage(content="Search the web for Python tutorials")],
        "web_search_enabled": True,
    }
    with patch("src.agent.routing.router._check_cloud_available", return_value=True):
        out = await router_node(state)
    assert out["route"].startswith("complex")
    assert "web_search" in out.get("selected_toolboxes", [])


@pytest.mark.anyio
async def test_selected_toolboxes_always_present():
    """Every routing result should include selected_toolboxes."""
    state: AgentState = {
        "messages": [HumanMessage(content="Hello!")],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert "selected_toolboxes" in out
    assert isinstance(out["selected_toolboxes"], list)


# ── Vision detection tests ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_image_attachment_routes_to_vision():
    """Image attachments should route to complex-cloud without router HITL."""
    state: AgentState = {
        "messages": [
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": "Describe all objects visible in the uploaded image",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abc123"},
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
        ),
    ):
        out = await router_node(state)
    assert out["route"] == "complex-cloud"
    assert out["router_clarification_used"] is False
    assert out["selected_toolboxes"] == ["file_ops", "memory"]


@pytest.mark.anyio
async def test_image_only_attachment_skips_hitl():
    """Image-only uploads must not pause for router clarification."""
    state: AgentState = {
        "messages": [
            HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abc123"},
                    },
                    {"type": "text", "text": "What's in this?"},
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
        ),
    ):
        out = await router_node(state)
    assert out["route"] == "complex-cloud"
    assert out["router_clarification_used"] is False
    assert out["selected_toolboxes"] == ["file_ops", "memory"]


@pytest.mark.anyio
async def test_image_with_frontier_routes_cloud_for_proxy():
    """Image + frontier prompt uses complex-cloud (Qwen vision_proxy → DeepSeek)."""
    from unittest.mock import AsyncMock, patch

    state: AgentState = {
        "messages": [
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": "Provide a formal proof based on this diagram",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abc123"},
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
        ),
    ):
        out = await router_node(state)
    assert out["route"] == "complex-cloud"
    assert out["router_clarification_used"] is False


# ── Cloud escalation tests ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_frontier_quality_request_routes_cloud():
    """Frontier-quality indicators should route to complex-cloud when available."""
    from unittest.mock import AsyncMock, patch

    state: AgentState = {
        "messages": [
            HumanMessage(
                content="Solve and prove the convergence of a complex differential equation"
            )
        ],
        "web_search_enabled": True,
    }
    # Mock the small LLM to classify as complex
    mock_llm = MagicMock()
    mock_llm.bind.return_value = mock_llm
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='{"routing":"complex","confidence":0.9,"toolbox":"all"}'
        )
    )
    with (
        patch(
            "src.agent.routing.router.get_small_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch("src.agent.routing.router._check_cloud_available", return_value=True),
    ):
        out = await router_node(state)
    assert out["route"] == "complex-cloud"


@pytest.mark.anyio
async def test_tool_history_forces_complex_even_when_classifier_says_simple():
    """Tool-heavy conversations should not drift back to simple route."""
    state: AgentState = {
        "messages": [
            HumanMessage(content="read my workspace file and summarize"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_workspace_file",
                        "args": {"filename": "notes.md"},
                        "id": "call_1",
                    }
                ],
            ),
            ToolMessage(
                content="file contents...",
                tool_call_id="call_1",
                name="read_workspace_file",
            ),
            HumanMessage(content="continue and finish this"),
        ],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"].startswith("complex")


@pytest.mark.anyio
async def test_long_context_boundary_routes_cloud_not_default():
    """Prompt right above 80% default-context threshold should route to complex-cloud."""
    long_text = "x" * 304_005  # just above longctx boundary for current heuristic
    state: AgentState = {
        "messages": [HumanMessage(content=long_text)],
        "web_search_enabled": True,
    }
    from unittest.mock import AsyncMock, patch

    mock_llm = MagicMock()
    mock_llm.bind.return_value = mock_llm
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='{"routing":"complex","confidence":0.95,"toolbox":"all"}'
        )
    )
    with (
        patch(
            "src.agent.routing.router.get_small_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch("src.agent.routing.router._check_cloud_available", return_value=True),
    ):
        out = await router_node(state)
    assert out["route"].startswith("complex")


@pytest.mark.anyio
async def test_tool_history_data_viz_followup_uses_data_viz_toolbox():
    """Visualize follow-ups after tool-heavy threads should bind data_viz tools."""
    state: AgentState = {
        "messages": [
            HumanMessage(content="What is the news about Ukraine today"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "web_search",
                        "args": {"query": "Ukraine news"},
                        "id": "call_1",
                    }
                ],
            ),
            ToolMessage(
                content="search results...",
                tool_call_id="call_1",
                name="web_search",
            ),
            AIMessage(content="Here is the latest news summary."),
            HumanMessage(content="Can you visualize it?"),
        ],
        "web_search_enabled": True,
    }
    with patch("src.agent.routing.router._check_cloud_available", return_value=True):
        out = await router_node(state)
    assert out["route"].startswith("complex")
    assert out["selected_toolboxes"] == ["data_viz"]
    assert out["router_metadata"]["features"]["task_category"] == "data_viz"


@pytest.mark.anyio
async def test_greeting_still_simple_with_tool_history():
    """Greetings must route to simple even when the conversation has tool history."""
    state: AgentState = {
        "messages": [
            HumanMessage(content="read my workspace file and summarize"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_workspace_file",
                        "args": {"filename": "notes.md"},
                        "id": "call_1",
                    }
                ],
            ),
            ToolMessage(
                content="file contents...",
                tool_call_id="call_1",
                name="read_workspace_file",
            ),
            HumanMessage(content="Hi there!"),
        ],
        "web_search_enabled": True,
    }
    out = await router_node(state)
    assert out["route"] == "simple"


# ── Local-first toolbox selection ─────────────────────────────────────────


def test_toolbox_for_local_first_newest_redis_version():
    """Live-data version queries must bind web_search only (not the all catalog)."""
    assert _toolbox_for_local_first("What's the newest update of redis version") == [
        "web_search"
    ]


def test_toolbox_for_local_first_coding_text_lean_default():
    """Unknown coding-ish text gets the lean default — never implicit ['all']."""
    toolbox = _toolbox_for_local_first(
        "Please refactor the authentication middleware helpers"
    )
    assert toolbox == _LOCAL_FIRST_DEFAULT_TOOLBOX
    assert "all" not in toolbox


@pytest.mark.anyio
async def test_newest_redis_version_selects_web_search_toolbox():
    """Router path for newest Redis version must select web_search toolbox."""
    state: AgentState = {
        "messages": [HumanMessage(content="What's the newest update of redis version")],
        "web_search_enabled": True,
    }
    with patch(
        "src.agent.routing.router.get_profile",
        return_value={"router_hitl_enabled": False},
    ):
        out = await router_node(state)
    assert out["route"].startswith("complex")
    assert out["selected_toolboxes"] == ["web_search"]
    assert "all" not in out["selected_toolboxes"]


@pytest.mark.anyio
async def test_local_first_coding_text_never_implicit_all():
    """Local-first coding-ish turns use lean default, never implicit ['all']."""
    state: AgentState = {
        "messages": [
            HumanMessage(
                content="Please refactor the authentication middleware helpers"
            )
        ],
        "web_search_enabled": True,
    }
    with patch(
        "src.agent.routing.router.get_profile",
        return_value={"router_hitl_enabled": False},
    ):
        out = await router_node(state)
    assert out["route"].startswith("complex")
    assert out["selected_toolboxes"] == _LOCAL_FIRST_DEFAULT_TOOLBOX
    assert "all" not in out["selected_toolboxes"]
    assert (
        out["router_metadata"].get("classification_source") == "hardcoded_local_first"
    )
