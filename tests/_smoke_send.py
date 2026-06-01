"""Minimal test: send one message and check response."""
import asyncio
import os
import httpx
import uuid

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")

async def run():
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{APP_BASE_URL}/api/health")
        assert r.status_code == 200
        print("[OK] Server ready")

    suffix = uuid.uuid4().hex[:8]
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{APP_BASE_URL}/api/projects", json={"name": f"SendTest {suffix}"})
        project = r.json()
        print(f"[OK] Created project {project['id']}")

    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            print("[OK] Browser launched")

            page = await browser.new_page()
            ws_urls = []
            def on_ws(ws):
                ws_urls.append(ws.url)
            page.on("websocket", on_ws)

            await page.goto(APP_BASE_URL, wait_until="load")
            await page.locator(".connection-label").filter(
                has_text="connected"
            ).wait_for(state="visible", timeout=30000)
            print(f"[OK] Connected. WS: {ws_urls[0] if ws_urls else 'none'}")

            # Switch to our project
            item = page.locator(".workspace-project-item").filter(has_text=project['name']).first
            await item.scroll_into_view_if_needed()
            await item.click()
            await page.get_by_text(f"Active: {project['name']}").wait_for(state="visible", timeout=15000)

            # Send a message
            textbox = page.get_by_role("textbox")
            await textbox.wait_for(state="visible", timeout=10000)

            msg_before = await page.locator(".message-assistant").count()
            print(f"[INFO] Assistant msgs before: {msg_before}")

            await textbox.fill("Hello! What is 2+2?")
            await page.locator(".composer-send").click()
            await page.get_by_text("Hello! What is 2+2?").first.wait_for(state="visible", timeout=15000)
            print("[OK] Message sent")

            # Wait for assistant response (up to 60s)
            import time
            deadline = time.time() + 60
            response = ""
            while time.time() < deadline:
                msg_now = await page.locator(".message-assistant").count()
                if msg_now > msg_before:
                    response = await page.locator(".message-assistant").nth(msg_now - 1).inner_text()
                    print(f"[OK] Got response after {(time.time() - (deadline - 60)):.1f}s")
                    break
                await asyncio.sleep(1)
            else:
                # Check what's on the page
                page_content = await page.content()
                print(f"[FAIL] No assistant response within 60s")
                # Show key parts
                if "hitl-prompt" in page_content:
                    print("  HITL card found on page")
                if "tool-activity" in page_content:
                    print("  Tool activity found on page")

            if response:
                print(f"Response ({len(response)} chars): {response[:200]}")

            await browser.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.delete(f"{APP_BASE_URL}/api/projects/{project['id']}")
            print(f"[OK] Cleaned up")


if __name__ == "__main__":
    asyncio.run(run())
