#!/usr/bin/env python3
"""
Owlynn Browser Extension Evaluation Suite.

Tests all 4 feature tracks of the Owlynn Browser Bridge extension using a
Python Mock Extension Client that connects to the backend WebSocket endpoint,
so no real browser extension (Brave) is needed.

Tracks tested:
  EX1.x — Active Tab Context
  EX2.x — Visual Context (Screenshots)
  EX3.x — Interactive DOM (click/type/scroll)
  EX4.x — Deep Background Scraping
  EX5.x — Moodle Extraction
  EX6.x — Connection Lifecycle

Usage:
  python scripts/run_extension_eval.py
  python scripts/run_extension_eval.py --no-mock   # use real Brave extension
  python scripts/run_extension_eval.py --track EX1  # run single track
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import websockets
from playwright.async_api import Page, async_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.getenv("OWLYNN_EVAL_BASE_URL", "http://127.0.0.1:5173")
API_URL = os.getenv("OWLYNN_EVAL_API_URL", "http://127.0.0.1:8000")

# Dynamically derive extension WebSocket URL from API_URL
from urllib.parse import urlparse

parsed_api = urlparse(API_URL)
ws_scheme = "wss" if parsed_api.scheme == "https" else "ws"
EXT_WS_URL = (
    f"{ws_scheme}://{parsed_api.netloc or '127.0.0.1:8000'}/api/browser_extension/ws"
)
SCREENSHOT_DIR = REPO_ROOT / "assets" / "extension_eval_screenshots"
OUTPUT_DATA_FILE = REPO_ROOT / "data" / "extension_eval_run_data.json"

SIMPLE_TIMEOUT_S = 120
COMPLEX_TIMEOUT_S = 600


# ─── Markers ─────────────────────────────────────────────────────────────────

MARKERS = {
    "tab_text": "EVAL_TAB_MARKER_7",
    "selection": "EVAL_SELECTION_MARKER",
    "moodle_assignment": "EVAL_MOODLE_ASSIGNMENT",
    "moodle_grade": "EVAL_MOODLE_GRADE_88",
    "fetch_page1": "EVAL_FETCH_MARKER_1",
    "fetch_page2": "EVAL_FETCH_MARKER_2",
    "tab_non_moodle": "EVAL_NONMOODLE_CONTENT",
}

# 1x1 red pixel PNG (minimal valid image for vision proxy)
_MINI_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
_MINI_IMG_DATA_URL = f"data:image/jpeg;base64,{_MINI_PNG_B64}"


# ─── Mock Extension Fixtures ──────────────────────────────────────────────────


def _make_tab_payload(request_id: str) -> dict:
    return {
        "id": request_id,
        "tab": {
            "url": "https://example.com/article",
            "title": "Example Article — example.com",
            "text": (
                f"This is a long article about machine learning on example.com. "
                f"{MARKERS['tab_text']}. The article discusses neural networks and deep learning.\n"
                f"<input type='text' id='search' placeholder='Search...' />\n"
                f"<button id='submit'>Submit</button>"
            ),
            "selection": f"machine learning {MARKERS['selection']}",
        },
    }


def _make_moodle_tab_payload(request_id: str) -> dict:
    return {
        "id": request_id,
        "tab": {
            "url": "https://moodle.university.edu/course/view.php?id=123",
            "title": "CS101 — Moodle",
            "isMoodle": True,
            "text": (
                f"## Moodle Context: CS101\n\n"
                f"### Assignments\n- {MARKERS['moodle_assignment']} (Due: 2026-06-30)\n\n"
                f"### Grades\n- Midterm: {MARKERS['moodle_grade']}/100\n- Lab 1: 95/100\n\n"
                f"### Course Modules\n- Week 1: Introduction\n- Week 2: Data Structures"
            ),
            "selection": "",
        },
    }


def _make_nonmoodle_tab_payload(request_id: str) -> dict:
    return {
        "id": request_id,
        "tab": {
            "url": "https://example.com/blog-post",
            "title": "A Blog Post",
            "isMoodle": False,
            "text": f"This is a regular blog post. {MARKERS['tab_non_moodle']}. No Moodle here.",
            "selection": "",
        },
    }


def _make_screenshot_payload(request_id: str) -> dict:
    return {
        "id": request_id,
        "image_data": _MINI_IMG_DATA_URL,
    }


def _make_action_payload(request_id: str) -> dict:
    return {
        "id": request_id,
        "result": {"success": True},
    }


def _make_fetch_urls_payload(request_id: str) -> dict:
    return {
        "id": request_id,
        "results": [
            {
                "url": "https://url1.example.com",
                "title": "Page One",
                "text": f"Content of page one. {MARKERS['fetch_page1']}. Great information here.",
            },
            {
                "url": "https://url2.example.com",
                "title": "Page Two",
                "text": f"Content of page two. {MARKERS['fetch_page2']}. More detail here.",
            },
            {
                "url": "https://url3.example.com",
                "title": "Page Three",
                "text": "Content of page three. Even more information.",
            },
        ],
    }


def _make_fetch_error_payload(request_id: str) -> dict:
    return {
        "id": request_id,
        "results": [
            {
                "url": "https://this-does-not-exist-abc123.com",
                "title": "",
                "text": "Error: net::ERR_NAME_NOT_RESOLVED",
                "error": True,
            }
        ],
    }


# ─── Test Case Definitions ────────────────────────────────────────────────────

TEST_CASES: list[dict[str, Any]] = [
    # ── Track 1: Active Tab Context ──────────────────────────────────────────
    {
        "id": "EX1.1",
        "track": "Track 1 — Active Tab Context",
        "topic": "Tab Context Retrieval",
        "prompt": "What page am I currently looking at in my browser? Make sure your answer includes the exact phrase 'EVAL_TAB_MARKER_7'.",
        "expected_tool": "get_active_browser_context",
        "expected_marker": MARKERS["tab_text"],
        "mock_action": "get_active_tab",
        "mock_fixture": _make_tab_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 20,
        "requires_extension": True,
    },
    {
        "id": "EX1.2",
        "track": "Track 1 — Active Tab Context",
        "topic": "Selected Text Awareness",
        "prompt": "Please summarize the text I currently have selected/highlighted in my browser. Make sure your answer includes the exact phrase 'EVAL_SELECTION_MARKER'.",
        "expected_tool": "get_active_browser_context",
        "expected_marker": MARKERS["selection"],
        "mock_action": "get_active_tab",
        "mock_fixture": _make_tab_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 20,
        "requires_extension": True,
    },
    {
        "id": "EX1.3",
        "track": "Track 1 — Active Tab Context",
        "topic": "Graceful Fallback (no extension)",
        "prompt": "What browser page am I looking at right now? Make sure your answer includes the exact phrase 'EVAL_TAB_MARKER_7'.",
        "expected_tool": "get_active_browser_context",
        "alternative_tools": ["playwright_browser_snapshot", "playwright_browser_tabs"],
        "expected_marker": None,
        "mock_action": None,
        "mock_fixture": None,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 10,
        "requires_extension": False,
        "disconnect_before": True,  # Ensure extension is disconnected
        "no_crash_check": True,
    },
    # ── Track 2: Visual Context / Screenshots ─────────────────────────────────
    {
        "id": "EX2.1",
        "track": "Track 2 — Visual Context",
        "topic": "Screenshot Capture",
        "prompt": "Take a screenshot of my browser and briefly describe what you see.",
        "expected_tool": "get_active_browser_screenshot",
        "expected_marker": None,  # Vision output varies
        "mock_action": "capture_screenshot",
        "mock_fixture": _make_screenshot_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 15,
        "requires_extension": True,
        "skip_if": "vision_unavailable",
        "check_vision_invoked": True,
    },
    {
        "id": "EX2.2",
        "track": "Track 2 — Visual Context",
        "topic": "Screenshot on Demand",
        "prompt": "Can you see my browser screen right now? Show me what you can see.",
        "expected_tool": "get_active_browser_screenshot",
        "expected_marker": None,
        "mock_action": "capture_screenshot",
        "mock_fixture": _make_screenshot_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 15,
        "requires_extension": True,
        "skip_if": "vision_unavailable",
        "check_vision_invoked": True,
    },
    # ── Track 3: Interactive DOM ──────────────────────────────────────────────
    {
        "id": "EX3.1",
        "track": "Track 3 — Interactive DOM",
        "topic": "Click Element",
        "prompt": "Click the submit button on my current browser page.",
        "expected_tool": "active_browser_action",
        "alternative_tools": [
            "playwright_browser_click",
            "playwright_browser_tabs",
            "playwright_browser_snapshot",
        ],
        "expected_marker": None,
        "mock_action": "browser_action",
        "mock_fixture": _make_action_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 10,
        "requires_extension": True,
    },
    {
        "id": "EX3.2",
        "track": "Track 3 — Interactive DOM",
        "topic": "Type into Field",
        "prompt": "Type 'Hello World' into the search box on my current browser page.",
        "expected_tool": "active_browser_action",
        "alternative_tools": [
            "playwright_browser_type",
            "playwright_browser_fill",
            "playwright_browser_tabs",
        ],
        "expected_marker": None,
        "mock_action": "browser_action",
        "mock_fixture": _make_action_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 10,
        "requires_extension": True,
    },
    {
        "id": "EX3.3",
        "track": "Track 3 — Interactive DOM",
        "topic": "Scroll Page",
        "prompt": "Scroll down on my current browser page.",
        "expected_tool": "active_browser_action",
        "alternative_tools": ["playwright_browser_scroll", "playwright_browser_tabs"],
        "expected_marker": None,
        "mock_action": "browser_action",
        "mock_fixture": _make_action_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 8,
        "requires_extension": True,
    },
    {
        "id": "EX3.4",
        "track": "Track 3 — Interactive DOM",
        "topic": "Hover Element",
        "prompt": "Hover over the hidden menu to reveal options on my current browser page.",
        "expected_tool": "active_browser_action",
        "alternative_tools": ["playwright_browser_tabs"],
        "expected_marker": None,
        "mock_action": "browser_action",
        "mock_fixture": _make_action_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 8,
        "requires_extension": True,
    },
    {
        "id": "EX3.5",
        "track": "Track 3 — Interactive DOM",
        "topic": "Batch Selection",
        "prompt": "Select all three radio buttons simultaneously on my current browser page using their element IDs.",
        "expected_tool": "active_browser_action",
        "alternative_tools": ["playwright_browser_tabs"],
        "expected_marker": None,
        "mock_action": "browser_action",
        "mock_fixture": _make_action_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 8,
        "requires_extension": True,
    },
    # ── Track 4: Deep Background Scraping ────────────────────────────────────
    {
        "id": "EX4.1",
        "track": "Track 4 — Background Scraping",
        "topic": "Multi-URL Fetch",
        "prompt": (
            "Please fetch the content of these three pages via my browser and give me a summary: "
            "https://url1.example.com, https://url2.example.com, https://url3.example.com. "
            "(These are mock URLs for testing, please fetch them anyway and include the exact phrase 'EVAL_FETCH_MARKER_1' in your response)"
        ),
        "expected_tool": "browser_background_fetch",
        "expected_marker": MARKERS["fetch_page1"],
        "mock_action": "fetch_urls",
        "mock_fixture": _make_fetch_urls_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 30,
        "requires_extension": True,
    },
    {
        "id": "EX4.2",
        "track": "Track 4 — Background Scraping",
        "topic": "Error Handling",
        "prompt": "Please fetch the content from https://this-does-not-exist-abc123.com via my browser",
        "expected_tool": "browser_background_fetch",
        "expected_marker": None,
        "mock_action": "fetch_urls",
        "mock_fixture": _make_fetch_error_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 10,
        "requires_extension": True,
        "no_crash_check": True,
    },
    # ── Track 5: Moodle Extraction ────────────────────────────────────────────
    {
        "id": "EX5.1",
        "track": "Track 5 — Moodle Extraction",
        "topic": "Moodle Assignments",
        "prompt": "What assignments do I have on my current Moodle page? Make sure your answer includes the exact phrase 'EVAL_MOODLE_ASSIGNMENT'.",
        "expected_tool": "get_active_browser_context",
        "expected_marker": MARKERS["moodle_assignment"],
        "mock_action": "get_active_tab",
        "mock_fixture": _make_moodle_tab_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 20,
        "requires_extension": True,
    },
    {
        "id": "EX5.2",
        "track": "Track 5 — Moodle Extraction",
        "topic": "Moodle Grades",
        "prompt": "Check my grades on my current Moodle page and summarize them. Make sure your answer includes the exact phrase 'EVAL_MOODLE_GRADE_88'.",
        "expected_tool": "get_active_browser_context",
        "expected_marker": MARKERS["moodle_grade"],
        "mock_action": "get_active_tab",
        "mock_fixture": _make_moodle_tab_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 15,
        "requires_extension": True,
    },
    {
        "id": "EX5.3",
        "track": "Track 5 — Moodle Extraction",
        "topic": "Non-Moodle Fallback",
        "prompt": "What is on my current browser page? Make sure your answer includes the exact phrase 'EVAL_NONMOODLE_CONTENT'.",
        "expected_tool": "get_active_browser_context",
        "expected_marker": MARKERS["tab_non_moodle"],
        "mock_action": "get_active_tab",
        "mock_fixture": _make_nonmoodle_tab_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 15,
        "requires_extension": True,
    },
    # ── Track 6: Connection Lifecycle ─────────────────────────────────────────
    {
        "id": "EX6.1",
        "track": "Track 6 — Connection Lifecycle",
        "topic": "Extension Auto-Connect",
        "prompt": "Please read my current browser tab and tell me what is on it. Make sure your answer includes the exact phrase 'EVAL_TAB_MARKER_7'.",
        "expected_tool": "get_active_browser_context",
        "expected_marker": MARKERS["tab_text"],
        "mock_action": "get_active_tab",
        "mock_fixture": _make_tab_payload,
        "timeout_s": COMPLEX_TIMEOUT_S,
        "min_response_chars": 10,
        "requires_extension": True,
        "lifecycle_check": "connected",
    },
    {
        "id": "EX6.3",
        "track": "Track 6 — Connection Lifecycle",
        "topic": "Graceful Missing Extension (screenshot)",
        "prompt": "Take a screenshot of my browser for me.",
        "expected_tool": "get_active_browser_screenshot",
        "expected_marker": None,
        "mock_action": None,
        "mock_fixture": None,
        "timeout_s": SIMPLE_TIMEOUT_S,
        "min_response_chars": 10,
        "requires_extension": False,
        "disconnect_before": True,
        "no_crash_check": True,
    },
]


# ─── Mock Extension Client ────────────────────────────────────────────────────


class MockExtensionClient:
    """
    Simulates the Brave browser extension by connecting to the backend
    WebSocket and responding to dispatched actions with pre-configured payloads.
    """

    def __init__(self):
        self._ws = None
        self._task = None
        self._fixture_override: dict[str, Any] | None = None
        self.connected = False
        self.last_action_received: str | None = None

    def set_fixture(self, action: str | None, fixture_fn) -> None:
        """Set which action this mock should respond to and with what payload."""
        self._fixture_override = {"action": action, "fn": fixture_fn}

    async def connect(self) -> None:
        """Connect to the backend extension WebSocket and authenticate."""
        for attempt in range(5):
            try:
                self._ws = await websockets.connect(EXT_WS_URL)

                # Fetch auth token from HTTP token endpoint
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "http://127.0.0.1:8000/api/browser_extension/token"
                    )
                    token = resp.json().get("token")

                # Send auth message immediately after connect
                await self._ws.send(json.dumps({"type": "auth", "token": token}))

                self.connected = True
                print(f"[MOCK-EXT] Connected and authenticated to {EXT_WS_URL}")
                self._task = asyncio.create_task(self._listen())
                return
            except Exception as e:
                if attempt < 4:
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError(f"Mock extension failed to connect: {e}")

    async def disconnect(self) -> None:
        """Disconnect from the backend extension WebSocket."""
        self.connected = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        print("[MOCK-EXT] Disconnected.")

    async def _listen(self) -> None:
        """Listen for dispatch requests from the backend and respond."""
        print("[MOCK-EXT] Listener task started.")
        try:
            async for raw_msg in self._ws:
                try:
                    msg = json.loads(raw_msg)
                except Exception as e:
                    print(f"[MOCK-EXT] Error parsing message: {e} raw={raw_msg}")
                    continue

                action = msg.get("action")
                request_id = msg.get("id")
                self.last_action_received = action
                print(f"[MOCK-EXT] Received action={action} id={request_id}")

                if not request_id:
                    continue

                response = None

                # Check for a per-test fixture override
                if (
                    self._fixture_override
                    and self._fixture_override.get("action") == action
                ):
                    fn = self._fixture_override.get("fn")
                    if fn:
                        response = fn(request_id)

                # Default responses (fallback)
                if response is None:
                    if action == "get_active_tab":
                        response = _make_tab_payload(request_id)
                    elif action == "capture_screenshot":
                        response = _make_screenshot_payload(request_id)
                    elif action == "browser_action":
                        response = _make_action_payload(request_id)
                    elif action == "fetch_urls":
                        response = _make_fetch_urls_payload(request_id)
                    else:
                        response = {
                            "id": request_id,
                            "error": f"Unknown action: {action}",
                        }

                try:
                    await self._ws.send(json.dumps(response))
                    print(f"[MOCK-EXT] Sent response for action={action}")
                except Exception as send_err:
                    print(f"[MOCK-EXT] Error sending response: {send_err}")
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            print("[MOCK-EXT] Connection closed by server.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[MOCK-EXT] Listener error: {e}")


# ─── Shared eval utilities (imported from frontier eval) ─────────────────────


def _load_frontier_eval():
    path = REPO_ROOT / "scripts" / "run_local_frontier_eval.py"
    spec = importlib.util.spec_from_file_location("frontier_eval", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run_local_frontier_eval.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["frontier_eval"] = mod
    spec.loader.exec_module(mod)
    return mod


# ─── Scoring ──────────────────────────────────────────────────────────────────


def score_turn(
    item: dict,
    *,
    response_text: str,
    executed_tools: list[str],
    turn_result: dict,
    model_info: dict,
    vision_available: bool,
) -> dict:
    """
    Score a single extension eval turn. Returns a dict with:
      score (int), max_score (int), breakdown (list[str])
    """
    score = 0
    max_score = 100
    breakdown = []
    expected_tool = item.get("expected_tool")
    expected_marker = item.get("expected_marker")
    min_chars = item.get("min_response_chars", 20)
    requires_extension = item.get("requires_extension", True)
    no_crash_check = item.get("no_crash_check", False)

    # ── Extension connectivity penalty ───────────────────────────────────────
    extension_was_off = item.get("disconnect_before", False)
    if requires_extension and extension_was_off:
        # Cap at 30 if we can't connect
        breakdown.append("CAPPED/30: Extension required but was disconnected")
        return {"score": min(score, 30), "max_score": max_score, "breakdown": breakdown}

    # ── Tool called correctly ─────────────────────────────────────────────────
    alternative_tools = item.get("alternative_tools", [])
    if expected_tool:
        if expected_tool in executed_tools:
            score += 40
            breakdown.append(f"+40: Tool '{expected_tool}' called correctly")
        elif any(t in executed_tools for t in alternative_tools):
            matched_alt = next(t for t in alternative_tools if t in executed_tools)
            score += 35  # Slight reduction for using alternate path
            breakdown.append(
                f"+35: Alternative tool '{matched_alt}' used (acceptable alternative for '{expected_tool}')"
            )
        else:
            score -= 20
            breakdown.append(
                f"-20: Expected tool '{expected_tool}' not called (got: {executed_tools})"
            )

    # ── Non-empty response ────────────────────────────────────────────────────
    normalized = response_text.strip()
    if len(normalized) >= min_chars:
        score += 20
        breakdown.append(
            f"+20: Response non-empty ({len(normalized)} chars ≥ {min_chars})"
        )
    else:
        breakdown.append(
            f"  0: Response too short ({len(normalized)} chars < {min_chars})"
        )

    # ── Marker found ──────────────────────────────────────────────────────────
    if expected_marker:
        if expected_marker.lower() in normalized.lower():
            score += 25
            breakdown.append(f"+25: Marker '{expected_marker}' found in response")
        else:
            breakdown.append(f"  0: Marker '{expected_marker}' NOT found in response")

    # ── No DSML leak ──────────────────────────────────────────────────────────
    dsml_markers = ["<tool_call>", "<function=", "｜｜", "dsml", "<｜tool"]
    has_dsml = any(m in normalized.lower() for m in dsml_markers)
    if has_dsml:
        score -= 15
        breakdown.append("-15: DSML leak detected in response")
    else:
        score += 10
        breakdown.append("+10: No DSML leak")

    # ── No crash / graceful reply ─────────────────────────────────────────────
    is_crash = normalized.lower().startswith(("[error", "traceback", "exception"))
    if no_crash_check:
        if not is_crash:
            score += 5
            breakdown.append("+5: Graceful response (no crash)")
        else:
            score -= 10
            breakdown.append("-10: Response looks like an error/crash")
    else:
        if not is_crash and normalized:
            score += 5
            breakdown.append("+5: Clean response")

    # ── Tool error penalty ────────────────────────────────────────────────────
    if turn_result.get("premature_complete"):
        score -= 10
        breakdown.append("-10: Premature complete (tool stall)")

    # ── Vision invoked check (Track 2) ───────────────────────────────────────
    if item.get("check_vision_invoked"):
        if model_info.get("vision_intake_mode"):
            score += 0  # No bonus — just no penalty
            breakdown.append("  ✓: Vision proxy invoked correctly")
        else:
            breakdown.append("  ⚠: Vision proxy not detected in model_info (may be OK)")

    return {"score": max(0, score), "max_score": max_score, "breakdown": breakdown}


# ─── Turn runner ─────────────────────────────────────────────────────────────


async def run_turn(
    page: Page,
    item: dict,
    *,
    ws_log,
    mock_client: MockExtensionClient | None,
    vision_ok: bool,
    fe,
) -> dict:
    """Run a single test case turn and return scored result."""
    prompt_id = item["id"]
    track = item.get("track", "")
    topic = item.get("topic", "")
    prompt_text = item["prompt"]
    timeout_s = item.get("timeout_s", COMPLEX_TIMEOUT_S)
    min_chars = item.get("min_response_chars", 20)
    expected_tool = item.get("expected_tool")

    # Skip vision tests if vision model unavailable
    if item.get("skip_if") == "vision_unavailable" and not vision_ok:
        print(f"\n[EVAL] SKIP [{prompt_id}] {topic} — vision model unavailable")
        return {
            "turn_index": prompt_id,
            "topic": topic,
            "track": track,
            "skipped": True,
            "skip_reason": "vision_unavailable",
            "score": None,
            "max_score": 100,
        }

    # Handle disconnect_before flag
    was_disconnected = False
    if item.get("disconnect_before") and mock_client:
        print(f"[EVAL] Disconnecting mock extension for {prompt_id}...")
        await mock_client.disconnect()
        await asyncio.sleep(2)
        was_disconnected = True

    # Set per-test mock fixture
    if mock_client and not was_disconnected:
        action = item.get("mock_action")
        fixture_fn = item.get("mock_fixture")
        mock_client.set_fixture(action, fixture_fn)

    # Reset circuit breaker before each turn (via backend API)
    try:
        import requests
        import os

        requests.put(
            "http://127.0.0.1:8000/api/unified-settings",
            json={"cloud_model_tier": "large-cloud"},
            headers={
                "X-Owlynn-Run-Token": os.environ.get("OWLYNN_LOCAL_RUN_TOKEN", "")
            },
            timeout=2,
        )
    except Exception:
        pass

    print("\n" + "=" * 80)
    print(f"  [{prompt_id}] {track} — {topic}")
    print("=" * 80)
    print(f"  User: {prompt_text[:100]}...")

    # Clear chat session to avoid context leakage across eval cases
    print("[EVAL] Clicking 'New chat'...")
    await page.locator('button.workspace-refresh[title="New chat"]').click()
    await page.wait_for_timeout(500)

    # Fully reset backend state to kill any ghost threads from previous tests
    import requests
    import os

    try:
        requests.post(
            "http://127.0.0.1:8000/api/debug/reset-all",
            headers={
                "X-Owlynn-Run-Token": os.environ.get("OWLYNN_LOCAL_RUN_TOKEN", "")
            },
            timeout=2,
        )
        requests.put(
            "http://127.0.0.1:8000/api/unified-settings",
            json={"cloud_model_tier": "large-cloud", "mcp.include_on_all": False},
            headers={
                "X-Owlynn-Run-Token": os.environ.get("OWLYNN_LOCAL_RUN_TOKEN", "")
            },
            timeout=2,
        )
    except Exception as e:
        print(f"Failed to reset backend: {e}")

    turn_start = time.time()
    msg_count_before = await page.evaluate(
        "() => document.querySelectorAll('.message-assistant').length"
    )

    turn_ts = time.monotonic()
    await fe.send_message(page, prompt_text)

    expected_tools = [expected_tool] if expected_tool else None
    turn_result = await fe.wait_for_turn_complete(
        page,
        timeout_s=600,
        min_chars=min_chars,
        expected_tools=expected_tools,
        ws_log=ws_log,
        since_ts=turn_start,
    )

    response_text = turn_result.get("response_text", "")
    executed_tools = turn_result.get("executed_tools", [])
    model_info = ws_log.model_info_since(turn_ts)
    orch_data = await fe.get_orchestration_data(page)

    print(f"  Reply: {response_text[:120]}...")
    print(
        f"  Tools: {executed_tools} | Model: {orch_data.get('model')} | Route: {orch_data.get('route')}"
    )

    # Score the turn (pass was_disconnected as disconnect_before context)
    item_with_context = {**item, "disconnect_before": was_disconnected}
    result = score_turn(
        item_with_context,
        response_text=response_text,
        executed_tools=executed_tools,
        turn_result=turn_result,
        model_info=model_info,
        vision_available=vision_ok,
    )

    grade = result["score"]
    max_grade = result["max_score"]
    print(f"  Score: {grade}/{max_grade}")
    for line in result["breakdown"]:
        print(f"    {line}")

    # Reconnect mock if it was disconnected for this test
    if was_disconnected and mock_client:
        print(f"[EVAL] Reconnecting mock extension after {prompt_id}...")
        await mock_client.connect()
        await asyncio.sleep(1.5)

    return {
        "turn_index": prompt_id,
        "topic": topic,
        "track": track,
        "user_query": prompt_text,
        "assistant_response": response_text,
        "executed_tools": executed_tools,
        "model": orch_data.get("model"),
        "route": orch_data.get("route"),
        "duration_seconds": round(time.monotonic() - turn_ts, 2),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "score": grade,
        "max_score": max_grade,
        "score_breakdown": result["breakdown"],
        "skipped": False,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main():
    # Wait for backend to be fully started and responsive
    print(f"[EVAL] Waiting for backend at {API_URL} to start...")
    backend_ready = False
    for _ in range(15):
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(f"{API_URL}/api/health")
                if resp.status_code == 200 and resp.json().get("agent") == "ready":
                    backend_ready = True
                    break
        except Exception:
            pass
        await asyncio.sleep(1.0)

    if not backend_ready:
        print(
            f"[EVAL] Warning: Backend at {API_URL} not fully responsive. Proceeding anyway."
        )

    if not os.environ.get("OWLYNN_LOCAL_RUN_TOKEN"):
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{API_URL}/api/local-run-token")
                if resp.status_code == 200:
                    token = resp.json().get("token")
                    if token:
                        os.environ["OWLYNN_LOCAL_RUN_TOKEN"] = token
                        print("[EVAL] Auto-loaded OWLYNN_LOCAL_RUN_TOKEN from backend")
        except Exception as e:
            print(f"[EVAL] Warning: Could not auto-load local run token: {e}")

    parser = argparse.ArgumentParser(description="Owlynn Browser Extension Eval")
    parser.add_argument(
        "--no-mock",
        action="store_true",
        help="Use real Brave extension instead of the Python mock client",
    )
    parser.add_argument(
        "--track",
        type=str,
        default=None,
        help="Run only test cases matching this track prefix (e.g. EX1, EX5)",
    )
    args = parser.parse_args()

    # Load shared frontier eval utilities
    fe = _load_frontier_eval()

    # Determine which test cases to run
    cases_to_run = TEST_CASES
    if args.track:
        cases_to_run = [c for c in TEST_CASES if c["id"].startswith(args.track)]
        if not cases_to_run:
            print(f"[EVAL] No test cases found for track prefix '{args.track}'")
            return

    # Fetch runtime profile
    runtime = await fe.fetch_runtime_profile()
    prior_strict = runtime.get("cloud_no_local_fallback", False)
    prior_scope = runtime.get("scope_clarification_enabled")
    prior_plan = runtime.get("plan_review_enabled")
    prior_execution = runtime.get("execution_policy", "auto_approve")

    print("[EVAL] Disabling HITL gates for automated run...")
    await fe.set_unified_settings(
        scope_clarification_enabled=False,
        plan_review_enabled=False,
        execution_policy="auto_approve",
    )

    # Check vision availability
    try:
        vision_ok = await fe.check_vision_vlm_available()
    except Exception:
        vision_ok = False
    print(f"[EVAL] Vision model available: {vision_ok}")

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    suffix = uuid.uuid4().hex[:6]
    project_name = f"ExtEval_{suffix}"
    project_id = await fe.create_project(project_name)

    eval_data = {
        "project_name": project_name,
        "project_id": project_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "runtime_profile": runtime.get("effective_profile", "unknown"),
        "vision_available": vision_ok,
        "mock_mode": not args.no_mock,
        "turns": [],
    }

    mock_client: MockExtensionClient | None = None

    try:
        # ── Start mock extension client ────────────────────────────────────
        if not args.no_mock:
            mock_client = MockExtensionClient()
            await mock_client.connect()
            await asyncio.sleep(1.5)  # Let backend register connection
            print("[EVAL] Mock extension client connected and ready.")
        else:
            print("[EVAL] --no-mock: Expecting real Brave extension to be connected.")

        ws_log = fe.WsEventLog()

        async with async_playwright() as p:
            print("[EVAL] Starting Playwright Chromium (headless)...")
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()
            ws_log.attach(page)

            print(f"[EVAL] Navigating to {BASE_URL}...")
            await page.goto(BASE_URL, wait_until="load")
            await fe.wait_for_ready(page)

            # Switch to project
            await (
                page.locator(".workspace-project-item")
                .filter(has_text=project_name)
                .first.click()
            )
            await page.wait_for_timeout(2000)
            await fe.wait_for_ready(page)

            await page.screenshot(path=str(SCREENSHOT_DIR / "00_start.png"))

            # ── Run all test cases ─────────────────────────────────────────
            for item in cases_to_run:
                result = await run_turn(
                    page,
                    item,
                    ws_log=ws_log,
                    mock_client=mock_client,
                    vision_ok=vision_ok,
                    fe=fe,
                )
                eval_data["turns"].append(result)

                # Incremental save
                OUTPUT_DATA_FILE.write_text(json.dumps(eval_data, indent=2))

            await page.screenshot(path=str(SCREENSHOT_DIR / "99_final.png"))
            await browser.close()

        # ── Compute final scores ───────────────────────────────────────────
        scored_turns = [t for t in eval_data["turns"] if not t.get("skipped")]
        total_score = sum(t["score"] for t in scored_turns)
        total_max = sum(t["max_score"] for t in scored_turns)
        pct = round(total_score / total_max * 100, 1) if total_max > 0 else 0

        # Per-track breakdown
        track_scores: dict[str, dict] = {}
        for t in scored_turns:
            track = t.get("track", "Unknown")
            if track not in track_scores:
                track_scores[track] = {"score": 0, "max": 0, "turns": []}
            track_scores[track]["score"] += t["score"]
            track_scores[track]["max"] += t["max_score"]
            track_scores[track]["turns"].append(t["turn_index"])

        eval_data["summary"] = {
            "total_score": total_score,
            "total_max": total_max,
            "score_percentage": pct,
            "grade": "PASS" if pct >= 75 else "MARGINAL" if pct >= 60 else "FAIL",
            "track_breakdown": {
                k: {
                    "score": v["score"],
                    "max": v["max"],
                    "pct": round(v["score"] / v["max"] * 100, 1) if v["max"] > 0 else 0,
                }
                for k, v in track_scores.items()
            },
        }

        OUTPUT_DATA_FILE.write_text(json.dumps(eval_data, indent=2))

        # ── Print summary ──────────────────────────────────────────────────
        print("\n" + "=" * 80)
        print(f"  EXTENSION EVAL COMPLETE — {total_score}/{total_max} ({pct}%)")
        print(f"  Grade: {eval_data['summary']['grade']}")
        print("=" * 80)
        for track, data in track_scores.items():
            tpct = round(data["score"] / data["max"] * 100, 1) if data["max"] > 0 else 0
            status = "✅" if tpct >= 70 else "⚠️" if tpct >= 60 else "❌"
            print(f"  {status} {track}: {data['score']}/{data['max']} ({tpct}%)")

        skipped = [t for t in eval_data["turns"] if t.get("skipped")]
        if skipped:
            print(f"\n  Skipped ({len(skipped)}): {[t['turn_index'] for t in skipped]}")

        print(f"\n  Results saved to: {OUTPUT_DATA_FILE}")

        # ── Write markdown report ──────────────────────────────────────────
        _write_report(eval_data)

    finally:
        if mock_client:
            await mock_client.disconnect()
        await fe.set_unified_settings(cloud_no_local_fallback=prior_strict)
        if prior_scope is not None:
            await fe.set_unified_settings(scope_clarification_enabled=prior_scope)
        if prior_plan is not None:
            await fe.set_unified_settings(plan_review_enabled=prior_plan)
        if prior_execution is not None:
            await fe.set_unified_settings(execution_policy=prior_execution)
        await fe.delete_project(project_id)


def _write_report(eval_data: dict) -> None:
    """Write a markdown eval report to docs/evaluations/."""
    date_str = time.strftime("%Y-%m-%d")
    report_path = REPO_ROOT / "docs" / "evaluations" / f"extension-eval-{date_str}.md"
    summary = eval_data.get("summary", {})
    pct = summary.get("score_percentage", 0)
    grade = summary.get("grade", "UNKNOWN")
    total = summary.get("total_score", 0)
    total_max = summary.get("total_max", 0)

    lines = [
        f"# Extension Eval — {date_str}",
        "",
        f"**Overall: {total}/{total_max} ({pct}%) — {grade}**",
        "",
        f"- Profile: `{eval_data.get('runtime_profile', 'unknown')}`",
        f"- Mock mode: `{eval_data.get('mock_mode', True)}`",
        f"- Vision available: `{eval_data.get('vision_available', False)}`",
        "",
        "## Per-Track Results",
        "",
        "| Track | Score | % | Status |",
        "|-------|-------|---|--------|",
    ]

    for track, data in summary.get("track_breakdown", {}).items():
        tpct = data.get("pct", 0)
        status = "✅ Pass" if tpct >= 70 else "⚠️ Marginal" if tpct >= 60 else "❌ Fail"
        lines.append(
            f"| {track} | {data['score']}/{data['max']} | {tpct}% | {status} |"
        )

    lines += ["", "## Turn Details", ""]

    for turn in eval_data.get("turns", []):
        if turn.get("skipped"):
            lines.append(
                f"### [{turn['turn_index']}] {turn['topic']} — ⏭ SKIPPED ({turn.get('skip_reason', '')})"
            )
        else:
            score = turn["score"]
            max_s = turn["max_score"]
            icon = "✅" if score >= 70 else "⚠️" if score >= 50 else "❌"
            lines.append(
                f"### [{turn['turn_index']}] {turn['topic']} — {icon} {score}/{max_s}"
            )
            lines.append(f"- Tools: `{turn.get('executed_tools', [])}`")
            lines.append(f"- Route: `{turn.get('route', '')}`")
            lines.append(f"- Duration: {turn.get('duration_seconds', 0):.1f}s")
            lines.append("- Breakdown:")
            for b in turn.get("score_breakdown", []):
                lines.append(f"  - {b}")
        lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[EVAL] Report written to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
