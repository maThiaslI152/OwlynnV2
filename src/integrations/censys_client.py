import os

import httpx

CENSYS_BASE = "https://search.censys.io/api/v2"


class CensysClient:
    def __init__(self, api_id: str = "", api_secret: str = ""):
        self.api_id = api_id or os.environ.get("CENSYS_API_ID", "")
        self.api_secret = api_secret or os.environ.get("CENSYS_API_SECRET", "")

    async def search_hosts(self, query: str, per_page: int = 25) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{CENSYS_BASE}/hosts/search",
                params={"q": query, "per_page": per_page},
                auth=(self.api_id, self.api_secret),
            )
            resp.raise_for_status()
            return resp.json()

    async def search_certificates(self, query: str, per_page: int = 25) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{CENSYS_BASE}/certificates/search",
                params={"q": query, "per_page": per_page},
                auth=(self.api_id, self.api_secret),
            )
            resp.raise_for_status()
            return resp.json()
