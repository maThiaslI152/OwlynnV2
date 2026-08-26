"""Regression tests for browser extension security hardening (C1–C4 / search)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.routes.browser_extension import (
    _auth_token,
    _is_allowed_extension_origin,
    active_connections,
    dispatch_extension_fetch_urls,
    pending_requests,
)
from src.api.server import app
from src.tools.web_tools import browser_background_fetch, web_search


def test_token_rejects_empty_and_null_origin():
    """C2: empty / null Origin must not receive the WS token."""
    client = TestClient(app)

    for origin in ("", "null"):
        resp = client.get("/api/browser_extension/token", headers={"origin": origin})
        assert resp.status_code == 403, origin

    # Missing Origin header → treated as empty → reject
    resp = client.get("/api/browser_extension/token")
    assert resp.status_code == 403

    # Valid extension origin still works
    resp = client.get(
        "/api/browser_extension/token",
        headers={"origin": "chrome-extension://abcdefg"},
    )
    assert resp.status_code == 200
    assert resp.json().get("token") == _auth_token


def test_is_allowed_extension_origin_helper():
    assert _is_allowed_extension_origin("chrome-extension://abc") is True
    assert _is_allowed_extension_origin("moz-extension://xyz") is True
    assert _is_allowed_extension_origin("") is False
    assert _is_allowed_extension_origin("null") is False
    assert _is_allowed_extension_origin("http://localhost:5173") is False


def test_ws_rejects_empty_and_null_origin():
    """C2: WebSocket must reject empty / null Origin."""
    from fastapi.websockets import WebSocketDisconnect

    client = TestClient(app)

    for origin in ("", "null"):
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(
                "/api/browser_extension/ws", headers={"origin": origin}
            ),
        ):
            pass
        assert exc_info.value.code == 4003


def test_token_file_permissions_on_generate(tmp_path, monkeypatch):
    """Token file should be written with owner-only mode (0o600)."""
    token_path = tmp_path / "browser_extension_token"
    monkeypatch.setattr("src.api.routes.browser_extension._TOKEN_PATH", token_path)
    from src.api.routes import browser_extension as be

    token = be._generate_auth_token()
    assert token
    assert token_path.is_file()
    mode = token_path.stat().st_mode & 0o777
    assert mode == 0o600


@pytest.mark.asyncio
async def test_fetch_urls_ssrf_blocked_without_dispatch():
    """C4: localhost / private URLs never reach the extension."""
    active_connections.clear()
    mock_ws = AsyncMock()
    active_connections.append(mock_ws)

    try:
        results = await dispatch_extension_fetch_urls(
            [
                "http://127.0.0.1:8000/admin",
                "http://169.254.169.254/latest/meta-data/",
                "http://192.168.1.1/",
            ]
        )
        assert len(results) == 3
        assert all("Blocked" in str(r.get("error", "")) for r in results)
        mock_ws.send_json.assert_not_called()
    finally:
        active_connections.clear()


@pytest.mark.asyncio
async def test_browser_background_fetch_ssrf_message():
    with patch(
        "src.api.routes.browser_extension.is_extension_connected",
        return_value=True,
    ):
        out = await browser_background_fetch.ainvoke(
            {"urls": ["http://localhost/secret"]}
        )
    assert "Blocked" in out
    assert (
        "localhost" in out.lower() or "Hostname" in out or "not allowed" in out.lower()
    )


@pytest.mark.asyncio
async def test_cookie_no_tab_deny_contract():
    """C3 contract: extension returns an error string; backend surfaces empty cookies."""
    mock_ws = AsyncMock()

    async def mock_send_json(payload):
        req_id = payload["id"]
        assert payload["action"] == "get_cookies"

        async def resolve():
            await asyncio.sleep(0.01)
            if req_id in pending_requests:
                pending_requests[req_id].set_result(
                    {
                        "id": req_id,
                        "error": "No active tab for cookie consent — denied by default.",
                    }
                )

        asyncio.create_task(resolve())

    mock_ws.send_json = mock_send_json
    active_connections.clear()
    active_connections.append(mock_ws)

    from src.api.routes.browser_extension import dispatch_extension_get_cookies

    try:
        cookies = await dispatch_extension_get_cookies("https://example.com/")
        # dispatch_extension_get_cookies returns "" on missing cookies key
        assert cookies == ""
    finally:
        active_connections.clear()


@pytest.mark.asyncio
async def test_captcha_empty_results_falls_through_search_tiers():
    """CAPTCHA hard-failure (empty hits) must not poison Tier 0.2 as success."""
    from src.tools.web_tools import SearchAttempt

    with (
        patch(
            "src.api.routes.browser_extension.is_extension_connected",
            return_value=True,
        ),
        patch(
            "src.api.routes.browser_extension.dispatch_extension_search",
            new=AsyncMock(return_value=[]),  # captcha → empty
        ),
        patch("src.tools.web_tools._web_search_wttr_in", return_value=None),
        patch(
            "src.tools.web_tools._web_search_curl_cffi",
            new=AsyncMock(
                return_value=(
                    "fallback results from curl",
                    SearchAttempt("tier1", "curl_cffi", "ok"),
                )
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
        out = await web_search.ainvoke(
            {"query": "python programming language", "backend": "auto"}
        )
        mock_curl.assert_called()
        assert "fallback results" in out or "curl" in out.lower() or out


def test_hitl_gates_screenshot_cookies_get_html():
    from src.agent.hitl.policy import SENSITIVE_TOOLS, is_sensitive_call

    assert "get_active_browser_screenshot" in SENSITIVE_TOOLS
    assert "download_to_workspace" in SENSITIVE_TOOLS
    assert is_sensitive_call("active_browser_action", {"action": "get_html"}) is True
    assert is_sensitive_call("active_browser_action", {"action": "click"}) is False
    assert is_sensitive_call("get_active_browser_context", {}) is False


def test_status_endpoint_still_public():
    client = TestClient(app)
    resp = client.get("/api/browser_extension/status")
    assert resp.status_code == 200
    assert "connected" in resp.json()
