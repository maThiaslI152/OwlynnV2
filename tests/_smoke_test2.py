"""Smoke test v2: wait for project items to appear."""
import asyncio
import os
import httpx
import uuid
import time

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")


async def smoke_test():
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{APP_BASE_URL}/api/health")
        assert r.status_code == 200
        print("[OK] Server ready")

    suffix = uuid.uuid4().hex[:8]
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{APP_BASE_URL}/api/projects", json={"name": f"SmokeTest {suffix}"})
        assert r.status_code == 200
        project = r.json()
        print(f"[OK] Created project {project['id']} ({project['name']})")

    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            ws_urls = []
            def on_ws(ws):
                ws_urls.append(ws.url)
            page.on("websocket", on_ws)

            await page.goto(APP_BASE_URL, wait_until="load")
            await page.locator(".connection-label").filter(
                has_text="connected"
            ).wait_for(state="visible", timeout=30000)
            print("[OK] Connected")

            if ws_urls:
                tid = ws_urls[0].split("/")[-1]
                print(f"[OK] Thread ID from WS: {tid}")
            else:
                print("[WARN] No WS events captured")
                tid = None

            # Wait for project items to appear (retry loop)
            for attempt in range(10):
                items = await page.locator(".workspace-project-item").all()
                if len(items) > 0:
                    print(f"[OK] Found {len(items)} workspace project items after ~{attempt*2}s")
                    for item in items:
                        text = (await item.inner_text()).strip()
                        print(f"  - {text[:50]}")
                    break
                await asyncio.sleep(2)
            else:
                print("[FAIL] No workspace project items appeared after 20s")
                content = await page.content()
                # Show relevant parts
                if "workspace-project-list" in content:
                    idx = content.index("workspace-project-list")
                    print(f"HTML around workspace-project-list: {content[idx:idx+500]}")
                print("---")
                # Also check all project-related text
                projects_in_page = await page.locator("[class*='project']").all()
                print(f"Elements with 'project' in class: {len(projects_in_page)}")
                for el in projects_in_page:
                    cls = await el.get_attribute("class")
                    txt = (await el.inner_text()).strip()[:60]
                    print(f"  [{cls}]: {txt}")

            # Try clicking the Refresh button
            refresh_btn = page.locator(".workspace-refresh").first
            if await refresh_btn.is_visible():
                print("[OK] Refresh button found")
                await refresh_btn.click()
                await asyncio.sleep(2)
                items = await page.locator(".workspace-project-item").all()
                print(f"After refresh: {len(items)} items")
            else:
                print("[WARN] Refresh button not visible")

            await browser.close()
            print("[OK] Done")

    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.delete(f"{APP_BASE_URL}/api/projects/{project['id']}")
            print(f"[OK] Deleted project {project['id']}")


if __name__ == "__main__":
    asyncio.run(smoke_test())
