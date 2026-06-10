import asyncio
import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browser_extension", tags=["browser_extension"])

active_connections: list[WebSocket] = []
pending_searches: dict[str, asyncio.Future] = {}


def is_extension_connected() -> bool:
    """Return True if at least one browser extension is currently connected via WebSocket."""
    return len(active_connections) > 0


async def dispatch_extension_search(search_url: str) -> list[dict]:
    """
    Dispatch a search query URL to the connected browser extension and await results.
    Raises RuntimeError if not connected, or asyncio.TimeoutError if the extension fails to respond.
    """
    if not is_extension_connected():
        raise RuntimeError("No browser extension is currently connected.")

    ws = active_connections[0]
    request_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    pending_searches[request_id] = future
    logger.info("Dispatching search to extension (ID: %s): %s", request_id, search_url)

    try:
        # Request search from extension
        await ws.send_json({"id": request_id, "action": "search", "url": search_url})

        # Wait for content script to scrape and respond (15s timeout limit)
        results = await asyncio.wait_for(future, timeout=15.0)
        return results
    except Exception as e:
        logger.warning(
            "Extension search failed or timed out for ID %s: %s", request_id, e
        )
        raise e
    finally:
        pending_searches.pop(request_id, None)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info("Browser search bridge extension connected from %s", websocket.client)

    try:
        while True:
            data = await websocket.receive_json()
            request_id = data.get("id")
            results = data.get("results", [])

            if request_id and request_id in pending_searches:
                future = pending_searches[request_id]
                if not future.done():
                    future.set_result(results)
            else:
                logger.debug(
                    "Received unexpected or expired query ID from extension: %s",
                    request_id,
                )
    except WebSocketDisconnect:
        logger.info("Browser search bridge extension disconnected.")
    except Exception as e:
        logger.warning("Error in extension websocket session: %s", e)
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)

        # Clean up any pending searches connected to this socket session
        if len(active_connections) == 0:
            for request_id, future in list(pending_searches.items()):
                if not future.done():
                    future.set_exception(
                        RuntimeError("Extension client disconnected during search.")
                    )
