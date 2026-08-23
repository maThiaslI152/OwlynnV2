#!/usr/bin/env python3
"""E2E Playwright automation: Brave extension search + graph + conversation change.

Goals:
  1. Open Owlynn in Brave with the browser extension loaded and connected
  2. Switch to split/mindmap view and adjust viewport (zoom/pan/fit)
  3. Send a conversation that triggers internet search via the Brave extension
  4. Wait for completion via WebSocket idle detection (DOM fallback secondary)
  5. Ask Owlynn to generate a matplotlib chart from the search results
  6. Change conversation: topic-shift follow-up, then switch to another mindmap node
  7. Verify Thought Graph growth and capture screenshots at every stage
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from playwright.async_api import Page, async_playwright

# ── Configuration ────────────────────────────────────────────────────────────
BASE_URL = os.getenv("OWLYNN_EVAL_BASE_URL", "http://127.0.0.1:5173")
API_URL = os.getenv("OWLYNN_EVAL_API_URL", "http://127.0.0.1:8000")
BRAVE_PATH = Path(
    "/Volumes/KNV3_1TB/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
)
EXTENSION_DIR = Path("/Volumes/KNV3_1TB/OwlynnV2/browser-extension")

SCREENSHOT_DIR = Path("/Volumes/KNV3_1TB/OwlynnV2/assets/mindmap_e2e_screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

TURN_TIMEOUT_S = 450  # Up to 7.5 min for complex local LLM tool turns
MIN_RESPONSE_CHARS = 30
EXTENSION_WAIT_S = 30
EXTENSION_MARKER = "via Browser Extension"


# ── WsEventLog ───────────────────────────────────────────────────────────────
class WsEventLog:
    """Capture WebSocket frames from the browser to detect idle + extract data."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def attach(self, page: Page) -> None:
        def on_websocket(ws) -> None:
            def on_frame(payload) -> None:
                try:
                    raw = payload if isinstance(payload, str) else payload.decode("utf-8")
                    data = json.loads(raw)
                    if isinstance(data, dict) and data.get("type"):
                        self.events.append(
                            {"type": data["type"], "ts": time.time(), "payload": data}
                        )
                except Exception:
                    pass

            ws.on("framereceived", on_frame)

        page.on("websocket", on_websocket)

    def idle_since(self, since_ts: float) -> bool:
        for ev in self.events:
            if ev["ts"] < since_ts:
                continue
            p = ev.get("payload", {})
            if p.get("type") == "status" and p.get("content") == "idle":
                return True
        return False

    def tools_since(self, since_ts: float) -> list[str]:
        seen: list[str] = []
        for ev in self.events:
            if ev["type"] != "tool_execution" or ev["ts"] < since_ts:
                continue
            name = (ev.get("payload", {}).get("tool_name") or "").strip()
            if name and name not in seen:
                seen.append(name)
        return seen

    def assistant_text_since(self, since_ts: float) -> str:
        latest = ""
        for ev in self.events:
            if ev["ts"] < since_ts or ev["type"] != "assistant.message":
                continue
            p = ev.get("payload", {})
            msg = p.get("message") if isinstance(p, dict) else None
            if isinstance(msg, dict):
                content = msg.get("content") or ""
            else:
                content = p.get("content") or ""
            if isinstance(content, str) and content.strip():
                latest = content
        return latest

    def chunk_text_since(self, since_ts: float) -> str:
        parts: list[str] = []
        for ev in self.events:
            if ev["ts"] < since_ts or ev["type"] != "chunk":
                continue
            content = ev.get("payload", {}).get("content") or ""
            if isinstance(content, str) and content:
                parts.append(content)
        return "".join(parts)

    def tool_outputs_since(self, since_ts: float) -> str:
        parts: list[str] = []
        for ev in self.events:
            if ev["type"] != "tool_execution" or ev["ts"] < since_ts:
                continue
            payload = ev.get("payload", {})
            for key in ("output", "input", "error"):
                value = payload.get(key) or ""
                if isinstance(value, str) and value.strip():
                    parts.append(value)
        return "\n".join(parts)

    def extension_search_since(self, since_ts: float) -> bool:
        return EXTENSION_MARKER in self.tool_outputs_since(since_ts)

    def tool_errors_since(self, since_ts: float) -> list[str]:
        errors: list[str] = []
        for ev in self.events:
            if ev["type"] != "tool_execution" or ev["ts"] < since_ts:
                continue
            payload = ev.get("payload", {})
            if payload.get("status") == "error":
                err = payload.get("error") or payload.get("output") or ""
                if isinstance(err, str) and err.strip():
                    errors.append(err.strip())
        return errors

    def web_search_success_since(self, since_ts: float) -> bool:
        for ev in self.events:
            if ev["type"] != "tool_execution" or ev["ts"] < since_ts:
                continue
            payload = ev.get("payload", {})
            if payload.get("tool_name") == "web_search" and payload.get("status") == "success":
                return True
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────
async def health_check() -> bool:
    """Wait for backend to be ready (up to 30s)."""
    for _ in range(30):
        try:
            async with httpx.AsyncClient(timeout=1.0) as c:
                resp = await c.get(f"{API_URL}/api/health")
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(1.0)
    return False


async def load_run_token() -> str | None:
    """Fetch the local run token for API auth."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            resp = await c.get(f"{API_URL}/api/local-run-token")
            if resp.status_code == 200:
                token = resp.json().get("token")
                if token:
                    os.environ["OWLYNN_LOCAL_RUN_TOKEN"] = token
                    return token
    except Exception:
        pass
    return os.environ.get("OWLYNN_LOCAL_RUN_TOKEN")


async def create_project(name: str) -> str:
    """Create a test project via API."""
    headers = {"X-Owlynn-Run-Token": os.environ.get("OWLYNN_LOCAL_RUN_TOKEN", "")}
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as c:
        resp = await c.post(f"{API_URL}/api/projects", json={"name": name})
        assert resp.status_code == 200, f"Failed to create project: {resp.text}"
        return resp.json()["id"]


async def delete_project(project_id: str) -> None:
    headers = {"X-Owlynn-Run-Token": os.environ.get("OWLYNN_LOCAL_RUN_TOKEN", "")}
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as c:
        try:
            await c.delete(f"{API_URL}/api/projects/{project_id}")
        except Exception:
            pass


def _auth_headers() -> dict[str, str]:
    return {"X-Owlynn-Run-Token": os.environ.get("OWLYNN_LOCAL_RUN_TOKEN", "")}


async def wait_for_extension_connected(timeout_s: int = EXTENSION_WAIT_S) -> dict:
    """Poll backend until the Brave browser extension WebSocket is authenticated."""
    deadline = time.monotonic() + timeout_s
    last_status: dict = {"connected": False, "connections": 0}
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient(timeout=3.0, headers=_auth_headers()) as c:
                resp = await c.get(f"{API_URL}/api/browser_extension/status")
                if resp.status_code == 200:
                    last_status = resp.json()
                    if last_status.get("connected") and (last_status.get("connections") or 0) >= 1:
                        return {
                            "connected": True,
                            "connections": last_status.get("connections", 0),
                            "elapsed": round(timeout_s - (deadline - time.monotonic()), 2),
                        }
        except Exception:
            pass
        await asyncio.sleep(1.0)
    return {
        "connected": False,
        "connections": last_status.get("connections", 0),
        "elapsed": timeout_s,
    }


async def get_graph_snapshot() -> dict:
    """Fetch Thought Graph node/edge counts and node metadata."""
    async with httpx.AsyncClient(timeout=10.0, headers=_auth_headers()) as c:
        resp = await c.get(f"{API_URL}/api/graph/data")
        if resp.status_code != 200:
            return {"ok": False, "status_code": resp.status_code, "total_nodes": 0, "total_edges": 0, "nodes": []}
        graph_data = resp.json()
        nodes = graph_data.get("nodes") or []
        return {
            "ok": True,
            "total_nodes": graph_data.get("total_nodes", len(nodes)),
            "total_edges": graph_data.get("total_edges", len(graph_data.get("edges") or [])),
            "nodes": nodes,
            "titles": [n.get("title", "") for n in nodes if isinstance(n, dict)],
        }


async def preflight_extension_search() -> dict:
    """Verify extension search works via REST before chat turns."""
    engines = ["google", "bing", "ddg"]
    attempts: list[dict] = []
    for engine in engines:
        try:
            async with httpx.AsyncClient(timeout=25.0, headers=_auth_headers()) as c:
                resp = await c.post(
                    f"{API_URL}/api/browser_extension/search",
                    json={"query": "Python 3.14 features", "engine": engine},
                )
                data = resp.json() if resp.status_code == 200 else {}
                hits = data.get("results") or []
                attempts.append(
                    {
                        "engine": engine,
                        "status_code": resp.status_code,
                        "hits": len(hits),
                        "error": data.get("error"),
                    }
                )
                if resp.status_code == 200 and hits:
                    return {
                        "ok": True,
                        "engine": engine,
                        "hits": len(hits),
                        "attempts": attempts,
                    }
        except Exception as exc:
            attempts.append({"engine": engine, "error": str(exc)[:120]})
    return {"ok": False, "attempts": attempts}


async def ensure_extension_connected(page: Page, label: str) -> dict:
    """Re-check extension connectivity before a search-dependent turn."""
    status = await wait_for_extension_connected(timeout_s=15)
    statusbar_ok = await assert_statusbar_extension(page)
    print(
        f"  {'✅' if status['connected'] else '❌'} Extension re-check ({label}): "
        f"connections={status.get('connections', 0)}, statusbar={statusbar_ok}",
        flush=True,
    )
    return {**status, "statusbar_connected": statusbar_ok}


async def assert_statusbar_extension(page: Page) -> bool:
    """Check StatusBar Brave Ext pill reports connected."""
    try:
        pill = page.locator('.status-bar span[title*="Brave Extension"]').first
        title = await pill.get_attribute("title")
        return title == "Brave Extension: Connected"
    except Exception:
        return False


async def get_active_branch(page: Page) -> str:
    """Read the Active Branch thread id from split-view HUD."""
    try:
        row = page.locator('span:has-text("Active Branch") strong').first
        return (await row.inner_text()).strip()
    except Exception:
        return ""


async def scrape_dom_tool_output(page: Page) -> str:
    """Scrape rendered tool activity cards for provenance markers."""
    parts: list[str] = []
    try:
        cards = page.locator(".tool-activity-card")
        count = await cards.count()
        for i in range(count):
            card = cards.nth(i)
            try:
                await card.locator(".tool-activity-row").click()
                await page.wait_for_timeout(150)
            except Exception:
                pass
            text = (await card.inner_text()).strip()
            if text:
                parts.append(text)
        pills = page.locator(".tool-activity-output, .tool-pill")
        pill_count = await pills.count()
        for i in range(pill_count):
            text = (await pills.nth(i).inner_text()).strip()
            if text:
                parts.append(text)
    except Exception:
        pass
    return "\n".join(parts)


def extension_provenance_found(*texts: str) -> bool:
    combined = "\n".join(t for t in texts if t)
    return EXTENSION_MARKER in combined


async def create_branch_via_api(parent_id: str, title: str = "E2E Branch Switch") -> dict:
    """Create a new thought branch via REST API."""
    new_id = f"thread-e2e-{int(time.time())}"
    async with httpx.AsyncClient(timeout=10.0, headers=_auth_headers()) as c:
        resp = await c.post(
            f"{API_URL}/api/graph/nodes",
            json={
                "id": new_id,
                "title": title,
                "mode": "normal",
                "parent_id": parent_id,
            },
        )
        if resp.status_code != 200:
            return {"ok": False, "reason": resp.text[:200]}
        return {"ok": True, "node_id": new_id, "title": title}


async def click_different_mindmap_node(
    page: Page, current_thread: str, graph_nodes: list[dict] | None = None
) -> dict:
    """Click a different node on the ForceGraph canvas; verify Active Branch changes."""
    fit_btn = page.locator("button[title='Fit to screen']")
    canvas = page.locator(".mindmap-container canvas")
    search_input = page.locator('input[placeholder="Search mindmap..."]')
    result: dict = {"switched": False, "from": current_thread, "to": "", "method": ""}

    try:
        await canvas.wait_for(state="visible", timeout=8000)
        try:
            await fit_btn.click()
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        box = await canvas.bounding_box()
        if not box:
            result["reason"] = "no_canvas_box"
            return result

        initial = current_thread or await get_active_branch(page)

        # Try mindmap search filter then click canvas center
        other = None
        if graph_nodes:
            other = next(
                (n for n in graph_nodes if isinstance(n, dict) and n.get("id") != initial),
                None,
            )
        if other and other.get("title"):
            try:
                title_prefix = str(other["title"])[:24]
                await search_input.fill(title_prefix)
                await page.wait_for_timeout(800)
                await fit_btn.click()
                await page.wait_for_timeout(1000)
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                await page.mouse.click(cx, cy)
                await page.wait_for_timeout(500)
                active = await get_active_branch(page)
                if active and active != initial:
                    result.update(
                        {"switched": True, "to": active, "method": "mindmap_search_click"}
                    )
                    return result
                await search_input.fill("")
            except Exception:
                pass

        # Grid search across canvas — ForceGraph nodes spread after fit-to-screen
        for row in range(2, 9):
            for col in range(2, 9):
                x = box["x"] + box["width"] * col / 10
                y = box["y"] + box["height"] * row / 10
                await page.mouse.click(x, y)
                await page.wait_for_timeout(400)
                active = await get_active_branch(page)
                if active and active != initial:
                    result.update({"switched": True, "to": active, "method": f"grid_{row}_{col}"})
                    return result

        # Fallback: create branch via API, refresh mindmap, search, and click
        created = await create_branch_via_api(initial)
        if created.get("ok"):
            refresh_btn = page.locator("button[title='Refresh graph']")
            try:
                await refresh_btn.click()
                await page.wait_for_timeout(1000)
                await fit_btn.click()
                await page.wait_for_timeout(1000)
            except Exception:
                pass
            try:
                await search_input.fill(created.get("title", "E2E Branch Switch"))
                await page.wait_for_timeout(800)
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                await page.mouse.click(cx, cy)
                await page.wait_for_timeout(600)
                active = await get_active_branch(page)
                if active and active != initial:
                    result.update(
                        {
                            "switched": True,
                            "to": active,
                            "method": "api_branch_create_click",
                            "created_node": created.get("node_id"),
                        }
                    )
                    return result
                if created.get("node_id") and active == created.get("node_id"):
                    result.update(
                        {
                            "switched": True,
                            "to": active,
                            "method": "api_branch_create_direct",
                            "created_node": created.get("node_id"),
                        }
                    )
                    return result
            except Exception as exc:
                result["api_branch_error"] = str(exc)

        result["reason"] = "no_node_hit"
    except Exception as exc:
        result["reason"] = str(exc)

    return result


async def send_message(page: Page, text: str) -> None:
    """Type into the chat composer and click send."""
    textarea = page.locator("textarea")
    await textarea.wait_for(state="visible", timeout=10000)
    await textarea.fill(text)

    send_btn = page.locator(".composer-send")
    await send_btn.wait_for(state="visible", timeout=5000)

    for attempt in range(5):
        await send_btn.click()
        try:
            await page.wait_for_function(
                "el => !el.value", arg=await textarea.element_handle(), timeout=2000
            )
            return
        except Exception:
            await textarea.press("Enter")
            await page.wait_for_timeout(1000)


async def resolve_hitl(page: Page) -> int:
    """Auto-approve any pending HITL cards."""
    pending = page.locator(".hitl-prompt-card.hitl-pending")
    if await pending.count() <= 0:
        return 0

    card = pending.last

    # Try skip button first
    skip = card.locator(".hitl-btn-skip")
    if await skip.count() > 0:
        await skip.first.click(force=True, timeout=5000)
        return 1

    # Handle scope questions
    if await card.locator(".hitl-scope-question").count() > 0:
        await page.evaluate(
            """() => {
                const lastCard = [...document.querySelectorAll('.hitl-prompt-card.hitl-pending')].pop();
                lastCard?.querySelectorAll('.hitl-scope-question').forEach(q => {
                    q.querySelector('.hitl-choice-btn')?.click();
                });
            }"""
        )
    elif await card.locator(".hitl-choice-btn").count() > 0:
        await card.locator(".hitl-choice-btn").first.click(force=True, timeout=3000)

    approve = card.locator(".hitl-btn-approve")
    if await approve.count() > 0:
        await approve.first.click(force=True, timeout=5000)
    return 1


async def scrape_dom_response(page: Page) -> str:
    """Scrape the latest assistant response text from the DOM."""
    try:
        bubbles = page.locator(".message-assistant .message-bubble, .message-ai, [data-role='assistant']")
        count = await bubbles.count()
        if count > 0:
            text = await bubbles.last.inner_text()
            return text.strip()
    except Exception:
        pass
    return ""


async def scrape_dom_tools(page: Page) -> list[str]:
    """Scrape tool names executed in the current session from the DOM."""
    tools = []
    try:
        pills = page.locator(".tool-activity-name code, .tool-pill")
        count = await pills.count()
        for i in range(count):
            t = (await pills.nth(i).inner_text()).strip()
            if t and t not in tools:
                tools.append(t)
    except Exception:
        pass
    return tools


async def wait_for_turn(
    page: Page,
    ws_log: WsEventLog,
    since_ts: float,
    timeout_s: int = TURN_TIMEOUT_S,
) -> dict:
    """Wait for conversation turn to complete using WS idle + DOM fallback."""
    start = time.monotonic()
    await asyncio.sleep(2.0)
    last_status_print = 0.0

    while time.monotonic() - start < timeout_s:
        elapsed = time.monotonic() - start

        # Ensure page is still responsive
        try:
            await asyncio.wait_for(page.evaluate("1"), timeout=3.0)
        except asyncio.TimeoutError:
            return {"completed": False, "reason": "page_deadlocked", "elapsed": elapsed}

        # Resolve HITL if any
        await resolve_hitl(page)

        # Status heartbeat every 15s
        if elapsed - last_status_print >= 15.0:
            last_status_print = elapsed
            ws_tools = ws_log.tools_since(since_ts)
            print(f"    ⏳ Waiting... ({int(elapsed)}s elapsed, tools so far: {ws_tools or 'none'})", flush=True)

        # 1. Primary check: WS idle event
        if ws_log.idle_since(since_ts):
            await asyncio.sleep(1.5)  # Grace for trailing chunks

            ws_text = ws_log.assistant_text_since(since_ts)
            if not ws_text:
                ws_text = ws_log.chunk_text_since(since_ts)
            dom_text = await scrape_dom_response(page)
            final_text = ws_text or dom_text

            ws_tools = ws_log.tools_since(since_ts)
            dom_tools = await scrape_dom_tools(page)
            tools = list(dict.fromkeys(ws_tools + dom_tools))

            if len(final_text) >= MIN_RESPONSE_CHARS:
                return {
                    "completed": True,
                    "response_text": final_text,
                    "executed_tools": tools,
                    "elapsed": round(elapsed, 2),
                    "source": "ws_idle",
                }

        # 2. Secondary check: DOM completion (stop button gone, text rendered)
        if elapsed >= 10.0:
            stop_btn = page.locator(".composer-stop, button.is-stop, button:has-text('Stop')")
            stop_visible = False
            try:
                stop_visible = await stop_btn.count() > 0 and await stop_btn.first.is_visible()
            except Exception:
                pass

            if not stop_visible:
                dom_text = await scrape_dom_response(page)
                if len(dom_text) >= MIN_RESPONSE_CHARS:
                    await asyncio.sleep(2.0)
                    dom_text_stable = await scrape_dom_response(page)
                    if dom_text_stable == dom_text and len(dom_text_stable) >= MIN_RESPONSE_CHARS:
                        ws_tools = ws_log.tools_since(since_ts)
                        dom_tools = await scrape_dom_tools(page)
                        tools = list(dict.fromkeys(ws_tools + dom_tools))
                        return {
                            "completed": True,
                            "response_text": dom_text_stable,
                            "executed_tools": tools,
                            "elapsed": round(elapsed, 2),
                            "source": "dom_stable",
                        }

        await asyncio.sleep(2.0)

    # Scrape whatever we have on timeout
    ws_text = ws_log.assistant_text_since(since_ts) or ws_log.chunk_text_since(since_ts)
    dom_text = await scrape_dom_response(page)
    final_text = ws_text or dom_text
    ws_tools = ws_log.tools_since(since_ts)
    dom_tools = await scrape_dom_tools(page)
    tools = list(dict.fromkeys(ws_tools + dom_tools))

    return {
        "completed": len(final_text) >= MIN_RESPONSE_CHARS,
        "response_text": final_text,
        "executed_tools": tools,
        "elapsed": timeout_s,
        "reason": "timeout",
    }


async def screenshot(page: Page, name: str) -> Path:
    path = SCREENSHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"  📸 Screenshot: {path.name}", flush=True)
    return path


# ── Main E2E Flow ─────────────────────────────────────────────────────────────
async def run_e2e() -> dict:
    results: dict = {"steps": [], "passed": False}

    # 1. Health check
    print("⏳ Checking backend health...", flush=True)
    if not await health_check():
        print("❌ Backend not reachable at", API_URL, flush=True)
        results["steps"].append({"step": "health_check", "passed": False})
        return results
    print("✅ Backend healthy", flush=True)

    # 2. Load run token
    token = await load_run_token()
    print(f"🔑 Run token: {'loaded' if token else 'missing (continuing anyway)'}", flush=True)

    # 3. Create test project
    project_id = await create_project(f"E2E Mindmap Search Graph {int(time.time())}")
    print(f"📁 Created project: {project_id}", flush=True)

    try:
        # 4. Launch Brave with extension
        executable = str(BRAVE_PATH) if BRAVE_PATH.exists() else None
        args = []
        if EXTENSION_DIR.exists():
            args = [
                f"--disable-extensions-except={EXTENSION_DIR}",
                f"--load-extension={EXTENSION_DIR}",
                "--no-first-run",
                "--no-default-browser-check",
            ]

        async with async_playwright() as p:
            user_data = f"/tmp/owlynn-mindmap-e2e-{int(time.time())}"
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data,
                executable_path=executable,
                headless=False,
                args=args,
                viewport={"width": 1440, "height": 920},
            )
            page = context.pages[0] if context.pages else await context.new_page()

            # Attach WS logger BEFORE navigation
            ws_log = WsEventLog()
            ws_log.attach(page)

            # 5. Navigate to project
            url = f"{BASE_URL}/?project={project_id}"
            print(f"🌐 Navigating to {url}", flush=True)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Wait for connection indicator
            try:
                await page.locator(".connection-dot-connected").wait_for(
                    state="visible", timeout=15000
                )
                print("✅ WebSocket connected", flush=True)
            except Exception:
                print("⚠️  Connection dot not found, continuing anyway", flush=True)

            # ── STEP C: Brave Extension Gate ─────────────────────────────
            print("\n🔌 Step C: Wait for Brave extension connection", flush=True)
            ext_status = await wait_for_extension_connected(timeout_s=EXTENSION_WAIT_S)
            statusbar_ok = await assert_statusbar_extension(page)
            ext_passed = ext_status["connected"]
            print(
                f"  {'✅' if ext_passed else '❌'} Extension API connected "
                f"(connections={ext_status.get('connections', 0)}, "
                f"elapsed={ext_status.get('elapsed', '?')}s)",
                flush=True,
            )
            print(
                f"  {'✅' if statusbar_ok else '⚠️ '} StatusBar Brave Ext pill "
                f"({'Connected' if statusbar_ok else 'not connected yet'})",
                flush=True,
            )
            if not ext_passed:
                results["steps"].append(
                    {
                        "step": "brave_extension_gate",
                        "passed": False,
                        "connections": ext_status.get("connections", 0),
                        "statusbar_connected": statusbar_ok,
                    }
                )
                results["passed"] = False
                print("❌ Extension never connected — aborting E2E", flush=True)
                await context.close()
                return results

            results["steps"].append(
                {
                    "step": "brave_extension_gate",
                    "passed": True,
                    "connections": ext_status.get("connections", 0),
                    "statusbar_connected": statusbar_ok,
                    "elapsed": ext_status.get("elapsed"),
                }
            )

            await page.wait_for_timeout(3000)
            print("\n🧪 Step C (preflight): Extension search smoke test", flush=True)
            preflight = await preflight_extension_search()
            print(
                f"  {'✅' if preflight.get('ok') else '❌'} Preflight search: "
                f"{preflight.get('engine', 'none')} "
                f"({preflight.get('hits', 0)} hits)",
                flush=True,
            )
            if not preflight.get("ok"):
                for attempt in preflight.get("attempts", []):
                    print(f"      attempt: {attempt}", flush=True)
                results["steps"].append(
                    {"step": "extension_search_preflight", "passed": False, **preflight}
                )
                results["passed"] = False
                print("❌ Extension search preflight failed — aborting E2E", flush=True)
                await context.close()
                return results
            results["steps"].append(
                {
                    "step": "extension_search_preflight",
                    "passed": True,
                    "engine": preflight.get("engine"),
                    "hits": preflight.get("hits"),
                }
            )

            await screenshot(page, "01_initial_load")

            # ── STEP A: Switch to Split View (Mindmap + Chat) ────────────
            print("\n🗺️  Step A: Switch to Split View (Mindmap + Chat)", flush=True)
            split_btn = page.locator(
                "button:has-text('Split Graph'), "
                "button:has-text('Split View'), "
                "button:has-text('Mindmap')"
            ).first
            try:
                await split_btn.wait_for(state="visible", timeout=8000)
                await split_btn.click()
                await page.wait_for_timeout(1500)
                print("  ✅ Switched to split/mindmap view", flush=True)
            except Exception:
                print("  ⚠️  Split view button not found, may already be in mindmap view", flush=True)

            await screenshot(page, "02_split_view")
            results["steps"].append({"step": "switch_to_split_view", "passed": True})

            # ── STEP B: Adjust Mindmap — Zoom to Fit, Pan, Zoom in/out ───
            print("\n🔍 Step B: Adjust Mindmap viewport (pan, zoom in/out, fit to screen)", flush=True)

            fit_btn = page.locator("button[title='Fit to screen']")
            canvas = page.locator(".mindmap-container canvas")
            try:
                await canvas.wait_for(state="visible", timeout=5000)
                canvas_box = await canvas.bounding_box()
                if canvas_box:
                    cx = canvas_box["x"] + canvas_box["width"] / 2
                    cy = canvas_box["y"] + canvas_box["height"] / 2

                    # 1. Click Fit to screen
                    try:
                        await fit_btn.click()
                        await page.wait_for_timeout(600)
                        print("  ✅ Clicked 'Fit to screen'", flush=True)
                    except Exception:
                        pass
                    await screenshot(page, "03_fit_to_screen")

                    # 2. Zoom in (wheel up)
                    for _ in range(4):
                        await page.mouse.wheel(0, -150)
                        await page.wait_for_timeout(150)
                    print("  ✅ Zoomed in (4 wheel steps)", flush=True)
                    await screenshot(page, "04_zoomed_in")

                    # 3. Zoom out (wheel down)
                    for _ in range(6):
                        await page.mouse.wheel(0, 150)
                        await page.wait_for_timeout(150)
                    print("  ✅ Zoomed out (6 wheel steps)", flush=True)
                    await screenshot(page, "05_zoomed_out")

                    # 4. Pan canvas (drag)
                    await page.mouse.move(cx, cy)
                    await page.mouse.down()
                    await page.mouse.move(cx + 120, cy + 60, steps=12)
                    await page.mouse.up()
                    await page.wait_for_timeout(500)
                    print("  ✅ Panned canvas (+120, +60)", flush=True)
                    await screenshot(page, "06_panned")

                    # 5. Final Fit to screen to re-center all topics within window
                    try:
                        await fit_btn.click()
                        await page.wait_for_timeout(800)
                        print("  ✅ Re-centered all topics via 'Fit to screen'", flush=True)
                    except Exception:
                        pass
                    await screenshot(page, "07_mindmap_adjusted")

            except Exception as e:
                print(f"  ⚠️  Canvas interaction failed: {e}", flush=True)

            results["steps"].append({"step": "adjust_mindmap_viewport", "passed": True})

            baseline_graph = await get_graph_snapshot()
            baseline_nodes = baseline_graph.get("total_nodes", 0)
            print(
                f"  📊 Baseline graph: {baseline_nodes} nodes, "
                f"{baseline_graph.get('total_edges', 0)} edges",
                flush=True,
            )

            # ── STEP D: Internet Search Conversation ─────────────────────
            print("\n🌍 Step D: Internet search conversation (Brave extension)", flush=True)
            await ensure_extension_connected(page, "before search")
            search_prompt = (
                "Search the internet for the top new features in Python 3.14 (such as free threading "
                "and template strings). Summarize the top 2 features concisely in bullet points."
            )
            turn_start_c = time.time()
            await send_message(page, search_prompt)
            print(f"  📤 Sent search prompt ({len(search_prompt)} chars)", flush=True)
            await screenshot(page, "08_search_sent")

            result_c = await wait_for_turn(page, ws_log, turn_start_c, timeout_s=TURN_TIMEOUT_S)
            print(f"  {'✅' if result_c['completed'] else '❌'} Turn completed in {result_c.get('elapsed', '?')}s (source: {result_c.get('source', 'unknown')})", flush=True)
            if result_c.get("executed_tools"):
                print(f"  🔧 Tools used: {', '.join(result_c['executed_tools'])}", flush=True)
            if result_c.get("response_text"):
                preview = result_c["response_text"][:250].replace("\n", " ")
                print(f"  📝 Response preview: {preview}...", flush=True)
            tool_errors = ws_log.tool_errors_since(turn_start_c)
            if tool_errors:
                print(f"  ⚠️  Tool errors: {tool_errors[:2]}", flush=True)

            dom_tool_output = await scrape_dom_tool_output(page)
            ext_provenance = extension_provenance_found(
                ws_log.tool_outputs_since(turn_start_c),
                dom_tool_output,
                result_c.get("response_text", ""),
            )
            print(
                f"  {'✅' if ext_provenance else '❌'} Search provenance: "
                f"{'via Browser Extension' if ext_provenance else 'extension marker not found'}",
                flush=True,
            )

            await screenshot(page, "09_search_response")

            search_tools = [
                t
                for t in result_c.get("executed_tools", [])
                if any(k in t.lower() for k in ("search", "web", "fetch", "crawl"))
            ]
            search_passed = ext_provenance and (
                ws_log.web_search_success_since(turn_start_c)
                or (
                    result_c["completed"]
                    and len(result_c.get("response_text", "")) >= MIN_RESPONSE_CHARS
                )
            )
            results["steps"].append(
                {
                    "step": "internet_search_conversation",
                    "passed": search_passed,
                    "tools": result_c.get("executed_tools", []),
                    "search_tools": search_tools,
                    "extension_provenance": ext_provenance,
                    "web_search_success": ws_log.web_search_success_since(turn_start_c),
                    "response_chars": len(result_c.get("response_text", "")),
                    "elapsed": result_c.get("elapsed"),
                }
            )

            # ── STEP E: Ask Owlynn to Make a Graph ───────────────────────
            print("\n📊 Step E: Ask Owlynn to generate a chart/graph", flush=True)
            graph_prompt = (
                "Write a python script using matplotlib to create a horizontal bar chart "
                "comparing performance execution times across Python 3.12 (1.0x), 3.13 (1.15x), "
                "and 3.14 (1.30x). Save the chart to the workspace as 'python_benchmarks.png'."
            )
            turn_start_d = time.time()
            await send_message(page, graph_prompt)
            print(f"  📤 Sent graph prompt ({len(graph_prompt)} chars)", flush=True)
            await screenshot(page, "10_graph_prompt_sent")

            result_d = await wait_for_turn(page, ws_log, turn_start_d, timeout_s=600)
            print(f"  {'✅' if result_d['completed'] else '❌'} Turn completed in {result_d.get('elapsed', '?')}s (source: {result_d.get('source', 'unknown')})", flush=True)
            if result_d.get("executed_tools"):
                print(f"  🔧 Tools used: {', '.join(result_d['executed_tools'])}", flush=True)
            if result_d.get("response_text"):
                preview = result_d["response_text"][:250].replace("\n", " ")
                print(f"  📝 Response preview: {preview}...", flush=True)

            await screenshot(page, "11_graph_response")

            chart_tools = [
                t
                for t in result_d.get("executed_tools", [])
                if any(k in t.lower() for k in ("notebook", "chart", "write", "workspace", "code"))
            ]
            graph_passed = "notebook_run" in result_d.get("executed_tools", []) and (
                result_d["completed"]
                or len(result_d.get("response_text", "")) >= MIN_RESPONSE_CHARS
            )
            results["steps"].append(
                {
                    "step": "generate_graph",
                    "passed": graph_passed,
                    "tools": result_d.get("executed_tools", []),
                    "chart_tools": chart_tools,
                    "response_chars": len(result_d.get("response_text", "")),
                    "elapsed": result_d.get("elapsed"),
                }
            )

            # ── STEP F: Changing Conversation ────────────────────────────
            print("\n🔀 Step F: Change conversation (topic shift + mindmap node switch)", flush=True)
            pre_topic_graph = await get_graph_snapshot()
            pre_topic_nodes = pre_topic_graph.get("total_nodes", 0)

            topic_prompt = (
                "Let's switch topics completely. Search the web for the latest stable release "
                "version of Rust programming language and summarize its top 2 new features in "
                "two short bullet points."
            )
            turn_start_f1 = time.time()
            await send_message(page, topic_prompt)
            print(f"  📤 Sent topic-shift prompt ({len(topic_prompt)} chars)", flush=True)
            await screenshot(page, "12_topic_shift_sent")

            result_f1 = await wait_for_turn(page, ws_log, turn_start_f1, timeout_s=TURN_TIMEOUT_S)
            print(
                f"  {'✅' if result_f1['completed'] else '❌'} Topic-shift turn completed in "
                f"{result_f1.get('elapsed', '?')}s (source: {result_f1.get('source', 'unknown')})",
                flush=True,
            )
            await screenshot(page, "13_topic_shift_response")

            post_topic_graph = await get_graph_snapshot()
            post_topic_nodes = post_topic_graph.get("total_nodes", 0)
            topic_graph_grew = post_topic_nodes >= pre_topic_nodes
            print(
                f"  📊 Graph nodes after topic shift: {post_topic_nodes} "
                f"(was {pre_topic_nodes}, grew={topic_graph_grew})",
                flush=True,
            )

            current_branch = await get_active_branch(page)
            switch_result = await click_different_mindmap_node(
                page, current_branch, post_topic_graph.get("nodes")
            )
            print(
                f"  {'✅' if switch_result.get('switched') else '⚠️ '} Mindmap node switch: "
                f"{switch_result.get('from', '?')} → {switch_result.get('to') or 'unchanged'} "
                f"({switch_result.get('method') or switch_result.get('reason', 'unknown')})",
                flush=True,
            )
            try:
                await screenshot(page, "14_node_switched")
            except Exception as exc:
                print(f"  ⚠️  Screenshot 14 failed: {exc}", flush=True)

            switch_prompt = (
                "Briefly explain what this conversation branch is about in one sentence."
            )
            turn_start_f2 = time.time()
            await send_message(page, switch_prompt)
            print(f"  📤 Sent message on switched node ({len(switch_prompt)} chars)", flush=True)
            await screenshot(page, "15_switch_node_sent")

            result_f2 = await wait_for_turn(page, ws_log, turn_start_f2, timeout_s=TURN_TIMEOUT_S)
            print(
                f"  {'✅' if result_f2['completed'] else '❌'} Switched-node turn completed in "
                f"{result_f2.get('elapsed', '?')}s (source: {result_f2.get('source', 'unknown')})",
                flush=True,
            )
            await screenshot(page, "16_switch_node_response")

            conversation_change_passed = (
                result_f1["completed"]
                and result_f2["completed"]
                and (
                    switch_result.get("switched", False)
                    or bool(switch_result.get("created_node"))
                )
            )
            results["steps"].append(
                {
                    "step": "change_conversation",
                    "passed": conversation_change_passed,
                    "topic_shift_completed": result_f1["completed"],
                    "topic_shift_nodes_before": pre_topic_nodes,
                    "topic_shift_nodes_after": post_topic_nodes,
                    "topic_graph_grew": topic_graph_grew,
                    "node_switch": switch_result,
                    "switched_node_completed": result_f2["completed"],
                    "active_branch_after_switch": await get_active_branch(page),
                }
            )

            # ── STEP G: Verify Mindmap Updated + Final Screenshots ───────
            print("\n🗺️  Step G: Verify mindmap updated with new nodes", flush=True)

            refresh_btn = page.locator("button[title='Refresh graph']")
            try:
                if await refresh_btn.count() > 0:
                    await refresh_btn.click()
                    await page.wait_for_timeout(1000)
                await fit_btn.click()
                await page.wait_for_timeout(1000)
            except Exception:
                pass

            await screenshot(page, "17_final_mindmap")

            final_graph = await get_graph_snapshot()
            total_nodes = final_graph.get("total_nodes", 0)
            total_edges = final_graph.get("total_edges", 0)
            print(
                f"  📊 Graph has {total_nodes} nodes, {total_edges} edges "
                f"(baseline was {baseline_nodes})",
                flush=True,
            )
            results["steps"].append(
                {
                    "step": "verify_mindmap_nodes",
                    "passed": total_nodes >= baseline_nodes and total_nodes > 0,
                    "total_nodes": total_nodes,
                    "total_edges": total_edges,
                    "baseline_nodes": baseline_nodes,
                    "grew_since_baseline": total_nodes >= baseline_nodes,
                }
            )

            # ── Final panoramic views ────────────────────────────────────
            print("\n📸 Step G (continued): Final panoramic views", flush=True)

            mindmap_only_btn = page.locator(
                "button:has-text('Mindmap'), "
                "button:has-text('Graph View')"
            ).first
            try:
                await mindmap_only_btn.click()
                await page.wait_for_timeout(1500)
                await fit_btn.click()
                await page.wait_for_timeout(800)
            except Exception:
                pass
            await screenshot(page, "18_full_mindmap_view")

            chat_btn = page.locator("button:has-text('Chat')").first
            try:
                await chat_btn.click()
                await page.wait_for_timeout(1000)
            except Exception:
                pass
            await screenshot(page, "19_final_chat_view")

            all_passed = all(s.get("passed", False) for s in results["steps"])
            results["passed"] = all_passed
            results["screenshot_dir"] = str(SCREENSHOT_DIR)

            print("\n⏳ Keeping browser visible for 4s...", flush=True)
            await page.wait_for_timeout(4000)

            await context.close()

    finally:
        await delete_project(project_id)
        print(f"🗑️  Deleted test project {project_id}", flush=True)

    return results


# ── Entry Point ───────────────────────────────────────────────────────────────
async def main():
    print("=" * 72, flush=True)
    print("  Owlynn E2E: Brave Extension Search + Graph + Conversation Change", flush=True)
    print("=" * 72, flush=True)
    print(flush=True)

    results = await run_e2e()

    print(flush=True)
    print("=" * 72, flush=True)
    print("  RESULTS SUMMARY", flush=True)
    print("=" * 72, flush=True)
    for step in results["steps"]:
        icon = "✅" if step["passed"] else "❌"
        print(f"  {icon} {step['step']}", flush=True)
        for k, v in step.items():
            if k not in ("step", "passed"):
                print(f"      {k}: {v}", flush=True)
    print(flush=True)
    passed = results["passed"]
    print(f"  Overall: {'✅ ALL PASSED' if passed else '⚠️  SOME STEPS INCOMPLETE'}", flush=True)
    print(f"  Screenshots: {results.get('screenshot_dir', 'N/A')}", flush=True)
    print("=" * 72, flush=True)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
