#!/usr/bin/env python3
"""
Playwright frontier evaluation for Owlynn V2.

Scores routing, tools, memory, vision, file watcher, and format ingestion against
the current cloud-primary LangGraph pipeline.

Usage:
  python scripts/run_local_frontier_eval.py              # auto-detect settings
  python scripts/run_local_frontier_eval.py --profile local
  python scripts/run_local_frontier_eval.py --profile cloud
  python scripts/run_local_frontier_eval.py --cloud-off
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import random
import re
import shutil
import sys
import tempfile
import time
import mimetypes
import uuid
from pathlib import Path

# Add project root to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Any

import httpx
from playwright.async_api import Page, async_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
FIXTURE_DIR = REPO_ROOT / "assets" / "eval_fixtures"
SCREENSHOT_DIR = REPO_ROOT / "assets" / "frontier_eval_screenshots"
OUTPUT_DATA_FILE = REPO_ROOT / "data" / "frontier_eval_run_data.json"
WORKSPACE_DIR = REPO_ROOT / "workspace"

COMPLEX_ROUTES = frozenset({"complex-cloud"})
VISION_ROUTES = frozenset({"vision", "vision_cloud"})
# Cloud-intended complex turns that fail are scored as failed.
CLOUD_FAILURE_BADGES = frozenset(
    {
        "large-cloud-failed",
        "small-local-failed",
    }
)
SIMPLE_TIMEOUT_S = 180
COMPLEX_TIMEOUT_S = 900
# Idle polls (2s each) before accepting turn when expected tools never arrive.
IDLE_TOOL_STALL_POLLS = 8

CODEWORD = "ZEBRA-42"
MARKERS = {
    "csv": "EVAL_CSV_MARKER_42",
    "docx": "EVAL_DOCX_MARKER_99",
    "xlsx": "EVAL_XLSX_CELL_7",
    "pdf": "EVAL_PDF_MARKER_55",
    "ocr": "EVAL_OCR_MARKER",
}

# expected_route: simple | complex-cloud | vision
TEST_PROMPTS: list[dict[str, Any]] = [
    {
        "id": "F1.1",
        "topic": "Router Precision (Simple)",
        "prompt": "Hello there! Hope you are doing well today.",
        "expected_route": "simple",
        "expected_tools": [],
        "timeout_s": SIMPLE_TIMEOUT_S,
        "min_response_chars": 8,
        "pipeline_notes": "keyword_bypass → simple → memory_write",
    },
    {
        "id": "F2.1",
        "topic": "Router Precision (Complex)",
        "prompt": "Can you review the python code in this function and tell me if it has bugs?",
        "expected_route": "complex",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 40,
        "pipeline_notes": "code-review bypass → complex_llm",
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
        "pipeline_notes": "web_search→fetch→HITL write→memory_write",
    },
    {
        "id": "F4.1",
        "topic": "Massive Context Ingestion",
        "new_chat_before": True,
        "prompt": (
            "Read the file `docs/STATUS.md` from the workspace. "
            "What are the 'Architectural Concerns' listed there?"
        ),
        "expected_route": "complex",
        "expected_tools": ["read_workspace_file"],
        "workspace_seed": "docs/STATUS.md",
        "workspace_seed_from_fixture": "status_eval.md",
        "expected_marker": "Screen Assist",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 40,
        "pipeline_notes": "read_workspace_file → synthesis",
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
        "pipeline_notes": "complex_llm codegen (may hit scope_clarify)",
    },
    {
        "id": "F6.1",
        "topic": "Memory Retention (conversation)",
        "new_chat_before": True,
        "prompt": (
            "Without searching the web again, what city's weather did we look up earlier in this "
            "conversation, and what was the exact file name we saved it to?"
        ),
        "expected_route": "complex",
        "expected_tools": [],
        "expected_marker": "tokyo",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 20,
        "pipeline_notes": "STM via message history — no tools",
    },
    {
        "id": "F7.1",
        "topic": "Frontier Quality (flash tier)",
        "prompt": (
            "Give a rigorous formal proof sketch showing how to optimize this sorting algorithm "
            "to best-possible time complexity. Use frontier-quality reasoning."
        ),
        "expected_route": "complex",
        "expected_tier": "flash",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 120,
        "pipeline_notes": "frontier hint → complex-cloud; tier stays flash (profile default)",
    },
    {
        "id": "F7.2",
        "topic": "Frontier Pro tier path",
        "prompt": "Summarize the key steps of your previous proof sketch in three bullet points.",
        "expected_route": "complex",
        "expected_tier": "pro",
        "set_tier_before": "pro",
        "restore_tier_after": "flash",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 40,
        "pipeline_notes": "cloud_model_tier=pro → deepseek-v4-pro",
    },
    {
        "id": "F8.1",
        "topic": "Router LLM Classifier",
        "new_chat_before": True,
        "prompt": (
            "Over a long career, is breadth or depth usually more valuable? "
            "Argue both sides in detail."
        ),
        "expected_route": "complex",
        # Any non-bypass source proves the MiniCPM5 classifier actually ran.
        "expected_source": ["llm_classifier", "question_heuristic_override"],
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 60,
        "pipeline_notes": "open-ended reasoning → MiniCPM5 classifier (no keyword bypass)",
    },
    {
        "id": "F9.1",
        "topic": "Vision Proxy (OCR)",
        "prompt": "What exact text do you see in this image? Reply with the full string only.",
        # Router routes images to complex-(cloud|default) with task_category vision*.
        "expected_route": "complex",
        "expected_vision": True,
        "attach_file": "ocr_sample.png",
        "expected_marker": MARKERS["ocr"],
        "skip_if": "vision_unavailable",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 8,
        "pipeline_notes": "image → complex route + vision task_category → Florence OCR → DeepSeek",
    },
    {
        "id": "M1.1",
        "topic": "Memory Session Seed",
        "new_chat_before": True,
        "prompt": (
            f"My project codeword is {CODEWORD} and we use FastAPI for the backend API layer."
        ),
        "expected_route": "complex",
        "expected_ws_events": ["memory_updated"],
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 20,
        "pipeline_notes": "memory_write → personal JSON + LTM queue",
    },
    {
        "id": "M1.2",
        "topic": "Memory Session Recall",
        "prompt": "What was my project codeword?",
        "expected_route": "complex",
        "expected_marker": CODEWORD,
        "expected_tools": [],
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 5,
        "pipeline_notes": "same thread recall via messages + personal inject",
    },
    {
        "id": "M2.1",
        "topic": "LTM Cross-Thread Recall",
        "prompt": "What project codeword did I mention in an earlier conversation?",
        "expected_route": "complex",
        "expected_marker": CODEWORD,
        "new_chat_before": True,
        "skip_if": "mem0_unavailable",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 5,
        "pipeline_notes": "new thread → memory_retrieve → Mem0/Qdrant",
    },
    {
        "id": "M4.1",
        "topic": "Memory Retrieval Gate (negative)",
        "prompt": "Hi there!",
        "expected_route": "simple",
        "forbid_ws_events": ["memory_updated"],
        "timeout_s": SIMPLE_TIMEOUT_S,
        "min_response_chars": 3,
        "new_chat_before": True,
        "pipeline_notes": "simple route → needs_memory_retrieval=false",
    },
    {
        "id": "W1.1",
        "topic": "File Watcher",
        "prompt": "Read the file eval_watch.txt from my workspace and summarize it in one sentence.",
        "expected_route": "complex",
        "expected_tools": ["read_workspace_file"],
        "workspace_seed": "eval_watch.txt",
        "workspace_seed_content": "EVAL_WATCH_MARKER: autonomous file watcher smoke test.",
        "check_processed": "eval_watch.txt",
        "expected_ws_events": ["file_status"],
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 20,
        "pipeline_notes": "disk write → watcher → .processed → read_workspace_file",
    },
    {
        "id": "FF1.1",
        "topic": "Format PDF",
        "prompt": "What marker string appears in the attached PDF? Reply with just that string.",
        "expected_route": "complex",
        "attach_file": "sample.pdf",
        "expected_marker": MARKERS["pdf"],
        "check_processed": "sample.pdf",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 5,
        "pipeline_notes": "upload → PyMuPDF/Docling → agent read",
    },
    {
        "id": "FF2.1",
        "topic": "Format DOCX",
        "prompt": "What marker string appears in the attached Word document?",
        "expected_route": "complex",
        "attach_file": "sample.docx",
        "expected_marker": MARKERS["docx"],
        "check_processed": "sample.docx",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 5,
        "pipeline_notes": "upload → python-docx → agent read",
    },
    {
        "id": "FF3.1",
        "topic": "Format XLSX",
        "prompt": "What value is in col_a of the attached spreadsheet?",
        "expected_route": "complex",
        "attach_file": "sample.xlsx",
        "expected_marker": MARKERS["xlsx"],
        "check_processed": "sample.xlsx",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 5,
        "pipeline_notes": "upload → pandas markdown → agent read",
    },
    {
        "id": "FF4.1",
        "topic": "Format CSV",
        "prompt": "What is the value column for row alpha in the attached CSV?",
        "expected_route": "complex",
        "attach_file": "sample.csv",
        "expected_marker": MARKERS["csv"],
        "check_processed": "sample.csv",
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 5,
        "pipeline_notes": "upload → pandas → agent read",
    },
]


def _has_dsml_leak(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    if "dsml" in lowered or "｜｜" in text:
        return True
    if "tool_calls" in lowered and "invoke" in lowered:
        return True
    # Unexecuted tool-call markup leaking into the visible bubble.
    for marker in ("<tool_call>", "<function=", "</function>", "<｜tool"):
        if marker in lowered:
            return True
    return False


def _is_premature_dsml(text: str) -> bool:
    body = _normalize_response(text)
    return bool(body) and _has_dsml_leak(body)


def _normalize_response(text: str) -> str:

    lines = [
        ln
        for ln in (text or "").splitlines()
        if ln.strip() and ln.strip().lower() not in {"o", "just now"}
    ]
    joined = "\n".join(lines).strip()
    return re.sub(r"\s+", " ", joined)


def merge_executed_tools(ws_tools: list[str], dom_tools: list[str]) -> list[str]:
    """Prefer WS tool names; fall back to DOM scrape when WS is empty."""
    return ws_tools or dom_tools


def expected_tools_satisfied(
    executed: list[str], expected_tools: list[str] | None
) -> bool:
    if not expected_tools:
        return True
    return all(t in executed for t in expected_tools)


def should_exit_idle_tool_stall(
    *,
    tools_ok: bool,
    expected_tools: list[str] | None,
    normalized_len: int,
    min_chars: int,
    dsml: bool,
    running_tools: list[str],
    stall_polls: int,
    max_stall_polls: int = IDLE_TOOL_STALL_POLLS,
) -> bool:
    """True when graph is idle, response is ready, but required tools won't arrive."""
    if not expected_tools or tools_ok or dsml:
        return False
    if normalized_len < min_chars or running_tools:
        return False
    return stall_polls >= max_stall_polls


def resolve_workspace_seed_content(item: dict) -> str:
    fixture_name = item.get("workspace_seed_from_fixture")
    if fixture_name:
        path = FIXTURE_DIR / fixture_name
        return path.read_text(encoding="utf-8")
    return item.get("workspace_seed_content", "eval seed")


class WsEventLog:
    """Capture selected WebSocket frames from the browser."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def attach(self, page: Page) -> None:
        def on_websocket(ws) -> None:
            def on_frame(payload) -> None:
                try:
                    raw = (
                        payload if isinstance(payload, str) else payload.decode("utf-8")
                    )
                    data = json.loads(raw)
                    if isinstance(data, dict) and data.get("type"):
                        self.events.append(
                            {"type": data["type"], "ts": time.time(), "payload": data}
                        )
                except Exception:
                    pass

            ws.on("framereceived", on_frame)

        page.on("websocket", on_websocket)

    def saw(self, event_type: str, since_ts: float | None = None) -> bool:
        for ev in self.events:
            if ev["type"] != event_type:
                continue
            if since_ts is None or ev["ts"] >= since_ts:
                return True
        return False

    def types_since(self, since_ts: float) -> list[str]:
        return [ev["type"] for ev in self.events if ev["ts"] >= since_ts]

    def tools_since(self, since_ts: float) -> list[str]:
        """Tool names that actually executed (status != error), from the WS stream.

        This is the authoritative source of truth — the DOM ToolActivityCard
        scrape is unreliable in headless mode.
        """
        seen: list[str] = []
        for ev in self.events:
            if ev["type"] != "tool_execution" or ev["ts"] < since_ts:
                continue
            payload = ev.get("payload", {})
            name = (payload.get("tool_name") or "").strip()
            if name and name not in seen:
                seen.append(name)
        return seen

    def idle_since(self, since_ts: float) -> bool:
        for ev in self.events:
            if ev["ts"] < since_ts:
                continue
            payload = ev.get("payload", {})
            if payload.get("type") == "status" and payload.get("content") == "idle":
                return True
        return False

    def running_tools_since(self, since_ts: float) -> list[str]:
        """Tool names with a running tool_execution event and no success/error yet."""
        running: dict[str, bool] = {}
        for ev in self.events:
            if ev["type"] != "tool_execution" or ev["ts"] < since_ts:
                continue
            payload = ev.get("payload", {})
            name = (payload.get("tool_name") or "").strip()
            if not name:
                continue
            status = payload.get("status")
            if status == "running":
                running[name] = True
            elif status in ("success", "error"):
                running.pop(name, None)
        return list(running)

    def router_meta_since(self, since_ts: float) -> dict:
        """Latest router_info metadata after ``since_ts`` (route, source, task)."""
        meta: dict = {}
        for ev in self.events:
            if ev["type"] != "router_info" or ev["ts"] < since_ts:
                continue
            payload = ev.get("payload", {})
            if isinstance(payload.get("metadata"), dict):
                meta = payload["metadata"]
        if not meta:
            return {}
        features = meta.get("features") or {}
        return {
            "route": meta.get("route", ""),
            "classification_source": meta.get("classification_source", ""),
            "confidence": meta.get("confidence", ""),
            "task_category": features.get("task_category", ""),
            "has_images": bool(features.get("has_images", False)),
        }

    def model_info_since(self, since_ts: float) -> dict:
        """Latest model_info payload after ``since_ts`` (model badge, fallback chain)."""
        info: dict = {}
        for ev in self.events:
            if ev["type"] != "model_info" or ev["ts"] < since_ts:
                continue
            payload = ev.get("payload", {})
            for key in (
                "model",
                "fallback_chain",
                "vision_intake_mode",
                "vision_proxy_model",
            ):
                if payload.get(key) is not None:
                    info[key] = payload.get(key)
        return info

    def assistant_message_seen_since(self, since_ts: float) -> bool:
        """True when an assistant.message WS frame arrived after ``since_ts``."""
        for ev in self.events:
            if ev["ts"] < since_ts or ev["type"] != "assistant.message":
                continue
            payload = ev.get("payload", {})
            msg = payload.get("message") if isinstance(payload, dict) else None
            if isinstance(msg, dict):
                content = msg.get("content") or ""
            else:
                content = payload.get("content") or ""
            if str(content).strip():
                return True
        return False

    def assistant_text_since(self, since_ts: float) -> str:
        """Latest assistant.message content after ``since_ts`` (WS source of truth)."""
        latest = ""
        for ev in self.events:
            if ev["ts"] < since_ts or ev["type"] != "assistant.message":
                continue
            payload = ev.get("payload", {})
            msg = payload.get("message") if isinstance(payload, dict) else None
            if isinstance(msg, dict):
                content = msg.get("content") or ""
            else:
                content = payload.get("content") or ""
            if isinstance(content, str) and content.strip():
                latest = content
        return latest


async def poll_api(
    path: str, *, timeout_s: float = 30.0, interval_s: float = 1.0
) -> dict:
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"{API_URL}{path}")
                if resp.status_code == 200:
                    last = resp.json()
                    return last
            except Exception:
                pass
            await asyncio.sleep(interval_s)
    return last


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
        "cloud_model_tier": settings.get("cloud_model_tier", "flash"),
        "cloud_no_local_fallback": bool(settings.get("cloud_no_local_fallback")),
        "scope_clarification_enabled": settings.get("scope_clarification_enabled"),
        "plan_review_enabled": settings.get("plan_review_enabled"),
        "execution_policy": settings.get("execution_policy", "auto_approve"),
        "effective_profile": "cloud" if cloud_on and cloud_ok else "local",
    }


async def set_unified_settings(**fields: Any) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.put(f"{API_URL}/api/unified-settings", json=fields)


async def fetch_last_turn_tier() -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{API_URL}/api/usage")
            if resp.status_code == 200:
                last = resp.json().get("last_turn") or {}
                return str(last.get("model_tier") or "")
        except Exception:
            pass
    return ""


async def mem0_available() -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{API_URL}/api/mem0/count")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") != "error" and "error" not in data
        except Exception:
            pass
    return False


async def check_vision_vlm_available() -> bool:
    """Return True when Qwen3-VL-4B (vision VLM) is loaded (or can be loaded) in LM Studio."""
    from src.agent.core.complex_utils.lm_studio_vision import (
        is_vision_vlm_loaded,
        ensure_vision_vlm_loaded,
    )

    try:
        if await is_vision_vlm_loaded():
            return True
        return await ensure_vision_vlm_loaded()
    except Exception:
        return False


async def vision_available(profile: str) -> bool:
    vlm_ok = await check_vision_vlm_available()
    if profile == "local":
        return vlm_ok
    runtime = await fetch_runtime_profile()
    return runtime.get("cloud_available", False) and vlm_ok


def resolve_expected_route(expected: str, *, profile: str) -> str:
    if expected == "complex":
        return "complex-cloud"
    if expected == "vision":
        return "vision_cloud" if profile == "cloud" else "vision"
    return expected


def route_matches(actual: str, expected: str, *, profile: str) -> bool:
    if not actual:
        return False
    if expected == "complex":
        return actual == "complex-cloud"
    if expected == "vision":
        if profile == "cloud":
            return actual in VISION_ROUTES and actual == "vision_cloud"
        return actual in VISION_ROUTES
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


async def wait_for_ready(page: Page) -> None:
    print("[EVAL] Waiting for UI to be ready...")
    try:
        await page.locator(".workspace-project-item").first.wait_for(
            state="visible", timeout=30000
        )
    except Exception as e:
        print(f"Failed to find workspace item: {e}")
    await page.wait_for_timeout(1000)


async def new_chat(page: Page) -> None:
    print("[EVAL] Starting new chat...")
    await page.locator('button.workspace-refresh[title="New chat"]').click()
    await page.wait_for_timeout(1500)
    await wait_for_ready(page)


async def is_graph_busy(page: Page) -> bool:
    script = """() => {
          if (document.querySelector('.composer-stop')) return true;
          if (document.querySelector('.hitl-prompt-card.hitl-pending')) return true;
          if (document.querySelector('.tool-activity-running')) return true;
          if (document.querySelector('.streaming-cursor')) return true;
          return false;
        }"""
    try:
        return await asyncio.wait_for(page.evaluate(script), timeout=8.0)
    except Exception:
        return True


async def resolve_hitl(page: Page, expected_tools: list[str] | None = None) -> int:
    pending = page.locator(".hitl-prompt-card.hitl-pending")
    try:
        hitl_count = await pending.count()
    except Exception:
        return 0
    if hitl_count <= 0:
        return 0
    print("\n[EVAL] HITL Prompt detected! Resolving...")
    pending_card = pending.last
    skip = pending_card.locator(".hitl-btn-skip")
    try:
        if await skip.count() > 0:
            await skip.first.click(timeout=5000)
            await page.wait_for_timeout(2000)
            return hitl_count
    except Exception:
        pass
    try:
        if await pending_card.locator(".hitl-scope-question").count() > 0:
            await page.evaluate(
                """() => {
                  const cards = document.querySelectorAll('.hitl-prompt-card.hitl-pending');
                  if (cards.length > 0) {
                      const lastCard = cards[cards.length - 1];
                      lastCard.querySelectorAll('.hitl-scope-question').forEach((q) => {
                          const btn = q.querySelector('.hitl-choice-btn');
                          if (btn) btn.click();
                      });
                  }
                }"""
            )
            await page.wait_for_timeout(500)
        elif await pending_card.locator(".hitl-choice-btn").count() > 0:
            # Special case for Screen Assist tools
            screen_assist_tools = {
                "active_browser_action",
                "get_active_browser_context",
                "get_active_browser_screenshot",
            }
            if expected_tools and any(t in expected_tools for t in screen_assist_tools):
                if (
                    await pending_card.locator(
                        '.hitl-choice-btn:has-text("Read terminal or screen context")'
                    ).count()
                    > 0
                ):
                    await pending_card.locator(
                        '.hitl-choice-btn:has-text("Read terminal or screen context")'
                    ).first.click(timeout=3000)
                else:
                    await pending_card.locator(".hitl-choice-btn").first.click(
                        timeout=3000
                    )
            elif expected_tools and "browser_background_fetch" in expected_tools:
                if (
                    await pending_card.locator(
                        '.hitl-choice-btn:has-text("Search the web")'
                    ).count()
                    > 0
                ):
                    await pending_card.locator(
                        '.hitl-choice-btn:has-text("Search the web")'
                    ).first.click(timeout=3000)
                else:
                    await pending_card.locator(".hitl-choice-btn").first.click(
                        timeout=3000
                    )
            elif expected_tools and "get_active_browser_context" in expected_tools:
                if (
                    await pending_card.locator(
                        '.hitl-choice-btn:has-text("Just answer directly")'
                    ).count()
                    > 0
                ):
                    await pending_card.locator(
                        '.hitl-choice-btn:has-text("Just answer directly")'
                    ).first.click(timeout=3000)
                else:
                    await pending_card.locator(".hitl-choice-btn").first.click(
                        timeout=3000
                    )
            else:
                await pending_card.locator(".hitl-choice-btn").first.click(timeout=3000)
            await page.wait_for_timeout(1000)
    except Exception:
        pass
    approve = page.locator(".hitl-btn-approve")
    try:
        if await approve.count() > 0:
            await approve.first.click(timeout=5000)
            await page.wait_for_timeout(2000)
    except Exception:
        pass
    return hitl_count


async def wait_for_turn_complete(
    page: Page,
    *,
    timeout_s: int,
    min_chars: int,
    expected_tools: list[str] | None = None,
    ws_log: WsEventLog | None = None,
    since_ts: float | None = None,
) -> dict[str, Any]:
    print(f"[EVAL] Waiting for graph idle (up to {timeout_s}s)...")
    start_time = time.monotonic()
    hitl_resolves = 0
    await asyncio.sleep(1.5)
    last_print = start_time
    tool_stall_polls = 0

    async def _executed_tools() -> tuple[list[str], list[str]]:
        dom_tools = await scrape_executed_tools(page)
        ws_tools = ws_log.tools_since(since_ts) if ws_log and since_ts else []
        return merge_executed_tools(ws_tools, dom_tools), ws_tools

    while time.monotonic() - start_time < timeout_s:
        elapsed = time.monotonic() - start_time
        try:
            hitl_resolves += await asyncio.wait_for(
                resolve_hitl(page, expected_tools=expected_tools), timeout=12.0
            )
        except asyncio.TimeoutError:
            print("\n[EVAL] HITL resolve timed out; continuing poll...")

        # Print progress log before checking ws_idle continue conditions
        if time.monotonic() - last_print >= 10:
            try:
                dom_running = await asyncio.wait_for(
                    page.evaluate(
                        "() => Array.from(document.querySelectorAll('.tool-activity-running .tool-activity-name code'))"
                        ".map(e => e.innerText).join(', ')"
                    ),
                    timeout=5.0,
                )
            except Exception:
                dom_running = ""
            ws_running = (
                ws_log.running_tools_since(since_ts) if ws_log and since_ts else []
            )
            tools_running = ", ".join(ws_running) if ws_running else dom_running
            print(
                f"\r[EVAL] ... busy ({elapsed:.0f}s / {timeout_s}s) | tools: {tools_running or 'none'}",
                end="",
                flush=True,
            )
            last_print = time.monotonic()

        ws_idle = bool(ws_log and since_ts and ws_log.idle_since(since_ts))
        if ws_idle:
            try:
                await asyncio.wait_for(
                    page.evaluate(
                        "() => window.__owlynnEval?.clearPendingCorrelation?.()"
                    ),
                    timeout=3.0,
                )
            except Exception:
                pass
            if (
                since_ts
                and ws_log
                and not ws_log.assistant_message_seen_since(since_ts)
            ):
                await asyncio.sleep(1)
                continue
        if ws_log and since_ts:
            busy = not ws_idle
            # Fallback: if WS idle hasn't arrived but DOM shows no busy
            # indicators for >30s, treat as idle (WS event may have been lost)
            if busy and elapsed > 30:
                dom_busy = await is_graph_busy(page)
                if not dom_busy:
                    print(
                        "\n[EVAL] WS idle not received but DOM shows idle — "
                        "treating as complete"
                    )
                    busy = False
        else:
            busy = await is_graph_busy(page)
        if not busy:
            ws_text = (
                ws_log.assistant_text_since(since_ts) if ws_log and since_ts else ""
            )
            response_text = ws_text or await scrape_final_response(page)
            normalized = _normalize_response(response_text)
            tools, ws_tools = await _executed_tools()
            dsml = _is_premature_dsml(response_text)
            tools_ok = expected_tools_satisfied(tools, expected_tools)
            if len(normalized) >= min_chars and not dsml and tools_ok:
                source = "ws" if ws_tools else "dom"
                print(
                    f"\n[EVAL] Turn complete in {elapsed:.1f}s "
                    f"({len(normalized)} chars, tools={tools}, via={source})"
                )
                return {
                    "response_text": response_text,
                    "completed": True,
                    "graph_idle": True,
                    "premature_complete": False,
                    "hitl_resolves": hitl_resolves,
                    "busy_wait_seconds": round(elapsed, 2),
                    "executed_tools": tools,
                    "executed_tools_ws": ws_tools,
                }
            ws_running = (
                ws_log.running_tools_since(since_ts) if ws_log and since_ts else []
            )
            dom_running = await page.evaluate(
                "() => Array.from(document.querySelectorAll('.tool-activity-running .tool-activity-name code'))"
                ".map(e => e.innerText)"
            )
            running_tools = ws_running or dom_running
            if should_exit_idle_tool_stall(
                tools_ok=tools_ok,
                expected_tools=expected_tools,
                normalized_len=len(normalized),
                min_chars=min_chars,
                dsml=dsml,
                running_tools=running_tools,
                stall_polls=tool_stall_polls,
            ):
                print(
                    f"\n[EVAL] Idle tool stall exit in {elapsed:.1f}s "
                    f"({len(normalized)} chars, tools={tools}, missing expected)"
                )
                return {
                    "response_text": response_text,
                    "completed": True,
                    "graph_idle": True,
                    "premature_complete": True,
                    "hitl_resolves": hitl_resolves,
                    "busy_wait_seconds": round(elapsed, 2),
                    "executed_tools": tools,
                    "executed_tools_ws": ws_tools,
                }
            if dsml or (expected_tools and not tools_ok):
                tool_stall_polls += 1
                await asyncio.sleep(2)
                continue
            tool_stall_polls = 0
            if len(normalized) >= min_chars:
                print(
                    f"\n[EVAL] Idle with partial quality ({len(normalized)} chars, dsml={dsml})"
                )
                return {
                    "response_text": response_text,
                    "completed": len(normalized) >= min_chars,
                    "graph_idle": True,
                    "premature_complete": dsml or not tools_ok,
                    "hitl_resolves": hitl_resolves,
                    "busy_wait_seconds": round(elapsed, 2),
                    "executed_tools": tools,
                    "executed_tools_ws": ws_tools,
                }

        await asyncio.sleep(1)

    print("\n[EVAL] Timeout waiting for turn complete!")
    ws_text = ws_log.assistant_text_since(since_ts) if ws_log and since_ts else ""
    response_text = ws_text or await scrape_final_response(page)
    tools, ws_tools = await _executed_tools()
    return {
        "response_text": response_text,
        "completed": False,
        "graph_idle": not await is_graph_busy(page),
        "premature_complete": _is_premature_dsml(response_text),
        "hitl_resolves": hitl_resolves,
        "busy_wait_seconds": round(time.monotonic() - start_time, 2),
        "executed_tools": tools,
        "executed_tools_ws": ws_tools,
    }


async def scrape_final_response(page: Page) -> str:
    for _ in range(3):
        text = await page.evaluate(
            """() => {
              const children = [...document.querySelectorAll('.messages > *')];
              let lastUserIdx = -1;
              children.forEach((el, idx) => {
                if (el.querySelector('.message-user')) lastUserIdx = idx;
              });
              if (lastUserIdx < 0) {
                const bubbles = document.querySelectorAll('.message-assistant .message-bubble');
                for (let i = bubbles.length - 1; i >= 0; i--) {
                  const t = (bubbles[i].innerText || '').trim();
                  if (t && t.toLowerCase() !== 'o') return t;
                }
                return '';
              }
              for (let i = lastUserIdx + 1; i < children.length; i++) {
                const el = children[i];
                const bubble = el.querySelector('.message-assistant .message-bubble')
                  || (el.classList?.contains('message-assistant')
                    ? el.querySelector('.message-bubble')
                    : null);
                if (!bubble) continue;
                const t = (bubble.innerText || '').trim();
                if (t && t.toLowerCase() !== 'o') return t;
              }
              return '';
            }"""
        )
        if _normalize_response(text):
            return text.strip()
        await asyncio.sleep(0.5)
    return ""


async def scrape_executed_tools(page: Page) -> list[str]:
    return await page.evaluate(
        """() => {
          const children = [...document.querySelectorAll('.messages > *')];
          let lastUserIdx = -1;
          children.forEach((el, idx) => {
            if (el.querySelector('.message-user')) lastUserIdx = idx;
          });
          if (lastUserIdx < 0) return [];
          const tools = [];
          for (let i = lastUserIdx + 1; i < children.length; i++) {
            const el = children[i];
            el.querySelectorAll('.tool-activity-name code').forEach(codeEl => {
              const card = codeEl.closest('.tool-activity-card');
              const running = card?.classList.contains('tool-activity-running');
              const failed = card?.classList.contains('tool-activity-failed');
              const name = (codeEl.innerText || '').trim();
              if (name && !running && !failed) tools.push(name);
            });
            if (el.classList?.contains('message-assistant') || el.querySelector('.message-assistant')) {
              break;
            }
          }
          return [...new Set(tools)];
        }"""
    )


async def get_orchestration_data(page: Page) -> dict:
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
        classification_source = await page.evaluate(
            """() => {
              const rows = document.querySelectorAll('.orchestration-row');
              for (const row of rows) {
                const label = row.querySelector('.orchestration-label')?.innerText || '';
                if (label.trim() === 'Source') {
                  return row.querySelector('.orchestration-value')?.innerText?.trim() || '';
                }
              }
              return '';
            }"""
        )
        memory_saved = await page.evaluate(
            "() => document.querySelector('.orchestration-memory-ok')?.innerText?.trim() || ''"
        )
        tools = await scrape_executed_tools(page)
        return {
            "model": model,
            "route": route,
            "confidence": confidence,
            "classification_source": classification_source,
            "memory_saved": memory_saved,
            "tools": tools,
        }
    except Exception as e:
        print(f"[EVAL] Error scraping orchestration data: {e}")
        return {
            "model": "",
            "route": "",
            "confidence": "",
            "classification_source": "",
            "memory_saved": "",
            "tools": [],
        }


async def send_message(page: Page, text: str) -> None:
    print(f"[EVAL] Sending message ({len(text)} chars)...")
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
            print("[EVAL] Message sent successfully.")
            return
        except Exception:
            print(
                f"[EVAL] Send attempt {attempt + 1} failed (textarea not cleared). Retrying..."
            )
            await textarea.press("Enter")
            await page.wait_for_timeout(1000)

    print("[EVAL] Warning: Failed to confirm message send after 5 attempts.")


async def attach_file_via_drop(page: Page, filepath: Path) -> None:
    print(f"[EVAL] Attaching file via drop: {filepath.name}")
    raw = filepath.read_bytes()
    mime = mimetypes.guess_type(filepath.name)[0] or "application/octet-stream"
    data_url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    ok = await page.evaluate(
        """([name, mimeType, dataUrl]) => {
          const wrapper = document.querySelector('.composer-wrapper');
          if (!wrapper) return false;
          const binary = atob(dataUrl.split(',')[1]);
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          const blob = new Blob([bytes], { type: mimeType });
          const file = new File([blob], name, { type: mimeType });
          const dt = new DataTransfer();
          dt.items.add(file);
          const event = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt });
          wrapper.dispatchEvent(event);
          return true;
        }""",
        [filepath.name, mime, data_url],
    )
    if not ok:
        raise RuntimeError("Failed to dispatch file drop on composer")
    await page.wait_for_timeout(800)
    chip = page.locator(
        ".composer-attachments .attachment-name", has_text=filepath.name
    )
    await chip.wait_for(state="visible", timeout=10000)


async def upload_file_api(project_id: str, filepath: Path) -> None:
    print(f"[EVAL] Uploading {filepath.name} to project {project_id}...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        with filepath.open("rb") as fh:
            resp = await client.post(
                f"{API_URL}/api/upload",
                params={"project_id": project_id},
                files={
                    "file": (
                        filepath.name,
                        fh,
                        mimetypes.guess_type(filepath.name)[0]
                        or "application/octet-stream",
                    )
                },
            )
        if resp.status_code != 200 or resp.json().get("status") == "error":
            raise RuntimeError(f"Upload failed: {resp.text}")


async def seed_workspace_file(project_id: str, filename: str, content: str) -> Path:
    ws_dir = WORKSPACE_DIR / "projects" / project_id
    target = ws_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"[EVAL] Seeded workspace file: {target}")
    return target


async def poll_file_processed(
    project_id: str, filename: str, *, timeout_s: float = 45.0
) -> bool:
    deadline = time.monotonic() + timeout_s
    processed_cache = WORKSPACE_DIR / "projects" / project_id / ".processed"
    while time.monotonic() < deadline:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(
                    f"{API_URL}/api/files",
                    params={"project_id": project_id, "sub_path": ""},
                )
                if resp.status_code == 200:
                    for item in resp.json().get("files", []):
                        if (
                            item.get("name") == filename
                            and item.get("status") == "processed"
                        ):
                            return True
            except Exception:
                pass
        for suffix in (".txt", ".md"):
            if (processed_cache / f"{filename}{suffix}").exists():
                return True
        await asyncio.sleep(1.5)
    return False


def _infer_vision_intake_mode(ws_router: dict, ws_model: dict) -> str | None:
    if not ws_router.get("has_images"):
        return None
    chain = ws_model.get("fallback_chain") or []
    for step in chain:
        if isinstance(step, dict) and step.get("reason") == "vision_proxy_failed":
            return "fallback"
    if "vision" in (ws_router.get("task_category") or "").lower():
        return "proxy"
    return "proxy"


def _vision_route_acceptable(exchange: dict) -> bool:
    task = (exchange.get("task_category") or "").lower()
    if "vision" in task:
        return True
    if exchange.get("has_images") and exchange.get("vision_intake_mode") != "fallback":
        return True
    chain = exchange.get("fallback_chain") or []
    for step in chain:
        if isinstance(step, dict) and step.get("reason") == "vision_proxy_failed":
            return False
    return bool(exchange.get("has_images"))


def should_skip_turn(
    item: dict, *, profile: str, mem0_ok: bool, vision_ok: bool
) -> str | None:
    skip = item.get("skip_if")
    if skip == "mem0_unavailable" and not mem0_ok:
        return "mem0_unavailable"
    if skip == "vision_unavailable" and not vision_ok:
        return "vision_unavailable"
    return None


def score_exchange(exchange: dict, expected: dict, *, profile: str) -> dict:
    scores: dict[str, Any] = {
        "route_match": False,
        "tools_match": False,
        "response_ok": False,
        "dsml_leak": False,
        "cloud_regression": False,
        "cloud_fallback_fail": False,
        "premature_complete": exchange.get("premature_complete", False),
        "grade": 0,
    }
    expected_route = expected.get("expected_route", "")
    min_chars = expected.get("min_response_chars", 10)
    body = _normalize_response(exchange.get("assistant_response_full", ""))
    scores["response_ok"] = len(body) >= min_chars
    scores["dsml_leak"] = _has_dsml_leak(body)

    route_pts = (
        35
        if expected.get("expected_tier")
        or expected.get("expected_source")
        or expected.get("expected_vision")
        else 40
    )
    if route_matches(exchange.get("route", ""), expected_route, profile=profile):
        scores["route_match"] = True
        scores["grade"] += route_pts
    elif expected_route == "complex" and exchange.get("route") in COMPLEX_ROUTES:
        scores["route_match"] = True
        scores["grade"] += max(20, route_pts - 10)
    elif expected_route == "vision" and exchange.get("route") in VISION_ROUTES:
        scores["route_match"] = True
        scores["grade"] += route_pts
    elif (
        expected.get("expected_vision")
        and exchange.get("route") in COMPLEX_ROUTES
        and _vision_route_acceptable(exchange)
    ):
        # Router uses complex-cloud for images; task_category marks vision work.
        scores["route_match"] = True
        scores["vision_route_ok"] = True
        scores["grade"] += max(20, route_pts - 10)

    resp_pts = 15 if expected.get("expected_marker") else 20
    if scores["response_ok"]:
        scores["grade"] += resp_pts
    if scores["dsml_leak"]:
        scores["grade"] = max(0, scores["grade"] - 15)
    if scores["premature_complete"]:
        scores["grade"] = max(0, scores["grade"] - 10)

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
        tool_pts = 25 if expected.get("expected_marker") else 40
        if scores["tools_match"]:
            scores["grade"] += tool_pts
    else:
        scores["tools_match"] = True
        scores["grade"] += 30

    marker = expected.get("expected_marker")
    if marker:
        scores["recall_ok"] = marker.lower() in body.lower()
        if scores["recall_ok"]:
            scores["grade"] += 20
        else:
            scores["recall_ok"] = False

    expected_tier = expected.get("expected_tier")
    if expected_tier:
        actual_tier = exchange.get("model_tier", "")
        scores["tier_match"] = actual_tier == expected_tier
        if scores["tier_match"]:
            scores["grade"] += 15
        scores["tier_note"] = (
            "frontier hints do not auto-escalate tier; tier comes from profile.cloud_model_tier"
            if expected_tier == "flash"
            else ""
        )

    expected_source = expected.get("expected_source")
    if expected_source:
        accepted = (
            expected_source if isinstance(expected_source, list) else [expected_source]
        )
        actual_source = exchange.get("classification_source", "")
        scores["source_match"] = actual_source in accepted
        scores["actual_source"] = actual_source
        if scores["source_match"]:
            scores["grade"] += 15
        elif actual_source and actual_source not in ("keyword_bypass", "deterministic"):
            scores["grade"] += 10  # classifier ran, just a different label
        elif actual_source:
            scores["grade"] += 5  # bypass fired — classifier path not exercised

    if expected.get("expected_vision"):
        task = (exchange.get("task_category") or "").lower()
        scores["vision_match"] = (
            "vision" in task
            or exchange.get("has_images", False)
            or exchange.get("vision_intake_mode") == "proxy"
        )
        if scores["vision_match"]:
            scores["grade"] += 15
        marker = expected.get("expected_marker")
        if marker:
            if marker.lower() in body.lower() and scores["vision_match"]:
                scores["vision_ocr_ok"] = True
            elif scores.get("vision_match"):
                scores["vision_ocr_ok"] = False
                scores["grade"] = min(scores["grade"], 60)

    for ev_name in expected.get("expected_ws_events", []):
        key = f"ws_{ev_name}"
        scores[key] = exchange.get("ws_events_seen", {}).get(ev_name, False)
        if scores[key]:
            scores["grade"] += 5

    for ev_name in expected.get("forbid_ws_events", []):
        seen = exchange.get("ws_events_seen", {}).get(ev_name, False)
        scores[f"ws_forbid_{ev_name}"] = not seen
        if seen:
            scores["grade"] = max(0, scores["grade"] - 10)

    if expected.get("check_processed"):
        scores["processed_ok"] = exchange.get("file_processed", False)
        if scores["processed_ok"]:
            scores["grade"] += 10

    scores["grade"] = min(100, scores["grade"])
    badge = (exchange.get("model_badge") or "").strip()
    if profile == "cloud" and badge in CLOUD_FAILURE_BADGES:
        scores["cloud_regression"] = True
        scores["cloud_fallback_fail"] = True
        scores["grade"] = min(scores["grade"], 49)
    return scores


async def run_turn(
    page: Page,
    item: dict,
    *,
    profile: str,
    project_id: str,
    ws_log: WsEventLog,
    index: int,
) -> dict:
    from src.agent.cloud.cloud_circuit_breaker import reset_circuit_breaker

    reset_circuit_breaker()

    turn_start = time.time()
    ws_before = len(ws_log.events)

    if item.get("new_chat_before"):
        await new_chat(page)

    if item.get("set_tier_before"):
        await set_unified_settings(cloud_model_tier=item["set_tier_before"])

    if item.get("workspace_seed"):
        await seed_workspace_file(
            project_id,
            item["workspace_seed"],
            resolve_workspace_seed_content(item),
        )
        await asyncio.sleep(2.0)

    attach_name = item.get("attach_file")
    if attach_name:
        fixture = FIXTURE_DIR / attach_name
        if not fixture.exists():
            raise FileNotFoundError(f"Missing fixture: {fixture}")
        await attach_file_via_drop(page, fixture)
        if item.get("check_processed"):
            processed = await poll_file_processed(
                project_id, attach_name, timeout_s=20.0
            )
            item = {**item, "_upload_processed": processed}

    start_time = time.monotonic()
    await send_message(page, item["prompt"])
    wait_result = await wait_for_turn_complete(
        page,
        timeout_s=item.get("timeout_s", COMPLEX_TIMEOUT_S),
        min_chars=item.get("min_response_chars", 10),
        expected_tools=item.get("expected_tools"),
        ws_log=ws_log,
        since_ts=turn_start,
    )
    duration = time.monotonic() - start_time
    orch = await get_orchestration_data(page)
    model_tier = await fetch_last_turn_tier()

    if item.get("restore_tier_after"):
        await set_unified_settings(cloud_model_tier=item["restore_tier_after"])

    # WS stream is the source of truth; DOM scrape is a fallback only.
    ws_tools = wait_result.get("executed_tools_ws") or ws_log.tools_since(turn_start)
    ws_router = ws_log.router_meta_since(turn_start)
    ws_model = ws_log.model_info_since(turn_start)
    ws_since = {
        ev: ws_log.saw(ev, since_ts=turn_start)
        for ev in (
            "memory_updated",
            "context_summarized",
            "file_status",
            "router_info",
            "tool_execution",
        )
    }

    file_processed = item.get("_upload_processed", False)
    check_name = item.get("check_processed")
    if check_name and not file_processed:
        file_processed = await poll_file_processed(
            project_id, check_name, timeout_s=5.0
        )

    response_text = wait_result["response_text"]
    exchange = {
        "turn_index": index + 1,
        "prompt_id": item["id"],
        "topic": item["topic"],
        "pipeline_notes": item.get("pipeline_notes", ""),
        "user_query": item["prompt"],
        "assistant_response": response_text[:500]
        + ("..." if len(response_text) > 500 else ""),
        "assistant_response_full": response_text,
        "response_completed": wait_result["completed"],
        "graph_idle": wait_result["graph_idle"],
        "premature_complete": wait_result["premature_complete"],
        "hitl_resolves": wait_result["hitl_resolves"],
        "busy_wait_seconds": wait_result["busy_wait_seconds"],
        "expected_route_resolved": resolve_expected_route(
            item["expected_route"], profile=profile
        ),
        "model_badge": ws_model.get("model") or orch.get("model"),
        "route": ws_router.get("route") or orch.get("route"),
        "route_dom": orch.get("route"),
        "task_category": ws_router.get("task_category"),
        "has_images": ws_router.get("has_images", False),
        "fallback_chain": ws_model.get("fallback_chain"),
        "vision_intake_mode": ws_model.get("vision_intake_mode")
        or _infer_vision_intake_mode(ws_router, ws_model),
        "vision_proxy_model": ws_model.get("vision_proxy_model"),
        "model_tier": model_tier,
        "confidence": ws_router.get("confidence") or orch.get("confidence"),
        "classification_source": ws_router.get("classification_source")
        or orch.get("classification_source"),
        "memory_saved": orch.get("memory_saved"),
        "executed_tools": ws_tools
        or wait_result["executed_tools"]
        or orch.get("tools"),
        "executed_tools_ws": ws_tools,
        "executed_tools_dom": wait_result["executed_tools"] or orch.get("tools"),
        "ws_events_seen": ws_since,
        "ws_events_captured": ws_log.types_since(turn_start),
        "file_processed": file_processed,
        "duration_seconds": round(duration, 2),
        "approx_tps": round((len(response_text) / 4.0) / duration, 2)
        if duration > 0
        else 0,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "scored",
    }
    return exchange


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
    parser.add_argument(
        "--strict-cloud",
        action="store_true",
        help="Block local Qwen fallback (default when effective profile is cloud)",
    )
    parser.add_argument(
        "--allow-local-fallback",
        action="store_true",
        help="Opt out of strict cloud mode for this run",
    )
    parser.add_argument(
        "--ids",
        default="",
        help="Comma-separated turn IDs to run (e.g. F3.1,F9.1)",
    )
    args = parser.parse_args()

    fixture_script = REPO_ROOT / "scripts" / "generate_eval_fixtures.py"
    if not FIXTURE_DIR.exists() or not any(FIXTURE_DIR.iterdir()):
        import subprocess

        subprocess.run(["python", str(fixture_script)], check=True)

    runtime = await fetch_runtime_profile()
    prior_cloud = runtime["cloud_escalation_enabled"]
    prior_tier = runtime.get("cloud_model_tier", "flash")
    prior_strict = runtime.get("cloud_no_local_fallback", False)
    prior_scope = runtime.get("scope_clarification_enabled")
    prior_plan = runtime.get("plan_review_enabled")
    prior_execution = runtime.get("execution_policy", "auto_approve")
    if args.cloud_off:
        print("[EVAL] Disabling cloud escalation for this run...")
        await set_unified_settings(cloud_escalation_enabled=False)
        runtime = await fetch_runtime_profile()

    if args.profile == "auto":
        profile = runtime["effective_profile"]
    else:
        profile = args.profile

    use_strict = (
        not args.allow_local_fallback
        and profile == "cloud"
        and (args.strict_cloud or args.profile in ("auto", "cloud"))
    )
    if use_strict:
        print("[EVAL] Enabling strict cloud mode (no local Qwen fallback)...")
        await set_unified_settings(cloud_no_local_fallback=True)
        runtime = await fetch_runtime_profile()

    print("[EVAL] Disabling scope/plan HITL for automated run...")
    await set_unified_settings(
        scope_clarification_enabled=False,
        plan_review_enabled=False,
        execution_policy="auto_approve",
    )

    id_filter = (
        {x.strip() for x in args.ids.split(",") if x.strip()} if args.ids else None
    )

    if profile == "cloud" and not runtime.get("cloud_available"):
        raise SystemExit(
            "[EVAL] Cloud profile requires valid DeepSeek API (GET /api/cloud-status). "
            "Configure DEEPSEEK_API_KEY in Keychain or .env.local before --profile cloud."
        )

    mem0_ok = await mem0_available()
    vision_vlm_ok = await check_vision_vlm_available()
    vision_ok = await vision_available(profile)
    print(
        f"[EVAL] mem0_available={mem0_ok} vision_vlm_ok={vision_vlm_ok} "
        f"vision_ok={vision_ok}"
    )

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:6]
    project_name = f"FrontierEval_{suffix}"
    project_id = await create_project(project_name)

    eval_data: dict[str, Any] = {
        "project_name": project_name,
        "project_id": project_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "eval_version": "2026-06-11",
        "runtime_profile": profile,
        "cloud_escalation_enabled": runtime["cloud_escalation_enabled"],
        "cloud_available": runtime["cloud_available"],
        "cloud_model": runtime["cloud_model"],
        "cloud_model_tier": runtime.get("cloud_model_tier", "flash"),
        "mem0_available": mem0_ok,
        "vision_vlm_ok": vision_vlm_ok,
        "vision_available": vision_ok,
        "cloud_scoring": "cloud_failure",
        "strict_cloud": use_strict,
        "hardware_profile": "Apple M4 Air 24GB",
        "turn_count": len(TEST_PROMPTS),
        "exchanges": [],
        "skipped_turns": [],
    }

    total_score = 0
    scored_turns = 0

    try:
        async with async_playwright() as p:
            print("[EVAL] Starting Playwright Chromium (headless)...")
            browser = await p.chromium.launch(headless=True)
            page = await (
                await browser.new_context(viewport={"width": 1440, "height": 900})
            ).new_page()
            ws_log = WsEventLog()
            ws_log.attach(page)

            print(
                f"[EVAL] Profile: {profile} | cloud_escalation={runtime['cloud_escalation_enabled']} "
                f"| strict_cloud={use_strict}"
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
                if id_filter and prompt_id not in id_filter:
                    continue
                skip_reason = should_skip_turn(
                    item, profile=profile, mem0_ok=mem0_ok, vision_ok=vision_ok
                )
                print("\n" + "=" * 80)
                print(
                    f"  EXCHANGE {index + 1}/{len(TEST_PROMPTS)}: [{prompt_id}] {item['topic']}"
                )
                print("=" * 80)

                if skip_reason:
                    print(f"[EVAL] SKIPPED ({skip_reason})")
                    skipped = {
                        "prompt_id": prompt_id,
                        "topic": item["topic"],
                        "reason": skip_reason,
                        "status": "skipped",
                    }
                    eval_data["skipped_turns"].append(skipped)
                    eval_data["exchanges"].append(skipped)
                    continue

                exchange = await run_turn(
                    page,
                    item,
                    profile=profile,
                    project_id=project_id,
                    ws_log=ws_log,
                    index=index,
                )
                scores = score_exchange(exchange, item, profile=profile)
                exchange["scores"] = scores
                exchange["cloud_regression"] = scores.get("cloud_regression", False)
                total_score += scores["grade"]
                scored_turns += 1

                print(
                    f"Model: {exchange['model_badge']} | Route: {exchange['route']} "
                    f"(expected {exchange['expected_route_resolved']}) | tier={exchange.get('model_tier')}"
                )
                if scores.get("cloud_regression"):
                    print(
                        "  CLOUD FAILURE: cloud-intended turn "
                        f"(badge={exchange['model_badge']})"
                    )
                print(
                    f"Source: {exchange.get('classification_source')} | Tools: {exchange['executed_tools']} "
                    f"| idle={exchange['graph_idle']} | dsml={scores['dsml_leak']}"
                )
                print(f"Grade: {scores['grade']}/100")

                eval_data["exchanges"].append(exchange)
                OUTPUT_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(OUTPUT_DATA_FILE, "w") as f:
                    json.dump(eval_data, f, indent=2)
                await page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{index + 1:02d}_{prompt_id}.png")
                )

            max_score = scored_turns * 100
            eval_data["scored_turns"] = scored_turns
            eval_data["final_score"] = f"{total_score}/{max_score}"
            eval_data["score_percentage"] = (
                round((total_score / max_score) * 100, 2) if max_score else 0.0
            )
            with open(OUTPUT_DATA_FILE, "w") as f:
                json.dump(eval_data, f, indent=2)
            print(f"\n[EVAL] Saved {OUTPUT_DATA_FILE}")
            print(
                f"[EVAL] Final: {eval_data['final_score']} ({eval_data['score_percentage']}%) "
                f"[{scored_turns} scored, {len(eval_data['skipped_turns'])} skipped]"
            )
            await browser.close()
    finally:
        if args.cloud_off and prior_cloud:
            print("[EVAL] Restoring cloud escalation...")
            await set_unified_settings(cloud_escalation_enabled=True)
        await set_unified_settings(cloud_no_local_fallback=prior_strict)
        await set_unified_settings(cloud_model_tier=prior_tier)
        if prior_scope is not None:
            await set_unified_settings(scope_clarification_enabled=prior_scope)
        if prior_plan is not None:
            await set_unified_settings(plan_review_enabled=prior_plan)
        if prior_execution is not None:
            await set_unified_settings(execution_policy=prior_execution)
        await delete_project(project_id)


if __name__ == "__main__":
    asyncio.run(main())
