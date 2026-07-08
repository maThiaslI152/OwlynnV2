import httpx
import os

SHODAN_BASE = "https://api.shodan.io"


class ShodanClient:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("SHODAN_API_KEY", "")

    async def search(self, query: str, page: int = 1) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SHODAN_BASE}/shodan/host/search",
                params={"key": self.api_key, "query": query, "page": page},
            )
            resp.raise_for_status()
            return resp.json()

    async def host(self, ip: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SHODAN_BASE}/shodan/host/{ip}",
                params={"key": self.api_key},
            )
            resp.raise_for_status()
            return resp.json()

    async def scan(self, ips: list[str]) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{SHODAN_BASE}/shodan/scan",
                params={"key": self.api_key},
                json={"ips": ",".join(ips)},
            )
            resp.raise_for_status()
            return resp.json()
