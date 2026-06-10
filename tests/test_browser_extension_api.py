import asyncio
import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.api.routes.browser_extension import (
    active_connections,
    is_extension_connected,
    dispatch_extension_search,
)
from src.tools.web_tools import web_search


def test_extension_websocket_lifecycle():
    """Test that the WebSocket registers and unregisters connection status correctly."""
    client = TestClient(app)

    # Ensure no connection initially
    active_connections.clear()
    assert not is_extension_connected()

    # Connect and assert active status
    with client.websocket_connect("/api/browser_extension/ws") as ws:
        assert is_extension_connected()

    # Disconnect and assert offline status
    assert not is_extension_connected()


@pytest.mark.asyncio
async def test_dispatch_extension_search_success():
    """Test that dispatch_extension_search correctly pushes jobs and awaits replies asynchronously."""
    from unittest.mock import AsyncMock
    from src.api.routes.browser_extension import pending_searches

    # Mock WebSocket client
    mock_ws = AsyncMock()

    # When server sends json, simulate extension responding after a micro-delay
    async def mock_send_json(payload):
        req_id = payload["id"]

        # Trigger background resolution of the future matching this request ID
        async def resolve_future():
            await asyncio.sleep(0.02)
            if req_id in pending_searches:
                pending_searches[req_id].set_result(
                    [
                        {
                            "title": "Brave Search Result",
                            "href": "https://brave.com",
                            "body": "Brave browser search results content",
                        }
                    ]
                )

        asyncio.create_task(resolve_future())

    mock_ws.send_json = mock_send_json
    active_connections.clear()
    active_connections.append(mock_ws)

    try:
        results = await dispatch_extension_search(
            "https://www.google.com/search?q=test"
        )
        assert len(results) == 1
        assert results[0]["title"] == "Brave Search Result"
        assert results[0]["href"] == "https://brave.com"
        assert results[0]["body"] == "Brave browser search results content"
    finally:
        active_connections.clear()


@pytest.mark.asyncio
async def test_extension_search_fails_gracefully_when_offline():
    """Test that if the extension is offline, web_search falls back to standard tiers."""
    active_connections.clear()
    assert not is_extension_connected()

    from unittest.mock import patch
    from src.tools.web_tools import SearchAttempt

    # Mock wttr.in and curl_cffi to prevent actual network calls
    with (
        patch("src.tools.web_tools._web_search_wttr_in", return_value=None),
        patch("src.tools.web_tools._web_search_curl_cffi") as mock_curl,
    ):
        # Configure mock to return None to force standard fallbacks
        mock_curl.return_value = (None, SearchAttempt("tier1", "curl_cffi", "empty"))

        # Invoke search; since extension is offline it should bypass tier0.2 and hit tier1
        await web_search.ainvoke({"query": "python programming", "backend": "auto"})

        # Verify extension search (tier0.2) wasn't successful and curl was called
        mock_curl.assert_called()
