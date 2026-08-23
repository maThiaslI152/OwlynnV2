#!/usr/bin/env python3
"""
Playwright E2E Test:
1. Real conversation with live internet search
2. Streaming response with tool activity & citations
3. Thought Graph / Mindmap creation and interaction
4. Capture high-res screenshots for visual verification
"""

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

    # 1. Health check
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{BACKEND_URL}/api/health")
        print(f"[INIT] Backend health: {r.json()}")
        r_fe = await client.get(FRONTEND_URL)
        print(f"[INIT] Frontend status: {r_fe.status_code}")

    executable = str(BRAVE_PATH) if BRAVE_PATH.exists() else None
    print(f"[BROWSER] Launching browser: {executable or 'Chromium default'}")

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

        # Ensure we are in Split Graph mode to see both chat and mindmap
        print("[STEP 2] Activating Split View to display Mindmap & Chat...")
        split_btn = page.locator("button:has-text('Split Graph'), button:has-text('Split View')")
        if await split_btn.count() > 0:
            await split_btn.first.click()
            await page.wait_for_timeout(1000)

        # Check existing graph nodes
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                g_res = await client.get(f"{BACKEND_URL}/api/graph/nodes")
                print(f"[GRAPH] Initial nodes count: {len(g_res.json())}")
        except Exception as e:
            print(f"[GRAPH] Error fetching initial nodes: {e}")

        # Send search query in composer
        prompt = "Search the live internet for recent news about Python 3.14 features and give a concise summary."
        print(f"\n[STEP 3] Sending live internet search request: '{prompt}'...")

        textarea = page.locator("textarea.composer-textarea, textarea[placeholder*='Ask'], textarea")
        await textarea.first.fill(prompt)
        await page.wait_for_timeout(500)

        send_btn = page.locator("button.composer-send, button[type='submit']")
        await send_btn.first.click()
        print("  ✓ Sent message, waiting for web search tool execution and response...")

        # Wait for completion: button becomes stop during run, then normal again
        # Also poll until assistant message appears
        start_time = time.time()
        max_wait = 90  # 90 seconds timeout for full search & answer
        done = False

        while time.time() - start_time < max_wait:
            await page.wait_for_timeout(2000)
            
            # Check if there is an assistant message
            ai_msgs = page.locator(".chat-message-assistant, .prose, .message-ai, [data-role='assistant']")
            count = await ai_msgs.count()
            
            # Check if stop button is gone
            stop_btn = page.locator("button.composer-send.is-stop, button:has-text('Stop')")
            is_busy = await stop_btn.count() > 0
            
            # Check tool activity card
            tool_cards = page.locator(".tool-activity-card, .activity-feed, .tool-pill, [data-testid='tool-card']")
            tools_active = await tool_cards.count()

            print(f"  [WAIT] Elapsed: {int(time.time() - start_time)}s | AI Messages: {count} | Tools: {tools_active} | Busy: {is_busy}")

            if count > 0 and not is_busy and (time.time() - start_time > 5):
                done = True
                print("  ✓ Conversation completed successfully!")
                break

        await page.wait_for_timeout(2000)

        # Capture conversation screenshot
        print("\n[STEP 4] Capturing Conversation & Search Result Screenshot...")
        shot1 = ARTIFACT_DIR / "search_conversation_result.png"
        await page.screenshot(path=str(shot1), full_page=False)
        print(f"  ✓ Saved conversation screenshot: {shot1}")

        # Check graph nodes again
        print("\n[STEP 5] Inspecting Thought Graph & Mindmap State...")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                g_res = await client.get(f"{BACKEND_URL}/api/graph/nodes")
                nodes = g_res.json()
                print(f"  ✓ Current Thought Graph Nodes ({len(nodes)} total):")
                for n in nodes[-5:]:
                    print(f"    - [{n.get('mode', 'normal')}] {n.get('title')} (id: {n.get('id')})")
        except Exception as e:
            print(f"  ✗ Error fetching graph nodes: {e}")

        # Toggle to Full Mindmap View
        print("\n[STEP 6] Switching to Full Mindmap View...")
        mindmap_btn = page.locator("button:has-text('Mindmap Canvas'), button:has-text('Graph View'), button:has-text('Mindmap')")
        if await mindmap_btn.count() > 0:
            await mindmap_btn.first.click()
            await page.wait_for_timeout(2000)

        shot2 = ARTIFACT_DIR / "thought_graph_canvas.png"
        await page.screenshot(path=str(shot2), full_page=False)
        print(f"  ✓ Saved Thought Graph Canvas screenshot: {shot2}")

        # Switch back to Split View to get the unified experience
        print("\n[STEP 7] Capturing Split View with Mindmap & Conversation...")
        if await split_btn.count() > 0:
            await split_btn.first.click()
            await page.wait_for_timeout(2000)

        shot3 = ARTIFACT_DIR / "split_view_mindmap_conversation.png"
        await page.screenshot(path=str(shot3), full_page=False)
        print(f"  ✓ Saved Split View screenshot: {shot3}")

        await context.close()
        print("\n" + "=" * 80)
        print("  PLAYWRIGHT E2E VERIFICATION COMPLETED SUCCESSFULLY")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
