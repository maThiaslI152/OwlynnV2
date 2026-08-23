import os

import httpx

H1_BASE = "https://api.hackerone.com/v1"


class HackerOneClient:
    def __init__(self, username: str = "", api_key: str = ""):
        self.username = username or os.environ.get("HACKERONE_USERNAME", "")
        self.api_key = api_key or os.environ.get("HACKERONE_API_KEY", "")

    async def get_programs(self, limit: int = 20) -> list:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{H1_BASE}/hackers/programs",
                auth=(self.username, self.api_key),
                params={"page[size]": limit},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])

    async def get_program(self, handle: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{H1_BASE}/hackers/programs/{handle}",
                auth=(self.username, self.api_key),
            )
            resp.raise_for_status()
            return resp.json()

    async def submit_report(
        self,
        program_handle: str,
        title: str,
        vulnerability_info: str,
        severity_rating: str = "medium",
        impact: str = "",
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{H1_BASE}/hackers/reports",
                auth=(self.username, self.api_key),
                json={
                    "data": {
                        "type": "report",
                        "attributes": {
                            "team_handle": program_handle,
                            "title": title,
                            "vulnerability_information": vulnerability_info,
                            "impact": impact,
                            "weakness_id": None,
                        },
                    }
                },
            )
            resp.raise_for_status()
            return resp.json()
