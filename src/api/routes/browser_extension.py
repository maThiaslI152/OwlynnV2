import asyncio
import hmac
import logging
import secrets
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from src.config.config_loader import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browser_extension", tags=["browser_extension"])

active_connections: list[WebSocket] = []
pending_requests: dict[str, asyncio.Future] = {}

# ── Token-based authentication ────────────────────────────────────────────
_TOKEN_PATH = Path.home() / ".owlynn" / "browser_extension_token"


def _generate_auth_token() -> str:
    """Generate a new auth token and write to disk with owner-only permissions."""
    token = secrets.token_urlsafe(32)
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(token, encoding="utf-8")
    try:
        _TOKEN_PATH.chmod(0o600)
    except OSError as exc:
        logger.warning("Could not chmod browser extension token file: %s", exc)
    logger.info("Generated new browser extension auth token at %s", _TOKEN_PATH)
    return token


def _get_auth_token() -> str:
    """Read or generate the auth token."""
    if _TOKEN_PATH.is_file():
        try:
            _TOKEN_PATH.chmod(0o600)
        except OSError:
            pass
        return _TOKEN_PATH.read_text(encoding="utf-8").strip()
    return _generate_auth_token()


# Generate token on module load
_auth_token = _get_auth_token()


def get_extension_auth_token() -> str:
    """Public accessor for the browser-extension WebSocket token."""
    return _auth_token


def _is_allowed_extension_origin(origin: str) -> bool:
    """Allow only real browser-extension origins (reject empty / null)."""
    if not origin or origin == "null":
        return False
    return origin.startswith(("chrome-extension://", "moz-extension://"))


def _is_loopback_client(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in {"127.0.0.1", "::1", "localhost"}


def _token_request_allowed(request: Request) -> bool:
    """Gate /token: extension Origin, or loopback with no Origin (Brave MV3 quirk)."""
    origin = request.headers.get("origin", "")
    if _is_allowed_extension_origin(origin):
        return True
    # Opaque / page origins must never receive the token.
    if origin:
        return False
    # Brave/Chromium MV3 service workers often omit Origin on fetches to
    # 127.0.0.1. Same-user local processes can already read ~/.owlynn token.
    return _is_loopback_client(request)


@router.get("/token")
async def get_token(request: Request):
    """Return the auth token. Extension Origin or loopback-without-Origin only."""
    if not _token_request_allowed(request):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=403,
            content={"detail": "Token endpoint only accessible from browser extension"},
        )
    return {"token": _auth_token}


def _extension_timeout_seconds() -> float:
    return float(config.get("web_search.timeouts.extension", 15.0) or 15.0)


def is_extension_connected() -> bool:
    """Return True if at least one browser extension is currently connected via WebSocket."""
    return len(active_connections) > 0


def push_extension_ui_status(action: str, value: str = "") -> None:
    """Fire-and-forget push of a UI status update to the active extension."""
    if not is_extension_connected():
        return
    ws = active_connections[-1]
    message = {
        "id": str(uuid.uuid4()),
        "action": "ui_status",
        "payload": {
            "action": action,
            "value": value,
        },
    }
    try:
        from src.api.server import app

        loop = getattr(app.state, "loop", None)
        if loop:
            coro = ws.send_json(message)
            asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception as exc:
        logger.warning("Failed to push extension UI status: %s", exc)


def _broadcast_page_context(payload: dict) -> None:
    """Push user-initiated page context to all chat WebSocket clients."""
    from src.api.shared import connected_websockets
    from src.api.shared import logger as shared_logger

    url = str(payload.get("url") or "")
    title = str(payload.get("title") or "")
    text = str(payload.get("text") or "")
    selection = str(payload.get("selection") or "")
    intent = str(payload.get("intent") or "default")

    max_chars = int(config.get("browser_extension.max_tab_text_chars", 12000) or 12000)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n… [truncated]"

    event = {
        "type": "browser.page_context",
        "url": url,
        "title": title,
        "text": text,
        "selection": selection,
        "intent": intent,
    }

    try:
        from src.api.server import app

        loop = getattr(app.state, "loop", None)
    except Exception:
        loop = None

    if not loop:
        shared_logger.warning(
            "Loop not preserved; cannot broadcast browser.page_context."
        )
        return

    for ws in list(connected_websockets):
        try:
            coro = ws.send_json(event)
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as exc:
            shared_logger.warning("Failed to send browser.page_context: %s", exc)


async def dispatch_extension_request(action: str, payload: dict | None = None) -> dict:
    """
    Dispatch an action to the connected browser extension and await the response.
    Raises RuntimeError if not connected, or asyncio.TimeoutError on timeout.
    """
    if not is_extension_connected():
        raise RuntimeError("No browser extension is currently connected.")

    # Always use the most recently connected extension (e.g., MockExtensionClient)
    ws = active_connections[-1]
    request_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    pending_requests[request_id] = future
    message = {"id": request_id, "action": action, **(payload or {})}
    logger.info("Dispatching extension action %s (ID: %s)", action, request_id)

    try:
        await ws.send_json(message)
        result = await asyncio.wait_for(future, timeout=_extension_timeout_seconds())
        if not isinstance(result, dict):
            return {"results": result} if action == "search" else {"tab": result}
        return result
    except Exception as exc:
        logger.warning(
            "Extension action %s failed or timed out for ID %s: %s",
            action,
            request_id,
            exc,
        )
        raise
    finally:
        pending_requests.pop(request_id, None)


async def dispatch_extension_search(search_url: str) -> list[dict]:
    """
    Dispatch a search query URL to the connected browser extension and await results.
    Raises RuntimeError if not connected, or asyncio.TimeoutError if the extension fails to respond.
    """
    data = await dispatch_extension_request("search", {"url": search_url})
    results = data.get("results", [])
    return results if isinstance(results, list) else []


async def dispatch_extension_get_active_tab() -> dict:
    """Request URL, title, body text, and selection from the user's active browser tab."""
    data = await dispatch_extension_request("get_active_tab", {})
    tab = data.get("tab", data)
    return tab if isinstance(tab, dict) else {}


async def dispatch_extension_get_cookies(url: str) -> str:
    """Request cookie string for a specific URL from the extension."""
    try:
        data = await dispatch_extension_request("get_cookies", {"url": url})
        return data.get("cookies", "")
    except Exception as exc:
        logger.warning(f"Failed to fetch cookies for {url}: {exc}")
        return ""


async def dispatch_extension_capture_screenshot() -> str | None:
    """Request a base64 jpeg screenshot of the user's active browser tab."""
    data = await dispatch_extension_request("capture_screenshot", {})
    error = data.get("error")
    if error:
        logger.warning("Browser screenshot capture failed: %s", error)
        return None
    return data.get("image_data")


async def dispatch_extension_browser_action(
    action: str,
    selector: str = "",
    text: str = "",
    y: int = 0,
    element_id: int = -1,
    element_ids: list[int] = None,
) -> dict:
    """Execute a DOM interaction (click, type, scroll) on the active tab."""
    payload = {
        "action": action,
        "selector": selector,
        "text": text,
        "y": y,
        "element_id": element_id,
        "element_ids": element_ids or [],
    }
    data = await dispatch_extension_request("browser_action", {"payload": payload})
    if "error" in data:
        return {"success": False, "error": data["error"]}
    return data.get("result", {"success": False, "error": "Unknown error"})


async def dispatch_extension_fetch_urls(urls: list[str]) -> list[dict]:
    """Fetch multiple URLs in the background via the extension.

    Applies the same SSRF policy as ``fetch_webpage`` before dispatching.
    """
    from src.tools.url_policy import url_fetch_blocked_reason

    allowed: list[str] = []
    blocked_results: list[dict] = []
    for raw in urls or []:
        u = str(raw or "").strip()
        if not u:
            continue
        reason = url_fetch_blocked_reason(u)
        if reason:
            blocked_results.append(
                {"url": u, "text": "", "error": f"Blocked: {reason}"}
            )
        else:
            allowed.append(u)

    if not allowed:
        return blocked_results

    # We must allow a longer timeout since multiple tabs are loaded.
    original_timeout = config.get("web_search.timeouts.extension")
    config["web_search.timeouts.extension"] = 30.0 + (len(allowed) * 5.0)
    try:
        data = await dispatch_extension_request("fetch_urls", {"urls": allowed})
        results = data.get("results", [])
        fetched = results if isinstance(results, list) else []
        return blocked_results + fetched
    finally:
        config["web_search.timeouts.extension"] = original_timeout


def format_active_tab_context(tab: dict) -> str:
    """Format extension active-tab payload for agent tools."""
    url = str(tab.get("url") or "")
    title = str(tab.get("title") or "")
    text = str(tab.get("text") or "").strip()
    selection = str(tab.get("selection") or "").strip()
    error = str(tab.get("error") or "").strip()

    max_chars = int(config.get("browser_extension.max_tab_text_chars", 12000) or 12000)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n… [truncated]"

    lines = [f"browser|{url}|{title}"]
    if error:
        lines.append(f"note: {error}")
    if selection:
        lines.append("--- selection ---")
        lines.append(selection)
    if text:
        lines.append("--- page ---")
        lines.append(text)
    return "\n".join(lines)


# ── REST endpoints (for MCP server and external clients) ──────────────


@router.get("/status")
async def extension_status():
    """Check if a browser extension is currently connected."""
    return {
        "connected": is_extension_connected(),
        "connections": len(active_connections),
    }


@router.post("/search")
async def extension_search(request: Request):
    """Dispatch a search query to the connected browser extension."""
    if not is_extension_connected():
        return {"error": "No browser extension connected", "results": []}
    body = await request.json()
    query = body.get("query", "")
    engine = body.get("engine", "google")
    if not query:
        return {"error": "Missing 'query' field", "results": []}
    search_url = _build_search_url(query, engine)
    try:
        results = await dispatch_extension_search(search_url)
        return {"results": results, "engine": engine, "query": query}
    except TimeoutError:
        return {"error": "Search timed out", "results": []}
    except Exception as exc:
        return {"error": str(exc), "results": []}


@router.post("/fetch")
async def extension_fetch(request: Request):
    """Fetch page content from URLs via the browser extension."""
    if not is_extension_connected():
        return {"error": "No browser extension connected", "results": []}
    body = await request.json()
    urls = body.get("urls", [])
    if not urls:
        return {"error": "Missing 'urls' field", "results": []}
    try:
        results = await dispatch_extension_fetch_urls(urls)
        return {"results": results}
    except TimeoutError:
        return {"error": "Fetch timed out", "results": []}
    except Exception as exc:
        return {"error": str(exc), "results": []}


@router.get("/screenshot")
async def extension_screenshot():
    """Capture a screenshot of the active browser tab."""
    if not is_extension_connected():
        return {"error": "No browser extension connected", "image_data": None}
    try:
        image_data = await dispatch_extension_capture_screenshot()
        return {"image_data": image_data}
    except TimeoutError:
        return {"error": "Screenshot timed out", "image_data": None}
    except Exception as exc:
        return {"error": str(exc), "image_data": None}


def _build_search_url(query: str, engine: str) -> str:
    """Build a search URL for the given query and engine."""
    from urllib.parse import quote_plus

    encoded = quote_plus(query)
    if engine == "bing":
        return f"https://www.bing.com/search?q={encoded}"
    if engine == "duckduckgo":
        return f"https://duckduckgo.com/?q={encoded}"
    return f"https://www.google.com/search?q={encoded}"


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin", "")
    if not _is_allowed_extension_origin(origin):
        await websocket.close(code=4003, reason="Forbidden origin")
        return

    await websocket.accept()
    logger.info("Browser bridge extension connected from %s", websocket.client)

    # Wait for auth message (first message must be auth)
    try:
        auth_data = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        token_ok = (
            auth_data.get("type") == "auth"
            and isinstance(auth_data.get("token"), str)
            and hmac.compare_digest(auth_data.get("token", ""), _auth_token)
        )
        if not token_ok:
            logger.warning("Browser extension auth failed: invalid token")
            await websocket.close(code=4001, reason="Authentication failed")
            return
        logger.info("Browser extension authenticated successfully")
    except TimeoutError:
        logger.warning("Browser extension auth timeout — no auth message received")
        try:
            await websocket.close(code=4001, reason="Authentication timeout")
        except Exception:
            pass
        return
    except WebSocketDisconnect as e:
        # Client closed before auth (often missing token). Not a server fault —
        # log at debug to avoid drowning logs during extension reconnect loops.
        logger.debug("Browser extension disconnected before auth: %s", e)
        return
    except Exception as e:
        logger.warning("Browser extension auth error: %s", e)
        try:
            await websocket.close(code=4001, reason="Authentication error")
        except Exception:
            pass
        return

    active_connections.append(websocket)

    try:
        while True:
            data = await websocket.receive_json()

            # Validate message type — allowlist of known types
            msg_type = data.get("type")
            allowed_types = {"page_context_push", "ping", "auth"}
            if msg_type not in allowed_types and not (
                data.get("id") and isinstance(data.get("id"), str)
            ):
                logger.debug(
                    "Ignoring unknown message type from extension: %s", msg_type
                )
                continue

            if data.get("type") == "page_context_push":
                # Live-tracking Mem0 path and iframe sidebar response removed
                # (broken X-Frame-Options + dead allowlist config). User push
                # still broadcasts to chat clients.
                _broadcast_page_context(data)
                continue

            request_id = data.get("id")
            if request_id and request_id in pending_requests:
                future = pending_requests[request_id]
                if not future.done():
                    future.set_result(data)
            else:
                logger.debug(
                    "Received unexpected or expired request ID from extension: %s",
                    request_id,
                )
    except WebSocketDisconnect:
        logger.info("Browser bridge extension disconnected.")
    except Exception as exc:
        logger.warning("Error in extension websocket session: %s", exc)
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)

        if len(active_connections) == 0:
            for request_id, future in list(pending_requests.items()):
                if not future.done():
                    future.set_exception(
                        RuntimeError("Extension client disconnected during request.")
                    )


@router.post("/reload")
async def trigger_extension_reload():
    """Trigger the connected browser extension to reload itself."""
    if not is_extension_connected():
        return {"success": False, "error": "No extension connected"}

    ws = active_connections[-1]
    message = {"type": "RELOAD"}
    try:
        await ws.send_json(message)
        return {"success": True}
    except Exception as exc:
        logger.warning("Failed to push reload command: %s", exc)
        return {"success": False, "error": str(exc)}
