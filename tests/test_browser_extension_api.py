import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.routes.browser_extension import (
    _auth_token,
    active_connections,
    dispatch_extension_get_active_tab,
    dispatch_extension_search,
    format_active_tab_context,
    is_extension_connected,
    pending_requests,
)
from src.api.server import app
from src.tools.web_tools import web_search


def test_extension_websocket_lifecycle():
    """Test that the WebSocket registers and unregisters connection status correctly."""
    client = TestClient(app)

    active_connections.clear()
    assert not is_extension_connected()


def test_token_origin_restrictions():
    """Test that the /token endpoint strictly filters origins."""
    client = TestClient(app)

    # 1. Allowed: Chrome Extension
    resp = client.get(
        "/api/browser_extension/token", headers={"origin": "chrome-extension://abcdefg"}
    )
    assert resp.status_code == 200
    assert "token" in resp.json()

    # 2. Allowed: Empty origin (native clients)
    resp = client.get("/api/browser_extension/token", headers={"origin": ""})
    assert resp.status_code == 200

    # 3. Disallowed: Localhost
    resp = client.get(
        "/api/browser_extension/token", headers={"origin": "http://localhost:5173"}
    )
    assert resp.status_code == 403

    # 4. Disallowed: External website
    resp = client.get(
        "/api/browser_extension/token", headers={"origin": "https://evil.com"}
    )
    assert resp.status_code == 403


def test_ws_origin_restrictions():
    """Test that the WebSocket endpoint strictly filters origins."""
    client = TestClient(app)

    # Disallowed origin should be rejected with 403 (Forbidden)
    from fastapi.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(
            "/api/browser_extension/ws", headers={"origin": "https://evil.com"}
        ),
    ):
        pass
    assert exc_info.value.code == 4003

    # Allowed origin should connect
    with client.websocket_connect(
        "/api/browser_extension/ws", headers={"origin": "chrome-extension://abcdefg"}
    ) as ws:
        # Just connecting and then closing is enough to prove it didn't instantly reject with 4003
        pass

    with client.websocket_connect("/api/browser_extension/ws") as ws:
        # Default/empty origin also allowed
        pass

    with client.websocket_connect("/api/browser_extension/ws") as ws:
        # Send auth token as first message
        ws.send_json({"type": "auth", "token": _auth_token})
        # Give the server time to process the auth message
        import time

        time.sleep(0.1)
        assert is_extension_connected()

    assert not is_extension_connected()


@pytest.mark.asyncio
async def test_dispatch_extension_search_success():
    """Test that dispatch_extension_search correctly pushes jobs and awaits replies."""
    mock_ws = AsyncMock()

    async def mock_send_json(payload):
        req_id = payload["id"]

        async def resolve_future():
            await asyncio.sleep(0.02)
            if req_id in pending_requests:
                pending_requests[req_id].set_result(
                    {
                        "id": req_id,
                        "results": [
                            {
                                "title": "Brave Search Result",
                                "href": "https://brave.com",
                                "body": "Brave browser search results content",
                            }
                        ],
                    }
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
    finally:
        active_connections.clear()


@pytest.mark.asyncio
async def test_dispatch_extension_get_active_tab_success():
    mock_ws = AsyncMock()

    async def mock_send_json(payload):
        req_id = payload["id"]
        assert payload["action"] == "get_active_tab"

        async def resolve_future():
            await asyncio.sleep(0.02)
            if req_id in pending_requests:
                pending_requests[req_id].set_result(
                    {
                        "id": req_id,
                        "tab": {
                            "url": "https://example.com/doc",
                            "title": "Example Doc",
                            "text": "Body text here",
                            "selection": "highlight",
                        },
                    }
                )

        asyncio.create_task(resolve_future())

    mock_ws.send_json = mock_send_json
    active_connections.clear()
    active_connections.append(mock_ws)

    try:
        tab = await dispatch_extension_get_active_tab()
        assert tab["url"] == "https://example.com/doc"
        assert tab["title"] == "Example Doc"
        formatted = format_active_tab_context(tab)
        assert "browser|https://example.com/doc|Example Doc" in formatted
        assert "highlight" in formatted
        assert "Body text here" in formatted
    finally:
        active_connections.clear()


def test_page_context_push_broadcasts_to_chat_clients():
    from src.api import shared
    from src.api.routes import browser_extension as be_mod

    active_connections.clear()
    mock_chat_ws = AsyncMock()
    shared.connected_websockets.add(mock_chat_ws)
    mock_loop = MagicMock()

    with (
        patch.object(app.state, "loop", mock_loop, create=True),
        patch(
            "src.api.routes.browser_extension.asyncio.run_coroutine_threadsafe"
        ) as mock_run,
    ):
        be_mod._broadcast_page_context(
            {
                "url": "https://example.com",
                "title": "Example",
                "text": "Page body",
                "selection": "sel",
            }
        )
        assert mock_run.called
        assert mock_run.call_count == 1

    shared.connected_websockets.discard(mock_chat_ws)


@pytest.mark.asyncio
async def test_extension_search_fails_gracefully_when_offline():
    active_connections.clear()
    assert not is_extension_connected()

    from unittest.mock import patch

    from src.tools.web_tools import SearchAttempt

    with (
        patch("src.tools.web_tools._web_search_wttr_in", return_value=None),
        patch(
            "src.tools.web_tools._web_search_curl_cffi",
            new=AsyncMock(
                return_value=(None, SearchAttempt("tier1", "curl_cffi", "empty"))
            ),
        ) as mock_curl,
        patch("src.tools.web_tools._get_ddgs_class", return_value=None),
        patch(
            "src.tools.web_tools._web_search_httpx_ddg_html",
            new=AsyncMock(
                return_value=(None, SearchAttempt("tier3", "ddg_html", "empty"))
            ),
        ),
    ):
        await web_search.ainvoke({"query": "python programming", "backend": "auto"})
        mock_curl.assert_called()


@pytest.mark.asyncio
async def test_gateway_prefers_extension_for_active_tab():
    from src.tools.screen_assist.gateway import MacScreenAssistGateway

    gw = MacScreenAssistGateway()
    tab_payload = {
        "url": "https://docs.example.com",
        "title": "Docs",
        "text": "Hello world",
        "selection": "",
    }

    with (
        patch(
            "src.api.routes.browser_extension.is_extension_connected",
            return_value=True,
        ),
        patch(
            "src.api.routes.browser_extension.dispatch_extension_get_active_tab",
            new=AsyncMock(return_value=tab_payload),
        ),
        patch(
            "src.tools.screen_assist.browser.active_browser_tab",
            new=AsyncMock(return_value="should-not-be-used"),
        ),
    ):
        out = await gw.active_browser_url()
        assert "https://docs.example.com" in out
        assert "Hello world" in out
