import json
import os

import httpx

BURP_API_URL = os.environ.get("BURP_API_URL", "http://127.0.0.1:1337")
BURP_API_KEY = os.environ.get("BURP_API_KEY", "")


def _headers():
    h = {"Content-Type": "application/json"}
    if BURP_API_KEY:
        h["Authorization"] = f"Bearer {BURP_API_KEY}"
    return h


def _check_available() -> str | None:
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{BURP_API_URL}/v0.1", headers=_headers())
            if resp.status_code >= 500:
                return f"Burp API error: HTTP {resp.status_code}"
    except httpx.ConnectError:
        return "Burp Suite is not running or API is not accessible"
    except Exception as e:
        return f"Burp API check failed: {e}"
    return None


try:
    from mcp.server import MCPServer

    mcp = MCPServer("Burp Suite")

    @mcp.tool()
    async def burp_scan_target(url: str, scan_type: str = "active") -> str:
        """Launch a Burp Suite scan against a target URL. scan_type: 'active', 'passive', or 'crawl'."""
        err = _check_available()
        if err:
            return err
        async with httpx.AsyncClient(timeout=300) as client:
            if scan_type == "passive":
                resp = await client.post(
                    f"{BURP_API_URL}/v0.1/scan",
                    headers=_headers(),
                    json={
                        "urls": [url],
                        "scan_configuration": "crawl-and-audit-passive",
                    },
                )
            elif scan_type == "crawl":
                resp = await client.post(
                    f"{BURP_API_URL}/v0.1/crawl",
                    headers=_headers(),
                    json={"urls": [url]},
                )
            else:
                resp = await client.post(
                    f"{BURP_API_URL}/v0.1/scan",
                    headers=_headers(),
                    json={"urls": [url]},
                )
            resp.raise_for_status()
            data = resp.json()
            return json.dumps(
                {
                    "status": "scan_launched",
                    "scan_id": data.get("scan_id", data.get("crawl_id", "")),
                    "target": url,
                    "type": scan_type,
                }
            )

    @mcp.tool()
    async def burp_get_issues(scan_id: str = "", severity: str = "") -> str:
        """Retrieve scan issues/findings from Burp Suite. Filter by scan_id or severity (high/medium/low/info)."""
        err = _check_available()
        if err:
            return err
        async with httpx.AsyncClient(timeout=30) as client:
            params = {}
            if scan_id:
                params["scan_id"] = scan_id
            if severity:
                params["severity"] = severity
            resp = await client.get(
                f"{BURP_API_URL}/v0.1/issues",
                headers=_headers(),
                params=params,
            )
            resp.raise_for_status()
            return json.dumps(resp.json(), indent=2)

    @mcp.tool()
    async def burp_get_scan_status(scan_id: str) -> str:
        """Check the status of a Burp Suite scan."""
        err = _check_available()
        if err:
            return err
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BURP_API_URL}/v0.1/scan/{scan_id}",
                headers=_headers(),
            )
            resp.raise_for_status()
            return json.dumps(resp.json(), indent=2)

except ImportError:
    pass
