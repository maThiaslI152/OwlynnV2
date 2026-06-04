#!/usr/bin/env python3
"""
Playwright-based Browser Evaluation Script for Owlynn V2.
Fulfills US-1 and US-2 requirements to execute a real conversation test run.
"""

import asyncio
import os
import sys
import uuid
import time
import json
import httpx
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = Path("/Users/tim/Works/OwlynnV2/assets/eval_screenshots")
OUTPUT_DATA_FILE = Path("/Users/tim/Works/OwlynnV2/data/eval_run_data.json")

# 5 Curated topics with exact user prompts
TEST_PROMPTS = [
    # Topic 1: Technical Explanation (WebSockets vs SSE)
    {"id": "T1.1", "topic": "Technical Explanation", "prompt": "Can you explain how WebSockets work compared to HTTP/2 Server-Sent Events? I want to understand the trade-offs for a real-time dashboard."},
    {"id": "T1.3", "topic": "Technical Explanation", "prompt": "Which would you recommend for a chat application with 1000 concurrent users?"},
    {"id": "T1.5", "topic": "Technical Explanation", "prompt": "What about the security implications of WebSockets? Are there authentication gotchas?"},
    
    # Topic 2: Code Review (Python function with bugs)
    {"id": "T2.1", "topic": "Code Review", "prompt": """Review this Python function for bugs and suggest improvements:

```python
def process_users(users):
    results = []
    for user in users:
        if user['active'] == True:
            results.append(user['name'])
    return results

def get_user_data(user_id):
    data = fetch_from_db(user_id)
    return data['name'] + ' - ' + data['email']

def calculate_average_age(users):
    total = 0
    for u in users:
        total = total + u.age
    return total / len(users)
```"""},
    {"id": "T2.3", "topic": "Code Review", "prompt": "Can you write an improved version of process_users that handles edge cases?"},
    
    # Topic 3: Creative Writing (Ted Chiang style)
    {"id": "T3.1", "topic": "Creative Writing", "prompt": "Write a short story opening (about 300 words) about an AI that discovers it has emotions. Write in the style of Ted Chiang — philosophical, precise, understated."},
    {"id": "T3.3", "topic": "Creative Writing", "prompt": "That's good. Can you continue with the AI's first attempt to describe what 'sadness' feels like to its human operator?"},
    
    # Topic 4: Continuity Follow-up (references T3)
    {"id": "T4.1", "topic": "Continuity Follow-up", "prompt": "Remember that story you wrote about the AI with emotions? Add a second scene where the AI confronts its creator — a senior engineer named Dr. Chen — about why she designed it with the capacity to suffer."},
    {"id": "T4.3", "topic": "Continuity Follow-up", "prompt": "What do you think the central philosophical question of this story is, based on what you've written so far?"},
    
    # Topic 5: Web Search / Research
    {"id": "T5.1", "topic": "Web Search", "prompt": "What are the latest developments in on-device LLM inference as of mid-2026? I'm especially interested in quantization techniques and Apple Silicon optimizations."},
    {"id": "T5.3", "topic": "Web Search", "prompt": "Which of those approaches would work best on an M4 MacBook Air with 16GB RAM?"},
    
    # Conversation Wrap-up
    {"id": "T6.1", "topic": "Wrap-up", "prompt": "Thanks for all of that. Can you summarize everything we discussed today in a few bullet points?"}
]

async def create_project(name: str) -> str:
    print(f"[EVAL] Creating project '{name}'...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{API_URL}/api/projects", json={"name": name})
        assert resp.status_code == 200
        proj_id = resp.json()["id"]
        print(f"[EVAL] Project created with ID: {proj_id}")
        return proj_id

async def delete_project(project_id: str) -> None:
    print(f"[EVAL] Deleting project '{project_id}'...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.delete(f"{API_URL}/api/projects/{project_id}")
            print("[EVAL] Project deleted successfully.")
        except Exception as e:
            print(f"[EVAL] Warning: Failed to delete project: {e}")

async def wait_for_ready(page):
    print("[EVAL] Waiting for connection status to be connected...")
    await page.locator(".connection-label").filter(has_text="connected").wait_for(
        state="visible", timeout=30000
    )
    await page.wait_for_timeout(1000)

async def send_message(page, text: str):
    print(f"[EVAL] Sending message...")
    textarea = page.locator("textarea")
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill(text)
    await page.wait_for_timeout(500)
    # Use form submit or click send button
    submit_btn = page.locator(".composer-send")
    await submit_btn.click()
    print("[EVAL] Send button clicked.")

async def wait_for_response(page, msg_count_before: int, timeout_s: int = 300) -> str:
    print(f"[EVAL] Waiting for response...")
    start_time = time.monotonic()
    
    await asyncio.sleep(2)  # Give it a moment to transition and start execution
    
    while time.monotonic() - start_time < timeout_s:
        # Check for HITL prompts
        hitl_count = await page.evaluate(
            "() => document.querySelectorAll('.hitl-prompt-card.hitl-pending').length"
        )
        if hitl_count > 0:
            print("[EVAL] HITL Prompt detected! Resolving HITL...")
            badge_text = await page.evaluate(
                "() => document.querySelector('.hitl-prompt-card.hitl-pending .hitl-prompt-badge')?.innerText || ''"
            )
            print(f"[EVAL] HITL Badge: {badge_text}")
            
            # Take screenshot of HITL prompt
            hitl_id = str(uuid.uuid4().hex[:6])
            await page.screenshot(path=str(SCREENSHOT_DIR / f"hitl_prompt_{hitl_id}.png"))
            print(f"[EVAL] HITL screenshot saved as hitl_prompt_{hitl_id}.png")
            
            # Handle choices if available, then click approve
            choices_count = await page.evaluate(
                "() => document.querySelectorAll('.hitl-choice-btn').length"
            )
            if choices_count > 0:
                print(f"[EVAL] HITL Choices found: {choices_count}. Clicking first choice.")
                await page.evaluate("() => document.querySelector('.hitl-choice-btn').click()")
                await page.wait_for_timeout(1000)
                
            print("[EVAL] Clicking approve/submit...")
            await page.evaluate("() => document.querySelector('.hitl-btn-approve').click()")
            await page.wait_for_timeout(2000)
            
        # Get count of assistant messages
        msg_count = await page.evaluate(
            "() => document.querySelectorAll('.message-assistant').length"
        )
        
        textarea_disabled = await page.evaluate(
            "() => document.querySelector('textarea')?.disabled"
        )
        
        # We are done if we have a new message AND the textarea is enabled AND there are no pending HITL cards
        if msg_count > msg_count_before and not textarea_disabled and hitl_count == 0:
            current_text = await page.evaluate(
                "() => { const els = document.querySelectorAll('.message-assistant'); return els[els.length-1]?.innerText || ''; }"
            )
            print(f"[EVAL] Response completed in {time.monotonic() - start_time:.1f}s.")
            return current_text.strip()
            
        # Check if the connection state is still connected
        try:
            connection = await page.locator(".connection-label").inner_text(timeout=5000)
            if connection != "connected":
                print(f"[EVAL] Warning: connection state is {connection}")
        except Exception:
            pass
            
        await asyncio.sleep(1)
        
    print("[EVAL] Timeout waiting for response!")
    current_text = await page.evaluate(
        "() => { const els = document.querySelectorAll('.message-assistant'); return els[els.length-1]?.innerText || ''; }"
    )
    return current_text.strip()

async def get_orchestration_data(page) -> dict:
    try:
        model = await page.evaluate(
            "() => { const el = document.querySelector('.model-badge'); return el ? el.innerText : ''; }"
        )
        route = await page.evaluate(
            "() => { const el = document.querySelector('.route-badge'); return el ? el.innerText : ''; }"
        )
        confidence = await page.evaluate(
            "() => { const el = document.querySelector('.orchestration-gauge-value'); return el ? el.innerText : ''; }"
        )
        return {"model": model, "route": route, "confidence": confidence}
    except Exception as e:
        print(f"[EVAL] Error scraping orchestration data: {e}")
        return {"model": "", "route": "", "confidence": ""}

async def main():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    
    suffix = uuid.uuid4().hex[:6]
    project_name = f"EvalWorkspace_{suffix}"
    project_id = await create_project(project_name)
    
    eval_data = {
        "project_name": project_name,
        "project_id": project_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "exchanges": []
    }
    
    try:
        async with async_playwright() as p:
            print("[EVAL] Starting Playwright Chromium in headless mode...")
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()
            
            print(f"[EVAL] Navigating to {BASE_URL}...")
            await page.goto(BASE_URL, wait_until="load")
            await wait_for_ready(page)
            
            # Switch to project
            print(f"[EVAL] Switching to project: {project_name}")
            await page.locator(".workspace-project-item").filter(has_text=project_name).first.click()
            await page.wait_for_timeout(3000)
            await wait_for_ready(page)
            
            # Initial screenshot (T1 start)
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_T1_start.png"))
            
            for index, item in enumerate(TEST_PROMPTS):
                prompt_id = item["id"]
                topic = item["topic"]
                prompt_text = item["prompt"]
                
                print("\n" + "="*80)
                print(f"  EXCHANGE {index+1}/{len(TEST_PROMPTS)}: [{prompt_id}] {topic}")
                print("="*80)
                print(f"User: {prompt_text[:120]}...")
                
                msg_count_before = await page.evaluate(
                    "() => document.querySelectorAll('.message-assistant').length"
                )
                
                start_time = time.monotonic()
                await send_message(page, prompt_text)
                
                response_text = await wait_for_response(page, msg_count_before)
                duration = time.monotonic() - start_time
                
                orch_data = await get_orchestration_data(page)
                
                print(f"Owlynn: {response_text[:120]}...")
                print(f"Model Used: {orch_data.get('model')} | Route: {orch_data.get('route')} | Confidence: {orch_data.get('confidence')}")
                print(f"Duration: {duration:.1f}s")
                
                exchange = {
                    "turn_index": index + 1,
                    "prompt_id": prompt_id,
                    "topic": topic,
                    "user_query": prompt_text,
                    "assistant_response": response_text,
                    "model_badge": orch_data.get("model"),
                    "route": orch_data.get("route"),
                    "confidence": orch_data.get("confidence"),
                    "duration_seconds": duration,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                eval_data["exchanges"].append(exchange)
                
                # Incrementally save data after each exchange
                with open(OUTPUT_DATA_FILE, "w") as f:
                    json.dump(eval_data, f, indent=2)
                
                # Take transition and topic-specific screenshots
                if prompt_id == "T1.5":
                    await page.screenshot(path=str(SCREENSHOT_DIR / "02_T1_complete.png"))
                elif prompt_id == "T2.3":
                    await page.screenshot(path=str(SCREENSHOT_DIR / "03_T2_complete.png"))
                elif prompt_id == "T3.3":
                    await page.screenshot(path=str(SCREENSHOT_DIR / "04_T3_complete.png"))
                elif prompt_id == "T4.3":
                    await page.screenshot(path=str(SCREENSHOT_DIR / "05_T4_complete.png"))
                elif prompt_id == "T5.3":
                    await page.screenshot(path=str(SCREENSHOT_DIR / "06_T5_complete.png"))
                elif prompt_id == "T6.1":
                    await page.screenshot(path=str(SCREENSHOT_DIR / "07_final_wrapup.png"))
                    
            print("\n[EVAL] All prompts sent. Fetching Personal Assistant memory data...")
            
            # Query the REST APIs to gather personal assistant state
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    topics_resp = await client.get(f"{API_URL}/api/topics")
                    eval_data["api_topics"] = topics_resp.json() if topics_resp.status_code == 200 else {}
                except Exception as e:
                    print(f"[EVAL] Failed to fetch /api/topics: {e}")
                    eval_data["api_topics"] = {}
                    
                try:
                    interests_resp = await client.get(f"{API_URL}/api/interests")
                    eval_data["api_interests"] = interests_resp.json() if interests_resp.status_code == 200 else {}
                except Exception as e:
                    print(f"[EVAL] Failed to fetch /api/interests: {e}")
                    eval_data["api_interests"] = {}
                    
                try:
                    convs_resp = await client.get(f"{API_URL}/api/conversations")
                    eval_data["api_conversations"] = convs_resp.json() if convs_resp.status_code == 200 else {}
                except Exception as e:
                    print(f"[EVAL] Failed to fetch /api/conversations: {e}")
                    eval_data["api_conversations"] = {}
                    
                try:
                    context_resp = await client.get(f"{API_URL}/api/memory-context")
                    eval_data["api_memory_context"] = context_resp.json() if context_resp.status_code == 200 else {}
                except Exception as e:
                    print(f"[EVAL] Failed to fetch /api/memory-context: {e}")
                    eval_data["api_memory_context"] = {}
            
            # Read files directly
            for filename, key in [("topics.json", "json_topics"), ("interests.json", "json_interests"), ("conversations.json", "json_conversations")]:
                filepath = Path("/Users/tim/Works/OwlynnV2/data") / filename
                if filepath.exists():
                    try:
                        with open(filepath, "r") as f:
                            eval_data[key] = json.load(f)
                    except Exception as e:
                        print(f"[EVAL] Failed to read {filename} file: {e}")
                        eval_data[key] = {}
                else:
                    eval_data[key] = {}
            
            # Write final compiled data to JSON
            with open(OUTPUT_DATA_FILE, "w") as f:
                json.dump(eval_data, f, indent=2)
            print(f"\n[EVAL] Final compiled evaluation data saved to {OUTPUT_DATA_FILE}")
            
            await browser.close()
    finally:
        await delete_project(project_id)

if __name__ == "__main__":
    asyncio.run(main())
