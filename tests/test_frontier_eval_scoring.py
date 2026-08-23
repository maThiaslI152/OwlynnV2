"""Scoring-only strict cloud eval: cloud-failure badges fail cloud-intended turns."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_local_frontier_eval import (
    CLOUD_FAILURE_BADGES,
    WsEventLog,
    expected_tools_satisfied,
    merge_executed_tools,
    score_exchange,
    should_exit_idle_tool_stall,
)


def test_ws_assistant_text_since_prefers_latest():
    log = WsEventLog()
    t0 = 1000.0
    log.events = [
        {
            "type": "assistant.message",
            "ts": t0 + 1,
            "payload": {"message": {"content": "first reply"}},
        },
        {
            "type": "assistant.message",
            "ts": t0 + 5,
            "payload": {"message": {"content": "second reply"}},
        },
    ]
    assert log.assistant_text_since(t0) == "second reply"
    assert log.assistant_message_seen_since(t0 + 3)


def test_cloud_fallback_badges_fail_complex_cloud():
    """Verify eval scoring detects cloud fallback badges."""
    exchange = {
        "route": "complex-cloud",
        "model_badge": "large-cloud-failed",
        "assistant_response_full": "x" * 20,
        "executed_tools": [],
    }
    expected = {"expected_route": "complex", "expected_tools": []}
    scores = score_exchange(exchange, expected, profile="cloud")
    assert scores.get("cloud_fallback_fail")


def test_large_cloud_failed_badge_fails_complex():
    exchange = {
        "route": "complex-cloud",
        "model_badge": "large-cloud-failed",
        "assistant_response_full": "Cloud compute failed",
        "executed_tools": [],
    }
    expected = {"expected_route": "complex"}
    scores = score_exchange(exchange, expected, profile="cloud")
    assert scores["cloud_fallback_fail"]
    assert scores["grade"] <= 49


def test_simple_route_small_local_not_regression():
    exchange = {
        "route": "simple",
        "model_badge": "small-local",
        "assistant_response_full": "hi there",
        "executed_tools": [],
    }
    expected = {"expected_route": "simple"}
    scores = score_exchange(exchange, expected, profile="cloud")
    assert not scores.get("cloud_fallback_fail")


def test_score_exchange_caps_grade_on_cloud_fallback():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_local_frontier_eval import score_exchange

    exchange = {
        "route": "complex-cloud",
        "model_badge": "large-cloud-failed",
        "assistant_response_full": "a" * 50,
        "executed_tools": ["web_search"],
    }
    expected = {"expected_route": "complex", "expected_tools": ["web_search"]}
    scores = score_exchange(exchange, expected, profile="cloud")
    assert scores["cloud_regression"]
    assert scores["cloud_fallback_fail"]
    assert scores["grade"] <= 49


def test_merge_executed_tools_prefers_ws():
    assert merge_executed_tools(["web_search", "write_workspace_file"], []) == [
        "web_search",
        "write_workspace_file",
    ]
    assert merge_executed_tools([], ["read_workspace_file"]) == ["read_workspace_file"]


def test_expected_tools_satisfied():
    assert expected_tools_satisfied(
        ["web_search", "write_workspace_file"], ["web_search", "write_workspace_file"]
    )
    assert not expected_tools_satisfied(
        ["web_search"], ["web_search", "write_workspace_file"]
    )
    assert expected_tools_satisfied([], None)
    assert expected_tools_satisfied([], [])


def test_ws_running_tools_since():
    log = WsEventLog()
    base = 1000.0
    log.events = [
        {
            "type": "tool_execution",
            "ts": base + 1,
            "payload": {"tool_name": "web_search", "status": "running"},
        },
        {
            "type": "tool_execution",
            "ts": base + 2,
            "payload": {"tool_name": "web_search", "status": "success"},
        },
        {
            "type": "tool_execution",
            "ts": base + 3,
            "payload": {"tool_name": "write_workspace_file", "status": "running"},
        },
    ]
    assert log.running_tools_since(base) == ["write_workspace_file"]
    assert log.tools_since(base) == ["web_search", "write_workspace_file"]


def test_should_exit_idle_tool_stall():
    assert should_exit_idle_tool_stall(
        tools_ok=False,
        expected_tools=["read_workspace_file"],
        normalized_len=100,
        min_chars=40,
        dsml=False,
        running_tools=[],
        stall_polls=8,
    )
    assert not should_exit_idle_tool_stall(
        tools_ok=False,
        expected_tools=["read_workspace_file"],
        normalized_len=100,
        min_chars=40,
        dsml=False,
        running_tools=[],
        stall_polls=3,
    )
    assert not should_exit_idle_tool_stall(
        tools_ok=False,
        expected_tools=["read_workspace_file"],
        normalized_len=10,
        min_chars=40,
        dsml=False,
        running_tools=[],
        stall_polls=8,
    )


def test_vision_ocr_fail_caps_grade():
    exchange = {
        "route": "complex-cloud",
        "model_badge": "large-cloud",
        "task_category": "vision_cloud",
        "has_images": True,
        "vision_intake_mode": "proxy",
        "assistant_response_full": "Cloud model failed",
        "executed_tools": [],
    }
    expected = {
        "expected_route": "complex",
        "expected_vision": True,
        "expected_marker": "EVAL_OCR_MARKER",
    }
    scores = score_exchange(exchange, expected, profile="cloud")
    assert scores.get("vision_match")
    assert not scores.get("vision_ocr_ok", True)
    assert scores["grade"] <= 60
