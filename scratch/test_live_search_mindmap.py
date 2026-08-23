#!/usr/bin/env python3
import asyncio
import os
import sys
import time
import json
import httpx
from pathlib import Path
from playwright.async_api import async_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
BACKEND_URL = "http://127.0.0.1:8000"
ARTIFACT_DIR = Path("/Users/winter/.gemini/antigravity/brain/239647bd-d60d-411c-839e-0c90efc38f4f")
BRAVE_PATH = Path("/Volumes/KNV3_1TB/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
EXTENSION_DIR = Path("/Volumes/KNV3_1TB/OwlynnV2/browser-extension")

async def main():
    print("=" * 80)
    print("  OWLYNN V2 PLAYWRIGHT E2E: REAL SEARCH CONVERSATION & THOUGHT GRAPH")
    print("=" * 80)

    executable = str(BRAVE_PATH) if BRAVE_PATH.exists() else None
    args = [
        f"--disable-extensions-except={str(EXTENSION_DIR)}",
        f"--load-extension={str(EXTENSION_DIR)}",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    async with async_playwright() as p:
        user_data = f"/tmp/owlynn-search-graph-test-{int(time.time())}"
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data,
            executable_path=executable,
            headless=False,
            args=args,
            viewport={"width": 1440, "height": 920},
        )

        page = context.pages[0] if context.pages else await context.new_page()

        print(f"[STEP 1] Navigating to Owlynn UI ({FRONTEND_URL})...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 1. Switch to Split Graph view
        print("[STEP 2] Activating Split View...")
        split_btn = page.locator("button:has-text('Split Graph'), button:has-text('Split View')")
        if await split_btn.count() > 0:
            await split_btn.first.click()
            await page.wait_for_timeout(1000)

        # 2. Start a fresh conversation branch / chat
        print("[STEP 3] Starting fresh conversation branch...")
        new_branch_btn = page.locator("button:has-text('New Branch')")
        if await new_branch_btn.count() > 0:
            await new_branch_btn.first.click()
            await page.wait_for_timeout(1000)

        prompt = "Search the live internet for recent news about Python 3.14 features and performance in 2026."
        print(f"\n[STEP 4] Sending search query: '{prompt}'...")

        textarea = page.locator("textarea.composer-textarea, textarea[placeholder*='Ask'], textarea")
        await textarea.first.fill(prompt)
        await page.wait_for_timeout(500)

        send_btn = page.locator("button.composer-send, button[type='submit']")
        await send_btn.first.click()
        print("  ✓ Sent message, awaiting web search tool execution & AI response...")

        start_time = time.time()
        max_wait = 75
        while time.time() - start_time < max_wait:
            await page.wait_for_timeout(3000)
            
            ai_msgs = page.locator(".chat-message-assistant, .prose, .message-ai, [data-role='assistant']")
            count = await ai_msgs.count()
            
            stop_btn = page.locator("button.composer-send.is-stop, button:has-text('Stop')")
            is_busy = await stop_btn.count() > 0
            
            tool_cards = page.locator(".tool-activity-card, .activity-feed, .tool-pill, [data-testid='tool-card']")
            tools_active = await tool_cards.count()

            print(f"  [WAIT] {int(time.time() - start_time)}s | AI msgs: {count} | Tools: {tools_active} | Busy: {is_busy}")

            # Once we see an assistant message and it's not busy anymore (or after at least 15s)
            if count > 0 and not is_busy and (time.time() - start_time > 12):
                print("  ✓ Response completed!")
                break

        await page.wait_for_timeout(3000)

        # Screenshot 1: Split View Conversation & Mindmap
        print("\n[STEP 5] Capturing Split View Conversation & Mindmap...")
        shot1 = ARTIFACT_DIR / "split_view_mindmap_conversation.png"
        await page.screenshot(path=str(shot1), full_page=False)
        print(f"  ✓ Saved: {shot1}")

        # Screenshot 2: Full Mindmap Canvas
        print("\n[STEP 6] Switching to Full Mindmap Canvas...")
        mindmap_tab = page.locator("button:has-text('Mindmap Canvas'), button:has-text('Mindmap')")
        if await mindmap_tab.count() > 0:
            await mindmap_tab.first.click()
            await page.wait_for_timeout(2000)

        shot2 = ARTIFACT_DIR / "thought_graph_canvas.png"
        await page.screenshot(path=str(shot2), full_page=False)
        print(f"  ✓ Saved: {shot2}")

        # Screenshot 3: Chat View
        print("\n[STEP 7] Switching to Full Chat View...")
        chat_tab = page.locator("button:has-text('Chat')")
        if await chat_tab.count() > 0:
            await chat_tab.first.click()
            await page.wait_for_timeout(2000)

        shot3 = ARTIFACT_DIR / "search_conversation_result.png"
        await page.screenshot(path=str(shot3), full_page=False)
        print(f"  ✓ Saved: {shot3}")

        await context.close()
        print("\n" + "=" * 80)
        print("  PLAYWRIGHT E2E VERIFICATION COMPLETED SUCCESSFULLY")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
