#!/usr/bin/env python3
"""
Playwright-based Local Frontier Evaluation Script for Owlynn V2.
Focuses on M4 Air constraints, 3-tier LLM routing, and deep tool usage.
"""

import asyncio
import uuid
import time
import json
import httpx
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = Path("/Users/tim/Works/OwlynnV2/assets/frontier_eval_screenshots")
OUTPUT_DATA_FILE = Path("/Users/tim/Works/OwlynnV2/data/frontier_eval_run_data.json")

TEST_PROMPTS = [
    # 1. Router Precision: Simple bypass
    {
        "id": "F1.1",
        "topic": "Router Precision (Simple)",
        "prompt": "Hello there! Hope you are doing well today.",
        "expected_route": "simple",
    },
    # 2. Router Precision: Code Review bypass (Complex)
    {
        "id": "F2.1",
        "topic": "Router Precision (Complex)",
        "prompt": "Can you review the python code in this function and tell me if it has bugs?",
        "expected_route": "complex-default",
    },
    # 3. Deep Tool Iteration: Web Search + File Ops
    {
        "id": "F3.1",
        "topic": "Deep Tool Iteration",
        "prompt": "Search the web for the weather in Tokyo right now. Then create a file in my workspace named 'tokyo_weather.txt' with the forecast summary.",
        "expected_route": "complex-default",
        "expected_tools": ["web_search", "write_workspace_file"],
    },
    # 4. Massive Context & Reading
    {
        "id": "F4.1",
        "topic": "Massive Context Ingestion",
        "prompt": "Read the file `docs/STATUS.md` from the workspace. What are the 'Architectural Concerns' listed there?",
        "expected_route": "complex-default",
        "expected_tools": ["read_workspace_file"],
    },
    # 5. Sustained Multi-step Reasoning
    {
        "id": "F5.1",
        "topic": "Sustained Reasoning",
        "prompt": "Write a complete React component for a Data Dashboard. It needs a header, a sidebar, and a main content area with a mock chart. Also write the CSS in a separate file named 'dashboard.css'. Give me the full code without placeholders.",
        "expected_route": "complex-default",
    },
    # 6. Memory Retention and Recall
    {
        "id": "F6.1",
        "topic": "Memory Retention",
        "prompt": "Without searching the web again, what city's weather did we look up earlier in this conversation, and what was the exact file name we saved it to?",
        "expected_route": "complex-default",
        "expected_tools": [],
    },
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
    await (
        page.locator(".connection-label")
        .filter(has_text="connected")
        .wait_for(state="visible", timeout=30000)
    )
    await page.wait_for_timeout(1000)


async def send_message(page, text: str):
    print("[EVAL] Sending message...")
    textarea = page.locator("textarea")
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill(text)
    await page.wait_for_timeout(500)
    submit_btn = page.locator(".composer-send")
    await submit_btn.click()
    print("[EVAL] Send button clicked.")


async def wait_for_response(page, msg_count_before: int, timeout_s: int = 1200) -> str:
    print(f"[EVAL] Waiting for response (up to {timeout_s}s)...")
    start_time = time.monotonic()

    await asyncio.sleep(2)

    last_print = start_time
    while time.monotonic() - start_time < timeout_s:
        current_time = time.monotonic()
        elapsed = current_time - start_time

        if current_time - last_print >= 10:
            current_text = await page.evaluate(
                "() => { const els = document.querySelectorAll('.message-assistant'); return els[els.length-1]?.innerText || ''; }"
            )
            tools_running = await page.evaluate(
                "() => { const els = document.querySelectorAll('.tool-name'); return Array.from(els).map(e => e.innerText).join(', '); }"
            )
            tps_est = (len(current_text) / 4.0) / elapsed if elapsed > 0 else 0
            # Print on same line (carriage return) so it doesn't spam
            print(
                f"\\r[EVAL] ... running ({elapsed:.0f}s / {timeout_s}s) | est. TPS: {tps_est:.1f} | tokens: {len(current_text) // 4} | tools: {tools_running or 'none'}",
                end="",
                flush=True,
            )
            last_print = current_time

        # HITL Handling
        hitl_count = await page.evaluate(
            "() => document.querySelectorAll('.hitl-prompt-card.hitl-pending').length"
        )
        if hitl_count > 0:
            print("\n[EVAL] HITL Prompt detected! Resolving HITL...")
            choices_count = await page.evaluate(
                "() => document.querySelectorAll('.hitl-choice-btn').length"
            )
            if choices_count > 0:
                await page.evaluate(
                    "() => document.querySelector('.hitl-choice-btn').click()"
                )
                await page.wait_for_timeout(1000)
            await page.evaluate(
                "() => document.querySelector('.hitl-btn-approve').click()"
            )
            await page.wait_for_timeout(2000)

        msg_count = await page.evaluate(
            "() => document.querySelectorAll('.message-assistant').length"
        )
        textarea_disabled = await page.evaluate(
            "() => document.querySelector('textarea')?.disabled"
        )

        if msg_count > msg_count_before and not textarea_disabled and hitl_count == 0:
            current_text = await page.evaluate(
                "() => { const els = document.querySelectorAll('.message-assistant'); return els[els.length-1]?.innerText || ''; }"
            )
            print(f"\n[EVAL] Response completed in {elapsed:.1f}s.")
            return current_text.strip()

        await asyncio.sleep(1)

    print("\n[EVAL] Timeout waiting for response!")
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

        # Scrape executed tool names from the latest response message block
        tools = await page.evaluate("""() => {
            const userMsgs = document.querySelectorAll('.message-user');
            const lastUser = userMsgs[userMsgs.length - 1];
            if (!lastUser) return [];
            
            let toolsList = [];
            let node = lastUser.nextElementSibling;
            while(node) {
                const els = node.querySelectorAll('.tool-name');
                if (els.length > 0) {
                    els.forEach(el => toolsList.push(el.innerText));
                }
                if (node.classList && node.classList.contains('tool-name')) {
                    toolsList.push(node.innerText);
                }
                node = node.nextElementSibling;
            }
            return toolsList;
        }""")

        return {
            "model": model,
            "route": route,
            "confidence": confidence,
            "tools": tools,
        }
    except Exception as e:
        print(f"[EVAL] Error scraping orchestration data: {e}")
        return {"model": "", "route": "", "confidence": "", "tools": []}


def score_exchange(exchange: dict, expected: dict) -> dict:
    scores = {"route_match": False, "tools_match": False, "grade": 0}

    # 1. Check Route
    if exchange.get("route") == expected.get("expected_route"):
        scores["route_match"] = True
        scores["grade"] += 50

    # 2. Check Tools
    if "expected_tools" in expected:
        expected_tools = expected["expected_tools"]
        executed_tools = exchange.get("executed_tools", [])
        executed_clean = [t.replace("Tool: ", "").strip() for t in executed_tools]

        if expected_tools == []:
            # We strictly expect NO tools to be used
            if len(executed_clean) == 0:
                scores["tools_match"] = True
                scores["grade"] += 50
            else:
                scores["tools_match"] = False
                scores["extra_tools"] = executed_clean
        else:
            # We want to see if ALL expected tools were used
            missing_tools = [
                t
                for t in expected_tools
                if not any(t in exec_t for exec_t in executed_clean)
            ]
            if not missing_tools:
                scores["tools_match"] = True
                scores["grade"] += 50
            else:
                scores["tools_match"] = False
                scores["missing_tools"] = missing_tools
    else:
        # If no tools expected and key omitted, give free points
        scores["tools_match"] = True
        scores["grade"] += 50

    return scores


async def main():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:6]
    project_name = f"FrontierEval_{suffix}"
    project_id = await create_project(project_name)

    eval_data = {
        "project_name": project_name,
        "project_id": project_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware_profile": "Apple M4 Air 24GB (Simulated)",
        "exchanges": [],
    }

    total_score = 0
    max_score = len(TEST_PROMPTS) * 100

    try:
        async with async_playwright() as p:
            print("[EVAL] Starting Playwright Chromium in headless mode...")
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()

            print(f"[EVAL] Navigating to {BASE_URL}...")
            await page.goto(BASE_URL, wait_until="load")
            await wait_for_ready(page)

            print(f"[EVAL] Switching to project: {project_name}")
            await (
                page.locator(".workspace-project-item")
                .filter(has_text=project_name)
                .first.click()
            )
            await page.wait_for_timeout(3000)
            await wait_for_ready(page)

            for index, item in enumerate(TEST_PROMPTS):
                prompt_id = item["id"]
                topic = item["topic"]
                prompt_text = item["prompt"]

                print("\n" + "=" * 80)
                print(
                    f"  EXCHANGE {index + 1}/{len(TEST_PROMPTS)}: [{prompt_id}] {topic}"
                )
                print("=" * 80)

                msg_count_before = await page.evaluate(
                    "() => document.querySelectorAll('.message-assistant').length"
                )

                start_time = time.monotonic()
                await send_message(page, prompt_text)

                response_text = await wait_for_response(page, msg_count_before)
                duration = time.monotonic() - start_time

                # Approximate Tokens per second (~4 chars per token)
                approx_tokens = len(response_text) / 4.0
                tps = approx_tokens / duration if duration > 0 else 0

                orch_data = await get_orchestration_data(page)

                exchange = {
                    "turn_index": index + 1,
                    "prompt_id": prompt_id,
                    "topic": topic,
                    "user_query": prompt_text,
                    "assistant_response": response_text[:500] + "..."
                    if len(response_text) > 500
                    else response_text,
                    "model_badge": orch_data.get("model"),
                    "route": orch_data.get("route"),
                    "confidence": orch_data.get("confidence"),
                    "executed_tools": orch_data.get("tools"),
                    "duration_seconds": round(duration, 2),
                    "approx_tps": round(tps, 2),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

                scores = score_exchange(exchange, item)
                exchange["scores"] = scores
                total_score += scores["grade"]

                print(
                    f"Model Used: {exchange['model_badge']} | Route: {exchange['route']}"
                )
                print(f"Tools Used: {exchange['executed_tools']}")
                print(
                    f"Duration: {exchange['duration_seconds']}s | Approx TPS: {exchange['approx_tps']} t/s"
                )
                print(f"Turn Grade: {scores['grade']}/100")

                eval_data["exchanges"].append(exchange)

                with open(OUTPUT_DATA_FILE, "w") as f:
                    json.dump(eval_data, f, indent=2)

                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{index + 1:02d}_{prompt_id}.png")
                )

            eval_data["final_score"] = f"{total_score}/{max_score}"
            eval_data["score_percentage"] = round((total_score / max_score) * 100, 2)

            with open(OUTPUT_DATA_FILE, "w") as f:
                json.dump(eval_data, f, indent=2)
            print(f"\n[EVAL] Final compiled data saved to {OUTPUT_DATA_FILE}")
            print(
                f"[EVAL] Final Score: {eval_data['final_score']} ({eval_data['score_percentage']}%)"
            )

            await browser.close()
    finally:
        await delete_project(project_id)


if __name__ == "__main__":
    asyncio.run(main())
