#!/usr/bin/env python3
"""
Playwright frontier evaluation for Owlynn V2.

Scores routing + tool usage against the **current** architecture:
- Routes: `simple` | `complex-default` (local Qwen) | `complex-cloud` (DeepSeek)
- Tools: inline `ToolActivityCard` (`.tool-activity-name code`), not legacy `.tool-name`
- Cloud escalation ON (default) → complex tasks expect `complex-cloud`

Usage:
  python scripts/run_local_frontier_eval.py              # auto-detect settings
  python scripts/run_local_frontier_eval.py --profile local   # force local complex route
  python scripts/run_local_frontier_eval.py --profile cloud   # force cloud complex route
  python scripts/run_local_frontier_eval.py --cloud-off       # disable escalation for run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
SCREENSHOT_DIR = REPO_ROOT / "assets" / "frontier_eval_screenshots"
OUTPUT_DATA_FILE = REPO_ROOT / "data" / "frontier_eval_run_data.json"

COMPLEX_ROUTES = frozenset({"complex-default", "complex-cloud"})
SIMPLE_TIMEOUT_S = 180
COMPLEX_TIMEOUT_S = 900

# expected_route: simple | complex (either tier) | complex-default | complex-cloud
TEST_PROMPTS = [
    {
        "id": "F1.1",
        "topic": "Router Precision (Simple)",
        "prompt": "Hello there! Hope you are doing well today.",
        "expected_route": "simple",
        "timeout_s": SIMPLE_TIMEOUT_S,
        "min_response_chars": 8,
    },
    {
        "id": "F2.1",
        "topic": "Router Precision (Complex)",
        "prompt": "Can you review the python code in this function and tell me if it has bugs?",
        "expected_route": "complex",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 40,
    },
    {
        "id": "F3.1",
        "topic": "Deep Tool Iteration",
        "prompt": (
            "Search the web for the weather in Tokyo right now. Then create a file in my "
            "workspace named 'tokyo_weather.txt' with the forecast summary."
        ),
        "expected_route": "complex",
        "expected_tools": ["web_search", "write_workspace_file"],
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 80,
    },
    {
        "id": "F4.1",
        "topic": "Massive Context Ingestion",
        "prompt": (
            "Read the file `docs/STATUS.md` from the workspace. "
            "What are the 'Architectural Concerns' listed there?"
        ),
        "expected_route": "complex",
        "expected_tools": ["read_workspace_file"],
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 40,
    },
    {
        "id": "F5.1",
        "topic": "Sustained Reasoning",
        "prompt": (
            "Write a complete React component for a Data Dashboard. It needs a header, a sidebar, "
            "and a main content area with a mock chart. Also write the CSS in a separate file named "
            "'dashboard.css'. Give me the full code without placeholders."
        ),
        "expected_route": "complex",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 200,
    },
    {
        "id": "F6.1",
        "topic": "Memory Retention",
        "prompt": (
            "Without searching the web again, what city's weather did we look up earlier in this "
            "conversation, and what was the exact file name we saved it to?"
        ),
        "expected_route": "complex",
        "expected_tools": [],
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 20,
    },
]


def _has_dsml_leak(text: str) -> bool:
    return "DSML" in text or "｜｜" in text or "tool_calls" in text and "invoke" in text


def _normalize_response(text: str) -> str:
    """Strip avatar noise and timestamps for length checks."""
    lines = [
        ln
        for ln in (text or "").splitlines()
        if ln.strip() and ln.strip().lower() not in {"o", "just now"}
    ]
    return "\n".join(lines).strip()


async def fetch_runtime_profile() -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{API_URL}/api/unified-settings")
            settings = resp.json() if resp.status_code == 200 else {}
        except Exception:
            settings = {}
        try:
            cloud_resp = await client.get(f"{API_URL}/api/cloud-status")
            cloud_status = cloud_resp.json() if cloud_resp.status_code == 200 else {}
        except Exception:
            cloud_status = {}
    cloud_on = settings.get("cloud_escalation_enabled", True) is not False
    cloud_ok = bool(cloud_status.get("available") and cloud_status.get("key_valid"))
    return {
        "cloud_escalation_enabled": cloud_on,
        "cloud_available": cloud_ok,
        "cloud_model": cloud_status.get("model", ""),
        "effective_profile": "cloud" if cloud_on and cloud_ok else "local",
    }


async def set_cloud_escalation(enabled: bool) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.put(
            f"{API_URL}/api/unified-settings",
            json={"cloud_escalation_enabled": enabled},
        )


def resolve_expected_route(expected: str, *, profile: str) -> str:
    if expected == "complex":
        return "complex-cloud" if profile == "cloud" else "complex-default"
    return expected


def route_matches(actual: str, expected: str, *, profile: str) -> bool:
    if not actual:
        return False
    if expected == "complex":
        if profile == "cloud":
            return actual == "complex-cloud"
        return actual == "complex-default"
    if expected == "complex-cloud" and profile == "local":
        return actual in COMPLEX_ROUTES  # lenient if misconfigured
    return actual == expected


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


async def wait_for_ready(page) -> None:
    print("[EVAL] Waiting for connection status to be connected...")
    await (
        page.locator(".connection-label")
        .filter(has_text="connected")
        .wait_for(state="visible", timeout=30000)
    )
    await page.wait_for_timeout(1000)


async def send_message(page, text: str) -> None:
    print("[EVAL] Sending message...")
    textarea = page.locator("textarea")
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill(text)
    await page.wait_for_timeout(500)
    await page.locator(".composer-send").click()
    print("[EVAL] Send button clicked.")


async def wait_for_response(
    page,
    msg_count_before: int,
    *,
    timeout_s: int,
    min_chars: int,
) -> tuple[str, bool]:
    print(f"[EVAL] Waiting for response (up to {timeout_s}s, min {min_chars} chars)...")
    start_time = time.monotonic()
    await asyncio.sleep(2)
    last_print = start_time

    while time.monotonic() - start_time < timeout_s:
        elapsed = time.monotonic() - start_time
        if time.monotonic() - last_print >= 10:
            current_text = await page.evaluate(
                "() => { const els = document.querySelectorAll('.message-assistant'); "
                "return els[els.length-1]?.innerText || ''; }"
            )
            tools_running = await page.evaluate(
                "() => Array.from(document.querySelectorAll('.tool-activity-name code'))"
                ".map(e => e.innerText).join(', ')"
            )
            tps_est = (len(current_text) / 4.0) / elapsed if elapsed > 0 else 0
            print(
                f"\r[EVAL] ... running ({elapsed:.0f}s / {timeout_s}s) | "
                f"est. TPS: {tps_est:.1f} | chars: {len(current_text)} | "
                f"tools: {tools_running or 'none'}",
                end="",
                flush=True,
            )
            last_print = time.monotonic()

        hitl_count = await page.evaluate(
            "() => document.querySelectorAll('.hitl-prompt-card.hitl-pending').length"
        )
        if hitl_count > 0:
            print("\n[EVAL] HITL Prompt detected! Resolving...")
            if await page.evaluate(
                "() => document.querySelectorAll('.hitl-choice-btn').length"
            ):
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
        current_text = await page.evaluate(
            "() => { const els = document.querySelectorAll('.message-assistant'); "
            "return els[els.length-1]?.innerText || ''; }"
        )
        normalized = _normalize_response(current_text)

        if (
            msg_count > msg_count_before
            and not textarea_disabled
            and hitl_count == 0
            and len(normalized) >= min_chars
        ):
            print(
                f"\n[EVAL] Response completed in {elapsed:.1f}s ({len(normalized)} chars)."
            )
            return current_text.strip(), True

        await asyncio.sleep(1)

    print("\n[EVAL] Timeout waiting for response!")
    current_text = await page.evaluate(
        "() => { const els = document.querySelectorAll('.message-assistant'); "
        "return els[els.length-1]?.innerText || ''; }"
    )
    return current_text.strip(), False


async def get_orchestration_data(page) -> dict:
    try:
        model = await page.evaluate(
            "() => document.querySelector('.model-badge')?.innerText || ''"
        )
        route = await page.evaluate(
            "() => document.querySelector('.route-badge')?.innerText || ''"
        )
        confidence = await page.evaluate(
            "() => document.querySelector('.orchestration-gauge-value')?.innerText || ''"
        )
        tools = await page.evaluate("""() => {
            const userMsgs = document.querySelectorAll('.message-user');
            const lastUser = userMsgs[userMsgs.length - 1];
            if (!lastUser) return [];
            const toolsList = [];
            let node = lastUser.nextElementSibling;
            while (node) {
                node.querySelectorAll('.tool-activity-name code').forEach(el => {
                    if (el.innerText) toolsList.push(el.innerText.trim());
                });
                if (node.classList?.contains('message-assistant')) break;
                node = node.nextElementSibling;
            }
            return [...new Set(toolsList)];
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


def score_exchange(exchange: dict, expected: dict, *, profile: str) -> dict:
    scores: dict = {
        "route_match": False,
        "tools_match": False,
        "response_ok": False,
        "dsml_leak": False,
        "grade": 0,
    }
    expected_route = expected.get("expected_route", "")
    min_chars = expected.get("min_response_chars", 10)
    body = _normalize_response(exchange.get("assistant_response_full", ""))
    scores["response_ok"] = len(body) >= min_chars
    scores["dsml_leak"] = _has_dsml_leak(body)

    if route_matches(exchange.get("route", ""), expected_route, profile=profile):
        scores["route_match"] = True
        scores["grade"] += 40
    elif expected_route == "complex" and exchange.get("route") in COMPLEX_ROUTES:
        scores["route_match"] = True
        scores["grade"] += 30  # partial: complex but wrong tier

    if scores["response_ok"]:
        scores["grade"] += 20
    if scores["dsml_leak"]:
        scores["grade"] = max(0, scores["grade"] - 15)

    if "expected_tools" in expected:
        expected_tools = expected["expected_tools"]
        executed = exchange.get("executed_tools", [])
        if expected_tools == []:
            scores["tools_match"] = len(executed) == 0
        else:
            missing = [t for t in expected_tools if t not in executed]
            scores["tools_match"] = not missing
            if missing:
                scores["missing_tools"] = missing
        if scores["tools_match"]:
            scores["grade"] += 40
    else:
        scores["tools_match"] = True
        scores["grade"] += 40

    scores["grade"] = min(100, scores["grade"])
    return scores


async def main() -> None:
    parser = argparse.ArgumentParser(description="Owlynn frontier evaluation")
    parser.add_argument(
        "--profile",
        choices=("auto", "local", "cloud"),
        default="auto",
        help="Expected complex tier (default: read from API)",
    )
    parser.add_argument(
        "--cloud-off",
        action="store_true",
        help="Disable cloud escalation for this run (restores prior setting after)",
    )
    args = parser.parse_args()

    runtime = await fetch_runtime_profile()
    prior_cloud = runtime["cloud_escalation_enabled"]
    if args.cloud_off:
        print("[EVAL] Disabling cloud escalation for this run...")
        await set_cloud_escalation(False)
        runtime = await fetch_runtime_profile()

    if args.profile == "auto":
        profile = runtime["effective_profile"]
    else:
        profile = args.profile

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:6]
    project_name = f"FrontierEval_{suffix}"
    project_id = await create_project(project_name)

    eval_data = {
        "project_name": project_name,
        "project_id": project_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "eval_version": "2026-06-10",
        "runtime_profile": profile,
        "cloud_escalation_enabled": runtime["cloud_escalation_enabled"],
        "cloud_available": runtime["cloud_available"],
        "cloud_model": runtime["cloud_model"],
        "hardware_profile": "Apple M4 Air 24GB",
        "exchanges": [],
    }

    total_score = 0
    max_score = len(TEST_PROMPTS) * 100

    try:
        async with async_playwright() as p:
            print("[EVAL] Starting Playwright Chromium (headless)...")
            browser = await p.chromium.launch(headless=True)
            page = await (
                await browser.new_context(viewport={"width": 1440, "height": 900})
            ).new_page()

            print(
                f"[EVAL] Profile: {profile} | cloud_escalation={runtime['cloud_escalation_enabled']}"
            )
            await page.goto(BASE_URL, wait_until="load")
            await wait_for_ready(page)

            await (
                page.locator(".workspace-project-item")
                .filter(has_text=project_name)
                .first.click()
            )
            await page.wait_for_timeout(3000)
            await wait_for_ready(page)

            for index, item in enumerate(TEST_PROMPTS):
                prompt_id = item["id"]
                print("\n" + "=" * 80)
                print(
                    f"  EXCHANGE {index + 1}/{len(TEST_PROMPTS)}: [{prompt_id}] {item['topic']}"
                )
                print("=" * 80)

                msg_count_before = await page.evaluate(
                    "() => document.querySelectorAll('.message-assistant').length"
                )
                timeout_s = item.get("timeout_s", COMPLEX_TIMEOUT_S)
                min_chars = item.get("min_response_chars", 10)

                start_time = time.monotonic()
                await send_message(page, item["prompt"])
                response_text, completed = await wait_for_response(
                    page,
                    msg_count_before,
                    timeout_s=timeout_s,
                    min_chars=min_chars,
                )
                duration = time.monotonic() - start_time
                orch = await get_orchestration_data(page)

                exchange = {
                    "turn_index": index + 1,
                    "prompt_id": prompt_id,
                    "topic": item["topic"],
                    "user_query": item["prompt"],
                    "assistant_response": response_text[:500]
                    + ("..." if len(response_text) > 500 else ""),
                    "assistant_response_full": response_text,
                    "response_completed": completed,
                    "expected_route_resolved": resolve_expected_route(
                        item["expected_route"], profile=profile
                    ),
                    "model_badge": orch.get("model"),
                    "route": orch.get("route"),
                    "confidence": orch.get("confidence"),
                    "executed_tools": orch.get("tools"),
                    "duration_seconds": round(duration, 2),
                    "approx_tps": round((len(response_text) / 4.0) / duration, 2)
                    if duration > 0
                    else 0,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                scores = score_exchange(exchange, item, profile=profile)
                exchange["scores"] = scores
                total_score += scores["grade"]

                print(
                    f"Model: {exchange['model_badge']} | Route: {exchange['route']} "
                    f"(expected {exchange['expected_route_resolved']})"
                )
                print(
                    f"Tools: {exchange['executed_tools']} | completed={completed} | dsml={scores['dsml_leak']}"
                )
                print(f"Grade: {scores['grade']}/100")

                eval_data["exchanges"].append(exchange)
                OUTPUT_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(OUTPUT_DATA_FILE, "w") as f:
                    json.dump(eval_data, f, indent=2)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{index + 1:02d}_{prompt_id}.png")
                )

            eval_data["final_score"] = f"{total_score}/{max_score}"
            eval_data["score_percentage"] = round((total_score / max_score) * 100, 2)
            with open(OUTPUT_DATA_FILE, "w") as f:
                json.dump(eval_data, f, indent=2)
            print(f"\n[EVAL] Saved {OUTPUT_DATA_FILE}")
            print(
                f"[EVAL] Final: {eval_data['final_score']} ({eval_data['score_percentage']}%)"
            )
            await browser.close()
    finally:
        if args.cloud_off and prior_cloud:
            print("[EVAL] Restoring cloud escalation...")
            await set_cloud_escalation(True)
        await delete_project(project_id)


if __name__ == "__main__":
    asyncio.run(main())
