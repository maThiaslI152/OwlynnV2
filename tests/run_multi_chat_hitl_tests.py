#!/usr/bin/env python3
"""
Standalone runner for multi-chat HITL & memory isolation E2E tests.

Usage:
    PYTHONPATH=$(pwd) .venv/bin/python tests/run_multi_chat_hitl_tests.py

All tests require a running backend at APP_BASE_URL (default http://127.0.0.1:8000).
"""

import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
AUDIT_LOG_PATH = (
    Path(os.getenv("OWLYNN_AUDIT_LOG_DIR", str(Path.home() / ".owlynn" / "logs")))
    / "audit.jsonl"
)

passed = 0
failed = 0


def test(name):
    """Decorator-like wrapper for async test functions."""

    def decorator(func):
        global passed, failed
        print(f"\n{'=' * 60}", flush=True)
        print(f"  TEST: {name}", flush=True)
        print(f"{'=' * 60}", flush=True)
        try:
            asyncio.run(func())
            print(f"  ✅ PASS: {name}", flush=True)
            passed += 1
        except Exception as e:
            print(f"  ❌ FAIL: {name}", flush=True)
            print(f"     {e}", flush=True)
            import traceback

            traceback.print_exc()
            failed += 1

    return decorator


# ── Helpers ──────────────────────────────────────────────────────────


async def _is_server_ready():
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{APP_BASE_URL}/api/health")
            return r.status_code == 200
    except Exception:
        return False


async def _create_project(name: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{APP_BASE_URL}/api/projects", json={"name": name})
        assert r.status_code == 200, f"Create failed: {r.status_code}"
        return r.json()


async def _delete_project(project_id: str) -> None:
    async with httpx.AsyncClient(timeout=10) as c:
        await c.delete(f"{APP_BASE_URL}/api/projects/{project_id}")


async def _fetch_history(thread_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{APP_BASE_URL}/api/history/{thread_id}")
        assert r.status_code == 200
        return r.json()


async def _launch_browser():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            await browser.close()


async def _assert_connected(page):
    await (
        page.locator(".connection-label")
        .filter(has_text="connected")
        .wait_for(state="visible", timeout=30000)
    )


async def _switch_project(page, name: str):
    await page.locator(".workspace-project-item").filter(has_text=name).first.click()
    await page.get_by_text(f"Active: {name}").wait_for(state="visible", timeout=10000)
    await _assert_connected(page)


async def _send_msg(page, text, timeout_ms=300000) -> str:
    """Send message, wait for any response, return assistant text (or empty).

    Waits for: new .message-assistant, any .tool-activity-card, or .hitl-prompt-card.
    """

    check_interval = 2
    deadline = time.time() + timeout_ms / 1000
    tb = page.get_by_role("textbox")
    await tb.wait_for(state="visible", timeout=30000)
    await tb.fill(text)

    # Count before
    msg_before = await page.locator(".message-assistant").count()
    tool_before = await page.locator(
        "[class*='tool-activity'],[class*='tool-card']"
    ).count()
    hitl_before = await page.locator(".hitl-prompt-card").count()

    await page.locator(".composer-send").click()
    await page.get_by_text(text).first.wait_for(state="visible", timeout=15000)

    # Poll until something changes
    while time.time() < deadline:
        msg_now = await page.locator(".message-assistant").count()
        tool_now = await page.locator(
            "[class*='tool-activity'],[class*='tool-card']"
        ).count()
        hitl_now = await page.locator(".hitl-prompt-card").count()
        if msg_now > msg_before or tool_now > tool_before or hitl_now > hitl_before:
            break
        await asyncio.sleep(check_interval)

    # Return last assistant message if any
    n = await page.locator(".message-assistant").count()
    if n > 0:
        return await page.locator(".message-assistant").nth(n - 1).inner_text()
    return ""


async def _assert_no_cross_ref(history: list[dict], sentinel: str, label: str):
    for msg in history:
        content = str(msg.get("content", ""))
        if sentinel in content:
            raise AssertionError(
                f"Cross-chat leak: {label} contains '{sentinel}': {content[:200]}"
            )


async def _audit_entries(thread_id: str, channel: str | None = None) -> list[dict]:
    if not AUDIT_LOG_PATH.exists():
        return []
    entries = []
    with open(AUDIT_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("thread_id") != thread_id:
                continue
            if channel and entry.get("channel") != channel:
                continue
            entries.append(entry)
    return entries


async def _trigger_sensitive_tool(page) -> bool:
    r = await _send_msg(
        page, "Create a file named test_hitl.txt with content 'HITL test'"
    )
    card = page.locator(".hitl-prompt-card.hitl-pending").first
    try:
        await card.wait_for(state="visible", timeout=45000)
        return True
    except Exception:
        return False


async def _trigger_scope_hitl(page) -> bool:
    r = await _send_msg(page, "Build me a web app")
    card = page.locator(".hitl-prompt-card.hitl-pending").first
    try:
        await card.wait_for(state="visible", timeout=45000)
        return True
    except Exception:
        return False


async def _confirm_hitl(page):
    btn = page.locator(".hitl-btn-approve").first
    await btn.wait_for(state="visible", timeout=5000)
    await btn.click()
    await asyncio.sleep(2)


async def _select_first_choice(page):
    btn = page.locator(".hitl-choice-btn").first
    await btn.wait_for(state="visible", timeout=5000)
    await btn.click()
    await _confirm_hitl(page)


# ── Test Data ────────────────────────────────────────────────────────

TOPICS = [
    "Hello! My project is called 'Echo Metrics'. It's a server monitoring dashboard. Can you help me design the data pipeline?",
    "I'm thinking of using Redis as a message queue. What Python library for consumers?",
    "How should I structure workers for CPU, memory, disk metrics?",
    "What data schema for a CPU metric event?",
    "Storage layer: PostgreSQL or TimescaleDB?",
    "Let's go with TimescaleDB. What hypertable config for 10k metrics/sec?",
    "Good, chunk_time_interval of 1 hour. How to set up continuous aggregates for hourly CPU averages?",
    "That view looks solid. Ingestion: Kafka or batch inserts from workers?",
    "Batch inserts it is. How to handle backpressure if DB lags?",
    "Bounded queue with circuit breaker. How to decide queue size limits?",
    "Base on peak memory. For 4GB worker, safe queue depth for 1KB payloads?",
    "About 500k events per worker. API layer: hypertables or materialized views?",
    "Materialized views refreshed every minute. How to avoid blocking reads?",
    "pg_cron with concurrent refresh. Alerting: anomaly detection for CPU metrics?",
    "Rolling z-score over 30 min. Threshold for paging vs warning?",
    "3-sigma pages, 2-sigma warnings. Separate alert service or inside dashboard?",
    "Separate evaluator makes sense. How to communicate with dashboard?",
    "Shared PG table with alert status. Index strategy for recent alerts?",
    "Composite index on (status, severity, created_at). Data retention for raw metrics?",
    "30-day raw retention, weekly compaction. Cron or external script?",
    "External Python script triggered by cron. What's next on the checklist?",
    "We covered pipeline, storage, alerting, retention. Can you summarize the full architecture?",
]


# ── Test: Medium Conversation (AC-1) ─────────────────────────────────


async def run_test_1():
    if not await _is_server_ready():
        raise RuntimeError(f"Server not ready at {APP_BASE_URL}")

    suffix = uuid.uuid4().hex[:8]
    proj_name = f"EchoMetrics {suffix}"
    proj = await _create_project(proj_name)
    pid = proj["id"]

    try:
        async for browser in _launch_browser():
            page = await browser.new_page()
            await page.goto(APP_BASE_URL, wait_until="load")
            await _assert_connected(page)
            await _switch_project(page, proj_name)

            for i, topic in enumerate(TOPICS):
                resp = await _send_msg(page, topic)
                assert resp, f"Turn {i + 1}: empty response"
                assert len(resp) > 5, f"Turn {i + 1}: too short: {resp[:100]}"

            last = await _send_msg(
                page, "What is the name of our project and its main purpose?"
            )
            assert last, "Summary empty"
            assert re.search(
                r"echo[- ]?metrics|Echo[- ]?Metrics|the project|monitoring|dashboard|pipeline",
                last,
                re.IGNORECASE,
            ), f"Context coherence fail: {last[:300]}"

            tid = (await page.locator("code").first.inner_text()).strip()
            history = await _fetch_history(tid)
            assert len(history) >= 5, f"History has {len(history)} msgs"

            await browser.close()
    finally:
        await _delete_project(pid)


# ── Test: Memory Isolation (AC-2, AC-6) ─────────────────────────────


async def run_test_2():
    if not await _is_server_ready():
        raise RuntimeError("Server not ready")

    suffix = uuid.uuid4().hex[:8]
    proj_a = await _create_project(f"MemA {suffix}")
    proj_b = await _create_project(f"MemB {suffix}")
    sentinel = f"SENTINEL_A_{suffix}"

    try:
        async for browser in _launch_browser():
            page = await browser.new_page()
            await page.goto(APP_BASE_URL, wait_until="load")
            await _assert_connected(page)

            await _switch_project(page, proj_a["name"])
            for i in range(5):
                await _send_msg(
                    page, f"Turn {i + 1}: Remember {sentinel}. What's {i + 2} squared?"
                )

            tid_a = (await page.locator("code").first.inner_text()).strip()
            hist_a = await _fetch_history(tid_a)
            assert len(hist_a) >= 5

            await _switch_project(page, proj_b["name"])
            await _send_msg(page, "Hello from B")
            tid_b = (await page.locator("code").first.inner_text()).strip()
            hist_b = await _fetch_history(tid_b)
            await _assert_no_cross_ref(hist_b, sentinel, "Chat B")

            entries_b = await _audit_entries(tid_b, "agent.hitl")
            for e in entries_b:
                assert e.get("thread_id") == tid_b, f"Bad thread: {e}"

            await browser.close()
    finally:
        await _delete_project(proj_a["id"])
        await _delete_project(proj_b["id"])


# ── Test: Tool-call HITL (AC-3, AC-5) ───────────────────────────────


async def run_test_3():
    if not await _is_server_ready():
        raise RuntimeError("Server not ready")

    suffix = uuid.uuid4().hex[:8]
    proj_a = await _create_project(f"ToolA {suffix}")
    proj_b = await _create_project(f"ToolB {suffix}")

    try:
        async for browser in _launch_browser():
            page = await browser.new_page()
            await page.goto(APP_BASE_URL, wait_until="load")
            await _assert_connected(page)

            await _switch_project(page, proj_a["name"])
            tid_a = (await page.locator("code").first.inner_text()).strip()

            appeared = await _trigger_sensitive_tool(page)
            assert appeared, "security_approval HITL card did not appear"
            await _confirm_hitl(page)

            follow = await _send_msg(page, "Did the file get created?")
            assert follow, "Chat A post-HITL response empty"

            await _switch_project(page, proj_b["name"])
            tid_b = (await page.locator("code").first.inner_text()).strip()
            hist_b = await _fetch_history(tid_b)
            await _assert_no_cross_ref(hist_b, "HITL test", "Chat B")

            entries_a = await _audit_entries(tid_a, "agent.hitl")
            assert len(entries_a) > 0, f"No audit entries for {tid_a}"
            for e in entries_a:
                assert e.get("thread_id") == tid_a

            entries_b = await _audit_entries(tid_b, "agent.hitl")
            for e in entries_b:
                assert e.get("thread_id") == tid_b

            await browser.close()
    finally:
        await _delete_project(proj_a["id"])
        await _delete_project(proj_b["id"])


# ── Test: Prompt-based HITL (AC-4, AC-5) ────────────────────────────


async def run_test_4():
    if not await _is_server_ready():
        raise RuntimeError("Server not ready")

    suffix = uuid.uuid4().hex[:8]
    proj_a = await _create_project(f"ScopeA {suffix}")
    proj_b = await _create_project(f"ScopeB {suffix}")

    try:
        async for browser in _launch_browser():
            page = await browser.new_page()
            await page.goto(APP_BASE_URL, wait_until="load")
            await _assert_connected(page)

            await _switch_project(page, proj_a["name"])
            tid_a = (await page.locator("code").first.inner_text()).strip()

            appeared = await _trigger_scope_hitl(page)
            assert appeared, "scope_clarification HITL card did not appear"

            submit_btn = page.locator(".hitl-btn-approve").first
            submit_text = await submit_btn.inner_text()
            assert "submit" in submit_text.lower() or "choice" in submit_text.lower(), (
                f"Expected scope button: {submit_text}"
            )

            await _select_first_choice(page)
            follow = await _send_msg(page, "Let's proceed with that option.")
            assert follow, "Chat A post-scope response empty"

            await _switch_project(page, proj_b["name"])
            tid_b = (await page.locator("code").first.inner_text()).strip()
            hist_b = await _fetch_history(tid_b)
            await _assert_no_cross_ref(hist_b, "Build me a web app", "Chat B")

            entries_a = await _audit_entries(tid_a, "agent.hitl")
            assert len(entries_a) > 0
            for e in entries_a:
                assert e.get("thread_id") == tid_a

            entries_b = await _audit_entries(tid_b, "agent.hitl")
            for e in entries_b:
                assert e.get("thread_id") == tid_b

            await browser.close()
    finally:
        await _delete_project(proj_a["id"])
        await _delete_project(proj_b["id"])


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting multi-chat HITL & memory isolation E2E tests...", flush=True)
    print(f"Backend URL: {APP_BASE_URL}", flush=True)

    tests = [
        ("Medium Conversation (AC-1)", run_test_1),
        ("Memory Isolation (AC-2, AC-6)", run_test_2),
        ("Tool-call HITL (AC-3, AC-5)", run_test_3),
        ("Prompt-based HITL (AC-4, AC-5)", run_test_4),
    ]

    for name, func in tests:
        print(f"\n{'=' * 60}", flush=True)
        print(f"  TEST: {name}", flush=True)
        print(f"{'=' * 60}", flush=True)
        try:
            asyncio.run(func())
            print("  ✅ PASS", flush=True)
            passed += 1
        except Exception as e:
            print(f"  ❌ FAIL: {e}", flush=True)
            import traceback

            traceback.print_exc()
            failed += 1
            break  # stop on first failure

    print(f"\n{'=' * 60}", flush=True)
    print(f"  RESULTS: {passed} passed, {failed} failed", flush=True)
    print(f"{'=' * 60}", flush=True)
    sys.exit(1 if failed > 0 else 0)
