#!/usr/bin/env python3
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
ARTIFACT_DIR = Path("/Users/winter/.gemini/antigravity/brain/239647bd-d60d-411c-839e-0c90efc38f4f")
BRAVE_PATH = Path("/Volumes/KNV3_1TB/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
EXTENSION_DIR = Path("/Volumes/KNV3_1TB/OwlynnV2/browser-extension")

async def main():
    executable = str(BRAVE_PATH) if BRAVE_PATH.exists() else None
    args = [
        f"--disable-extensions-except={str(EXTENSION_DIR)}",
        f"--load-extension={str(EXTENSION_DIR)}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    async with async_playwright() as p:
        user_data = f"/tmp/owlynn-verified-{int(time.time())}"
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data,
            executable_path=executable,
            headless=False,
            args=args,
            viewport={"width": 1440, "height": 920},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Switch to Split Graph view
        split_btn = page.locator("button:has-text('Split Graph'), button:has-text('Split View')")
        if await split_btn.count() > 0:
            await split_btn.first.click()
            await page.wait_for_timeout(1000)

        # Send search query
        prompt = "Search the live internet for recent news about Python 3.14 features and give a concise summary."
        textarea = page.locator("textarea.composer-textarea, textarea[placeholder*='Ask'], textarea")
        await textarea.first.fill(prompt)
        await page.wait_for_timeout(500)

        send_btn = page.locator("button.composer-send, button[type='submit']")
        await send_btn.first.click()
        print("Sent prompt, waiting for tool execution and response...")

        start_time = time.time()
        max_wait = 90
        while time.time() - start_time < max_wait:
            await page.wait_for_timeout(3000)
            
            stop_btn = page.locator("button.composer-send.is-stop, button:has-text('Stop')")
            is_busy = await stop_btn.count() > 0
            
            ai_text = page.locator(".prose, .chat-message-assistant, .message-ai")
            has_text = await ai_text.count() > 0
            
            print(f"Elapsed: {int(time.time() - start_time)}s | is_busy: {is_busy} | has_ai_text: {has_text}")

            if has_text and not is_busy and (time.time() - start_time > 15):
                print("Completed!")
                break

        await page.wait_for_timeout(3000)

        # Screenshot 1: Split View
        shot1 = ARTIFACT_DIR / "preview_split_search_flow.png"
        await page.screenshot(path=str(shot1), full_page=False)
        print(f"Saved: {shot1}")

        # Screenshot 2: Full Mindmap Canvas
        mindmap_tab = page.locator("button:has-text('Mindmap Canvas'), button:has-text('Mindmap')")
        if await mindmap_tab.count() > 0:
            await mindmap_tab.first.click()
            await page.wait_for_timeout(2000)

        shot2 = ARTIFACT_DIR / "preview_mindmap_thought_graph.png"
        await page.screenshot(path=str(shot2), full_page=False)
        print(f"Saved: {shot2}")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
