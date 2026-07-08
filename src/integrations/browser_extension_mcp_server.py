import json
import os

import httpx

OWLYNN_API_URL = os.environ.get("OWLYNN_API_URL", "http://127.0.0.1:8000")
BASE = f"{OWLYNN_API_URL}/api/browser_extension"


def _check_available() -> str | None:
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{BASE}/status")
            if resp.status_code >= 500:
                return f"Owlynn backend error: HTTP {resp.status_code}"
            data = resp.json()
            if not data.get("connected"):
                return "No browser extension connected. Open Chrome with the Owlynn extension installed."
    except httpx.ConnectError:
        return "Owlynn backend is not running. Start it with ./start.sh"
    except Exception as e:
        return f"Backend check failed: {e}"
    return None


try:
    from mcp.server import MCPServer

    mcp = MCPServer("Owlynn Browser")

    @mcp.tool()
    async def browser_search(query: str, engine: str = "google") -> str:
        """Search the web via the user's browser extension. Returns search results scraped from Google, Bing, or DuckDuckGo. Use this instead of webfetch for web searches.

        Args:
            query: Search query string.
            engine: Search engine to use: 'google', 'bing', or 'duckduckgo' (default: google).

        Returns:
            JSON list of search results with title, href, and body fields.
        """
        err = _check_available()
        if err:
            return err
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE}/search", json={"query": query, "engine": engine}
            )
            data = resp.json()
            if data.get("error"):
                return f"Search error: {data['error']}"
            results = data.get("results", [])
            if not results:
                return "No search results found."
            return json.dumps(results, indent=2)

    @mcp.tool()
    async def browser_fetch_page(url: str) -> str:
        """Fetch and extract text content from a web page via the user's browser. Handles JavaScript-rendered pages. Use this instead of webfetch for page content extraction.

        Args:
            url: The URL to fetch.

        Returns:
            Extracted text content from the page.
        """
        err = _check_available()
        if err:
            return err
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{BASE}/fetch", json={"urls": [url]})
            data = resp.json()
            if data.get("error"):
                return f"Fetch error: {data['error']}"
            results = data.get("results", [])
            if not results:
                return "No content extracted."
            texts = []
            for r in results:
                text = r.get("text", "").strip()
                if text:
                    texts.append(text)
            return "\n\n".join(texts) if texts else "Page returned no text content."

    @mcp.tool()
    async def browser_screenshot() -> str:
        """Capture a screenshot of the user's active browser tab with interactive element hints overlaid. Useful for visual verification of web pages.

        Returns:
            Base64-encoded JPEG screenshot, or an error message.
        """
        err = _check_available()
        if err:
            return err
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{BASE}/screenshot")
            data = resp.json()
            if data.get("error"):
                return f"Screenshot error: {data['error']}"
            image_data = data.get("image_data")
            if not image_data:
                return "No screenshot captured."
            return image_data

    @mcp.tool()
    async def browser_status() -> str:
        """Check if the Owlynn browser extension is connected and ready.

        Returns:
            Connection status of the browser extension.
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{BASE}/status")
                data = resp.json()
                if data.get("connected"):
                    return "Browser extension is connected and ready."
                return "No browser extension connected. Open Chrome with the Owlynn extension installed."
        except httpx.ConnectError:
            return "Owlynn backend is not running. Start it with ./start.sh"
        except Exception as e:
            return f"Status check failed: {e}"

except ImportError:
    pass
