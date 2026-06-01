"""Minimal smoke test to verify browser automation works."""
import asyncio
import os
import httpx
import uuid

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")


async def smoke_test():
    # 1. Check server is ready
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{APP_BASE_URL}/api/health")
        assert r.status_code == 200, f"Server not ready: {r.status_code}"
        print(f"[OK] Server ready at {APP_BASE_URL}")

    # 2. Create a project
    suffix = uuid.uuid4().hex[:8]
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{APP_BASE_URL}/api/projects", json={"name": f"SmokeTest {suffix}"})
        assert r.status_code == 200
        project = r.json()
        print(f"[OK] Created project {project['id']} ({project['name']})")

    try:
        # 3. Launch Playwright browser
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            print("[OK] Launched Chromium headless")

            page = await browser.new_page()
            print("[OK] Created page")

            # Capture WebSocket events
            ws_events = []

            def on_ws(ws):
                ws_events.append(ws.url)
                print(f"[WS] {ws.url}")

            page.on("websocket", on_ws)

            # Navigate
            await page.goto(APP_BASE_URL, wait_until="load")
            print(f"[OK] Navigated to {APP_BASE_URL}")

            # Wait for connection
            try:
                await page.locator(".connection-label").filter(
                    has_text="connected"
                ).wait_for(state="visible", timeout=30000)
                print("[OK] Connection status: connected")
            except Exception as e:
                print(f"[FAIL] Connection status not found: {e}")
                content = await page.content()
                print(f"Page snippet: {content[:2000]}")

            if ws_events:
                print(f"[OK] Captured {len(ws_events)} WebSocket events")
                for url in ws_events:
                    print(f"  {url}")
            else:
                print("[WARN] No WebSocket events captured")

            try:
                items = await page.locator(".workspace-project-item").all()
                print(f"[OK] Found {len(items)} workspace project items")
            except Exception as e:
                print(f"[FAIL] workspace-project-item not found: {e}")

            title = await page.title()
            print(f"[INFO] Page title: {title}")

            await browser.close()
            print("[OK] Browser closed")

    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.delete(f"{APP_BASE_URL}/api/projects/{project['id']}")
            print(f"[OK] Deleted project {project['id']}")


if __name__ == "__main__":
    asyncio.run(smoke_test())
