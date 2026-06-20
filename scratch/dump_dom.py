import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("http://127.0.0.1:5173")
        await page.wait_for_selector(".connection-status.connected", timeout=10000)

        # Click new chat
        await page.locator('button.workspace-refresh[title="New chat"]').click()
        await page.wait_for_timeout(500)

        # Dump HTML
        html = await page.content()
        with open("scratch/dom_dump.html", "w") as f:
            f.write(html)

        # Check hitl
        hitl_count = await page.locator(".hitl-prompt-card.hitl-pending").count()
        print(f"HITL Count: {hitl_count}")

        await browser.close()


asyncio.run(main())
