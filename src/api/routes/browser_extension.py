import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config.config_loader import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browser_extension", tags=["browser_extension"])

active_connections: list[WebSocket] = []
pending_requests: dict[str, asyncio.Future] = {}


def _extension_timeout_seconds() -> float:
    return float(config.get("web_search.timeouts.extension", 15.0) or 15.0)


def is_extension_connected() -> bool:
    """Return True if at least one browser extension is currently connected via WebSocket."""
    return len(active_connections) > 0


def _broadcast_page_context(payload: dict) -> None:
    """Push user-initiated page context to all chat WebSocket clients."""
    from src.api.shared import connected_websockets, logger as shared_logger

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
    action: str, selector: str = "", text: str = "", y: int = 0, element_id: int = -1
) -> dict:
    """Execute a DOM interaction (click, type, scroll) on the active tab."""
    payload = {
        "action": action,
        "selector": selector,
        "text": text,
        "y": y,
        "element_id": element_id,
    }
    data = await dispatch_extension_request("browser_action", {"payload": payload})
    if "error" in data:
        return {"success": False, "error": data["error"]}
    return data.get("result", {"success": False, "error": "Unknown error"})


async def dispatch_extension_fetch_urls(urls: list[str]) -> list[dict]:
    """Fetch multiple URLs in the background via the extension."""
    # We must allow a longer timeout since multiple tabs are loaded.
    original_timeout = config.get("web_search.timeouts.extension")
    config["web_search.timeouts.extension"] = 30.0 + (len(urls) * 5.0)
    try:
        data = await dispatch_extension_request("fetch_urls", {"urls": urls})
        results = data.get("results", [])
        return results if isinstance(results, list) else []
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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info("Browser bridge extension connected from %s", websocket.client)

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "page_context_push":
                if data.get("is_live_tracking"):
                    from src.memory.long_term import memory as mem0_memory

                    if mem0_memory:
                        text = str(data.get("text") or "")
                        url = str(data.get("url") or "")
                        title = str(data.get("title") or "")
                        if len(text) > 200:
                            # Compress text to avoid overwhelming memory
                            content = f"Page: {title} ({url})\n\n{text[:4000]}"
                            try:
                                mem0_memory.add(
                                    content,
                                    user_id="owner",
                                    metadata={"url": url, "source": "live_tracking"},
                                )
                                logger.info(f"Saved live tracking context for {url}")
                            except Exception as e:
                                logger.warning(
                                    f"Failed to save live tracking to memory: {e}"
                                )
                else:
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
