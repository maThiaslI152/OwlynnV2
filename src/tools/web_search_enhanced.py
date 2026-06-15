"""
Enhanced Web Search — SearXNG Integration
===========================================

Optional self-hosted metasearch (opt-in via ``SEARXNG_URL``).

SearXNG advantages when enabled:
- No API keys needed (self-hosted)
- No bot blocking or CAPTCHAs
- Aggregates Google, Bing, DuckDuckGo, Wikipedia, etc.
- Start with: ``podman compose --profile searxng up -d searxng``

Functions:
- ``searxng_search(query, categories, max_results)``: Search via local SearXNG.
- ``searxng_available()``: Health check for the SearXNG instance.

Falls back gracefully (returns ``None``) if SearXNG is not configured or unreachable.
"""

import logging

from src.config.settings import SEARXNG_URL

logger = logging.getLogger(__name__)


async def searxng_search(
    query: str,
    categories: str = "general",
    max_results: int = 8,
) -> list[dict] | None:
    """
    Search via a local SearXNG instance. Returns list of hit dicts or None on failure.
    """
    if not SEARXNG_URL:
        return None

    import httpx

    params = {
        "q": query,
        "format": "json",
        "categories": categories,
        "language": "en",
        "safesearch": 0,
    }
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "Owlynn/1.0", "Accept": "application/json"},
        ) as client:
            resp = await client.get(f"{SEARXNG_URL}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("SearXNG search failed: %s", e)
        return None

    results = data.get("results", [])
    if not results:
        return None

    hits = []
    for r in results[:max_results]:
        hits.append(
            {
                "title": r.get("title", "No title"),
                "href": r.get("url", ""),
                "body": r.get("content", r.get("snippet", "No snippet")),
                "engine": r.get("engine", "unknown"),
            }
        )
    return hits if hits else None


async def searxng_available() -> bool:
    """Check if SearXNG is reachable."""
    if not SEARXNG_URL:
        return False
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=5.0,
            headers={"User-Agent": "Owlynn/1.0", "Accept": "application/json"},
        ) as client:
            resp = await client.get(f"{SEARXNG_URL}/healthz")
            return resp.status_code == 200
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return False
