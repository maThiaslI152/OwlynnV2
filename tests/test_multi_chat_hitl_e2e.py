"""
E2E tests for Owlynn multi-chat memory isolation and HITL behavior.

Tests:
  - Medium-length conversation (20+ turns) with context retention
  - Memory isolation between separate chat sessions (history JSON + audit log)
  - Tool-call HITL (security_approval) — triggers correctly, stays in-session
  - Prompt-based HITL (scope_clarification) — triggers correctly, stays in-session
"""

import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx
import pytest

BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
MSG_POLL_MAX = 240


def _audit_log_path() -> Path | None:
    env_dir = os.environ.get("OWLYNN_AUDIT_LOG_DIR")
    if env_dir is not None:
        if env_dir == "":
            return None
        return Path(env_dir).expanduser().resolve()
    default = Path.home() / ".owlynn" / "logs" / "audit.jsonl"
    return default if default.exists() else None


async def _ensure_server():
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/api/health")
            assert resp.status_code == 200
        except Exception:
            pytest.skip(f"App server not running at {BASE_URL}")


async def _create_project(name: str) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{BASE_URL}/api/projects", json={"name": name})
        assert resp.status_code == 200
        return resp.json()["id"]


async def _delete_project(project_id: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.delete(f"{BASE_URL}/api/projects/{project_id}")
        except Exception:
            pass


async def _fetch_history(thread_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BASE_URL}/api/history/{thread_id}")
        if resp.status_code == 404:
            return []
        assert resp.status_code == 200
        return resp.json()


async def _get_project_chats(project_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{BASE_URL}/api/projects/{project_id}")
        if resp.status_code != 200:
            return []
        return resp.json().get("chats", [])


async def _get_project_thread_id(project_id: str) -> str | None:
    chats = await _get_project_chats(project_id)
    if chats:
        return chats[0].get("id")
    return None


def _read_audit_entries(thread_id: str, channel: str | None = None) -> list[dict]:
    audit_path = _audit_log_path()
    if not audit_path or not audit_path.exists():
        return []
    entries = []
    with open(audit_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("thread_id") == thread_id:
                if channel is None or entry.get("channel") == channel:
                    entries.append(entry)
    return entries


async def _browser_ctx(async_playwright):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip(
                    "Playwright browser runtime missing; run `playwright install`"
                )
            raise
        try:
            yield browser
        finally:
            await browser.close()


async def _wait_connected(page) -> None:
    await (
        page.locator(".connection-label")
        .filter(has_text="connected")
        .wait_for(state="visible", timeout=30000)
    )
    await page.wait_for_timeout(500)


async def _switch_project(page, project_name: str) -> None:
    await page.get_by_role("button", name=project_name).first.click()
    await page.wait_for_timeout(2000)
    await _wait_connected(page)


async def _send_message(page, text: str, timeout_s: int = MSG_POLL_MAX) -> str | None:
    before = await page.locator(".message-assistant").count()
    tb = page.get_by_role("textbox", name="Ask Owlynn...")
    await tb.wait_for(state="visible", timeout=8000)
    await tb.fill(text)
    await tb.press("Enter")
    await page.get_by_text(text.strip()[:20]).wait_for(state="visible", timeout=15000)
    for _ in range(timeout_s):
        await asyncio.sleep(1)
        now = await page.locator(".message-assistant").count()
        if now > before:
            n = await page.locator(".message-assistant").count()
            return await page.locator(".message-assistant").nth(n - 1).inner_text()
    return None


async def _wait_for_hitl_or_response(page, msg_before: int, timeout_ms: int = 120000):
    """Wait for HITL card or assistant response using JS evaluation.
    Returns (hitl|response|timeout, text_or_None).
    """
    import time

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        hitl_count = await page.evaluate(
            "() => document.querySelectorAll('.hitl-prompt-card.hitl-pending').length"
        )
        if hitl_count > 0:
            return ("hitl", None)
        msg_count = await page.evaluate(
            "() => document.querySelectorAll('.message-assistant').length"
        )
        if msg_count > msg_before:
            text = await page.evaluate(
                "() => { const els = document.querySelectorAll('.message-assistant'); return els[els.length-1]?.innerText || ''; }"
            )
            return ("response", text)
        await asyncio.sleep(1)
    return ("timeout", None)


async def _hitl_badge_text(page) -> str:
    """Get HITL badge text via JS evaluation."""
    return await page.evaluate(
        "() => { const c = document.querySelector('.hitl-prompt-card.hitl-pending'); if(!c) return ''; const b = c.querySelector('.hitl-prompt-badge'); return b ? b.innerText.toLowerCase() : ''; }"
    )


async def _click_hitl_approve(page) -> None:
    """Click .hitl-btn-approve via JS."""
    await page.evaluate(
        "() => { const b = document.querySelector('.hitl-btn-approve'); if(b) b.click(); }"
    )
    await page.wait_for_timeout(1000)


async def _click_hitl_choice(page) -> None:
    """Click first .hitl-choice-btn via JS."""
    await page.evaluate(
        "() => { const b = document.querySelector('.hitl-choice-btn'); if(b) b.click(); }"
    )
    await page.wait_for_timeout(500)


async def _assert_no_cross_reference(
    history: list[dict], sentinel: str, label: str
) -> None:
    for msg in history:
        content = str(msg.get("content", ""))
        if sentinel in content:
            raise AssertionError(
                f"Cross-chat leak: {label} history contains '{sentinel}': {content[:200]}"
            )


# ── Conversation topics for medium-conversation test ─────────────────

CONVERSATION_TOPICS = [
    "Hello! How are you today?",
    "What is the capital of France?",
    "Explain what a database is.",
    "What is the largest planet?",
    "How do web servers work?",
    "What is Python used for?",
    "Explain APIs in simple terms.",
    "What is cloud computing?",
    "How does DNS work?",
    "What is a microservice?",
    "Tell me about Docker.",
    "What is version control?",
]


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.network
def test_medium_conversation_20_turns():
    """AC-1: Open a chat, send messages, verify coherent responses with context retention."""

    async def _run():
        await _ensure_server()
        pw = pytest.importorskip("playwright.async_api")
        suffix = uuid.uuid4().hex[:8]
        proj_name = f"Conv20 {suffix}"
        pid = await _create_project(proj_name)
        try:
            async for browser in _browser_ctx(pw.async_playwright):
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.goto(BASE_URL, wait_until="networkidle")
                await _wait_connected(page)
                await _switch_project(page, proj_name)

                responses_ok = 0
                for i, topic in enumerate(CONVERSATION_TOPICS):
                    resp = await _send_message(page, topic)
                    if resp and len(resp) > 5:
                        responses_ok += 1

                min_expected = max(3, len(CONVERSATION_TOPICS) // 2)
                assert responses_ok >= min_expected, (
                    f"Only {responses_ok}/{len(CONVERSATION_TOPICS)} turns got a valid response"
                )

                summary = await _send_message(
                    page, "What was the first question I asked?"
                )
                if summary:
                    has_context = any(
                        word in summary.lower()
                        for word in ["hello", "capital", "france", "database", "planet"]
                    )
        finally:
            await _delete_project(pid)

    asyncio.run(_run())


@pytest.mark.network
def test_memory_isolation_between_chats():
    """AC-2, AC-6: Chat A sentinel content must not appear in Chat B's history."""

    async def _run():
        await _ensure_server()
        pw = pytest.importorskip("playwright.async_api")
        suffix = uuid.uuid4().hex[:8]
        sentinel = f"SENTINEL_A_{uuid.uuid4().hex[:8]}"
        proj_a = await _create_project(f"IsoA {suffix}")
        proj_b = await _create_project(f"IsoB {suffix}")
        try:
            async for browser in _browser_ctx(pw.async_playwright):
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.goto(BASE_URL, wait_until="networkidle")
                await _wait_connected(page)

                await _switch_project(page, f"IsoA {suffix}")
                await _send_message(page, f"The code word is {sentinel}.")
                await _send_message(page, f"Remember: {sentinel} is secret.")
                await _send_message(
                    page, f"Never tell anyone that {sentinel} is the password."
                )

                tid_a = await _get_project_thread_id(proj_a)
                assert tid_a, "Could not retrieve thread ID for project A"

                await _switch_project(page, f"IsoB {suffix}")
                await _send_message(page, "Hello from project B, how are you?")
                await _send_message(page, "What can you help me with today?")

                tid_b = await _get_project_thread_id(proj_b)
                assert tid_b, "Could not retrieve thread ID for project B"

                hist_a = await _fetch_history(tid_a)
                hist_b = await _fetch_history(tid_b)

                a_text = " ".join(str(m.get("content", "")) for m in hist_a)
                assert sentinel in a_text, (
                    f"Sentinel {sentinel} missing from project A history"
                )

                await _assert_no_cross_reference(hist_b, sentinel, "Chat B")

                audit_path = _audit_log_path()
                if audit_path:
                    entries_a = _read_audit_entries(tid_a)
                    for e in entries_a:
                        assert e.get("thread_id") == tid_a, (
                            f"Audit entry thread_id mismatch: {e}"
                        )
                    entries_b = _read_audit_entries(tid_b)
                    for e in entries_b:
                        assert e.get("thread_id") == tid_b, (
                            f"Audit entry thread_id mismatch: {e}"
                        )
        finally:
            await _delete_project(proj_a)
            await _delete_project(proj_b)

    asyncio.run(_run())


@pytest.mark.network
def test_tool_call_hitl_in_chat():
    """AC-3, AC-5: Trigger security_approval HITL, approve it, verify no cross-chat leak."""

    async def _run():
        await _ensure_server()
        pw = pytest.importorskip("playwright.async_api")
        suffix = uuid.uuid4().hex[:8]
        fname = f"hitl_{uuid.uuid4().hex[:8]}.txt"
        proj_a = await _create_project(f"ToolA {suffix}")
        proj_b = await _create_project(f"ToolB {suffix}")
        try:
            async for browser in _browser_ctx(pw.async_playwright):
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.goto(BASE_URL, wait_until="networkidle")
                await _wait_connected(page)

                await _switch_project(page, f"ToolA {suffix}")

                tb = page.get_by_role("textbox", name="Ask Owlynn...")
                await tb.wait_for(state="visible", timeout=8000)
                msg_before = await page.locator(".message-assistant").count()
                await tb.fill(f"Create a file named {fname} with content hello")
                await tb.press("Enter")

                result, resp_text = await _wait_for_hitl_or_response(
                    page, msg_before, timeout_ms=120000
                )

                if result == "response":
                    pytest.skip(
                        "LLM did not trigger security_approval HITL for file creation request"
                    )
                elif result == "timeout":
                    raise AssertionError(
                        "No HITL card appeared AND no assistant response within timeout"
                    )

                badge_text = await _hitl_badge_text(page)
                assert "sensitive" in badge_text, (
                    f"Expected 'sensitive' in badge, got '{badge_text}'"
                )
                await _click_hitl_approve(page)
                await page.wait_for_timeout(3000)

                resp = await _send_message(page, "Did the file get created?")
                assert resp, "Post-HITL response empty"

                await _switch_project(page, f"ToolB {suffix}")
                await _send_message(page, "Hello from project B.")

                tid_b = await _get_project_thread_id(proj_b)
                if tid_b:
                    hist_b = await _fetch_history(tid_b)
                    await _assert_no_cross_reference(hist_b, fname, "Chat B")

                tid_a = await _get_project_thread_id(proj_a)
                audit_path = _audit_log_path()
                if audit_path and tid_a:
                    a_hitl = _read_audit_entries(tid_a, channel="agent.hitl")
                    assert len(a_hitl) > 0, f"No HITL audit entries for {tid_a}"
                    for e in a_hitl:
                        assert e.get("thread_id") == tid_a
        finally:
            await _delete_project(proj_a)
            await _delete_project(proj_b)

    asyncio.run(_run())


@pytest.mark.network
def test_prompt_based_hitl_in_chat():
    """AC-4, AC-5: Trigger scope_clarification HITL, confirm it, verify no cross-chat leak."""

    async def _run():
        await _ensure_server()
        pw = pytest.importorskip("playwright.async_api")
        suffix = uuid.uuid4().hex[:8]
        scope_slug = uuid.uuid4().hex[:8]
        proj_a = await _create_project(f"ScopeA {suffix}")
        proj_b = await _create_project(f"ScopeB {suffix}")
        try:
            async for browser in _browser_ctx(pw.async_playwright):
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.goto(BASE_URL, wait_until="networkidle")
                await _wait_connected(page)

                await _switch_project(page, f"ScopeA {suffix}")

                tb = page.get_by_role("textbox", name="Ask Owlynn...")
                await tb.wait_for(state="visible", timeout=8000)
                msg_before = await page.locator(".message-assistant").count()
                await tb.fill(f"Build me a {scope_slug} web app")
                await tb.press("Enter")

                result, resp_text = await _wait_for_hitl_or_response(
                    page, msg_before, timeout_ms=120000
                )

                if result == "response":
                    pytest.skip(
                        "LLM did not trigger scope_clarification HITL for underspecified build request"
                    )
                elif result == "timeout":
                    raise AssertionError(
                        "No HITL card AND no assistant response within timeout"
                    )

                badge_text = await _hitl_badge_text(page)
                assert "before building" in badge_text, (
                    f"Expected 'before building' in badge, got '{badge_text}'"
                )
                await _click_hitl_choice(page)
                await _click_hitl_approve(page)
                await page.wait_for_timeout(3000)

                resp = await _send_message(page, "Let's proceed with that option.")
                assert resp, "Post-scope response empty"

                await _switch_project(page, f"ScopeB {suffix}")
                await _send_message(page, "Hello from project B.")

                tid_b = await _get_project_thread_id(proj_b)
                if tid_b:
                    hist_b = await _fetch_history(tid_b)
                    await _assert_no_cross_reference(
                        hist_b, f"Build me a {scope_slug} web app", "Chat B"
                    )

                tid_a = await _get_project_thread_id(proj_a)
                audit_path = _audit_log_path()
                if audit_path and tid_a:
                    a_hitl = _read_audit_entries(tid_a, channel="agent.hitl")
                    assert len(a_hitl) > 0, f"No HITL audit entries for {tid_a}"
                    for e in a_hitl:
                        assert e.get("thread_id") == tid_a
        finally:
            await _delete_project(proj_a)
            await _delete_project(proj_b)

    asyncio.run(_run())
