"""
Tests for the structured audit logging system.

Covers:
- audit_event emission with channel/event/data
- Channel filtering and level gating
- Context enrichment via contextvars
- Convenience functions (audit_debug, audit_info, etc.)
- @log_node decorator (sync and async)
- log_model_attempt and log_hitl_event helpers
- Sanitization of values
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import pytest

os.environ["OWLYNN_AUDIT_LOG_ENABLED"] = "0"
os.environ.setdefault("OWLYNN_AUDIT_LOG_DIR", "")

from src.config.audit_log import (
    _DEFAULT_CHANNEL_LEVELS,
    CHANNELS,
    _channel_levels,
    audit_context,
    audit_debug,
    audit_event,
    audit_info,
    audit_warn,
    configure_audit_log,
    get_thread_id,
    set_model,
    set_node,
    set_route,
    set_thread_id,
)
from src.config.log_middleware import (
    log_hitl_event,
    log_model_attempt,
    log_node,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_context():
    """Reset all contextvars and channel levels between tests."""
    set_thread_id("")
    set_node("")
    set_route("")
    set_model("")
    # Reset channel levels to defaults after tests that modify them
    _channel_levels.clear()
    _channel_levels.update(_DEFAULT_CHANNEL_LEVELS)
    yield


@pytest.fixture
def captured_audit(caplog):
    """Capture audit log output via caplog and return parsed entries."""
    caplog.set_level(logging.DEBUG, logger="audit")

    def _entries():
        entries = []
        for record in caplog.records:
            if record.name == "audit":
                try:
                    entries.append(json.loads(record.message))
                except json.JSONDecodeError:
                    pass
        return entries

    return _entries


# ── Tests: audit_event ──────────────────────────────────────────────────────


class TestAuditEvent:
    def test_basic_emission(self, captured_audit):
        audit_event("system", "startup", level=logging.INFO)
        entries = captured_audit()
        assert len(entries) == 1
        e = entries[0]
        assert e["channel"] == "system"
        assert e["event"] == "startup"
        assert "ts" in e

    def test_unknown_channel_is_dropped(self, captured_audit):
        audit_event("unknown.channel", "test", level=logging.INFO)
        entries = captured_audit()
        assert len(entries) == 0

    def test_level_gating_drops_below_threshold(self, captured_audit):
        # Set agent.model channel to WARNING
        configure_audit_log(channel_levels={"agent.model": "WARNING"}, enabled=False)
        audit_event("agent.model", "pool_cache_hit", level=logging.DEBUG)
        audit_event("agent.model", "swap_complete", level=logging.INFO)
        entries = captured_audit()
        assert len(entries) == 0  # Both below WARNING

    def test_level_gating_passes_warning(self, captured_audit):
        configure_audit_log(channel_levels={"agent.model": "WARNING"}, enabled=False)
        audit_event("agent.model", "swap_load_failed", level=logging.WARNING)
        entries = captured_audit()
        assert len(entries) == 1

    def test_extra_data_included(self, captured_audit):
        audit_event(
            "agent.tool",
            "tool_start",
            level=logging.INFO,
            tool="write_file",
            tool_call_id="call_xyz",
        )
        entries = captured_audit()
        assert len(entries) == 1
        e = entries[0]
        assert e["tool"] == "write_file"
        assert e["tool_call_id"] == "call_xyz"

    def test_thread_id_injection(self, captured_audit):
        set_thread_id("thread-123")
        audit_event("agent.lifecycle", "node_entry", level=logging.DEBUG)
        entries = captured_audit()
        assert entries[0]["thread_id"] == "thread-123"

    def test_node_injection(self, captured_audit):
        set_node("router")
        audit_event("agent.lifecycle", "node_entry", level=logging.DEBUG)
        entries = captured_audit()
        assert entries[0]["node"] == "router"

    def test_route_injection(self, captured_audit):
        set_route("complex-cloud")
        audit_event("agent.lifecycle", "node_entry", level=logging.DEBUG)
        entries = captured_audit()
        assert entries[0]["route"] == "complex-cloud"

    def test_model_injection(self, captured_audit):
        set_model("large-cloud")
        audit_event("agent.model", "model_selected", level=logging.INFO)
        entries = captured_audit()
        assert entries[0]["model"] == "large-cloud"


# ── Tests: context enrichment ───────────────────────────────────────────────


class TestAuditContext:
    def test_context_manager_injects_extras(self, captured_audit):
        with audit_context(session_id="sess-1", correlation_id="corr-2"):
            audit_event("agent.lifecycle", "node_entry", level=logging.DEBUG)
        entries = captured_audit()
        assert entries[0]["session_id"] == "sess-1"
        assert entries[0]["correlation_id"] == "corr-2"

    def test_context_manager_does_not_leak(self, captured_audit):
        with audit_context(session_id="sess-1"):
            pass
        audit_event("agent.lifecycle", "node_entry", level=logging.DEBUG)
        entries = captured_audit()
        assert "session_id" not in entries[0]

    def test_nested_context_merges(self, captured_audit):
        with audit_context(a=1), audit_context(b=2):
            audit_event("system", "test", level=logging.INFO)
        entries = captured_audit()
        assert entries[0].get("a") == 1
        assert entries[0].get("b") == 2


# ── Tests: convenience functions ────────────────────────────────────────────


class TestConvenienceFunctions:
    def test_audit_debug(self, captured_audit):
        audit_debug("memory.cache", "cache_hit", age_seconds=12)
        entries = captured_audit()
        assert entries[0]["event"] == "cache_hit"
        assert entries[0]["age_seconds"] == 12

    def test_audit_info(self, captured_audit):
        audit_info("api.ws", "ws_connected", thread_id="t1")
        entries = captured_audit()
        assert entries[0]["event"] == "ws_connected"

    def test_audit_warn(self, captured_audit):
        audit_warn("agent.model", "swap_load_failed", error="timeout")
        entries = captured_audit()
        assert entries[0]["event"] == "swap_load_failed"


# ── Tests: value sanitization ───────────────────────────────────────────────


class TestSanitization:
    def test_long_string_truncated(self, captured_audit):
        long_text = "x" * 600
        audit_info("system", "test", data=long_text)
        entries = captured_audit()
        assert len(entries[0]["data"]) <= 500 + 1  # 500 + "…"

    def test_list_truncated(self, captured_audit):
        long_list = list(range(50))
        audit_info("system", "test", items=long_list)
        entries = captured_audit()
        assert len(entries[0]["items"]) <= 20

    def test_dict_truncated(self, captured_audit):
        big_dict = {str(i): i for i in range(50)}
        audit_info("system", "test", mapping=big_dict)
        entries = captured_audit()
        assert len(entries[0]["mapping"]) <= 20


# ── Tests: @log_node decorator ──────────────────────────────────────────────


class TestLogNodeDecorator:
    def test_sync_wrapper(self, captured_audit):
        @log_node("test_sync")
        def my_node(state):
            return {"answer": 42}

        result = my_node({})
        assert result == {"answer": 42}
        entries = captured_audit()
        events = [e["event"] for e in entries]
        assert "node_entry" in events
        assert "node_exit" in events
        exit_entry = next(e for e in entries if e["event"] == "node_exit")
        assert "duration_ms" in exit_entry

    def test_async_wrapper(self, captured_audit):
        @log_node("test_async")
        async def my_node(state):
            return {"answer": 99}

        result = asyncio.run(my_node({}))
        assert result == {"answer": 99}
        entries = captured_audit()
        events = [e["event"] for e in entries]
        assert "node_entry" in events
        assert "node_exit" in events

    def test_error_logging(self, captured_audit):
        @log_node("test_error")
        def my_node(state):
            raise ValueError("boom")

        with pytest.raises(ValueError):
            my_node({})
        entries = captured_audit()
        events = [e["event"] for e in entries]
        assert "node_entry" in events
        assert "node_error" in events

    def test_preserves_name(self):
        @log_node("test")
        def my_node(state):
            pass

        assert my_node.__name__ == "my_node"

    def test_node_context_injected(self, captured_audit):
        @log_node("test_ctx")
        def my_node(state):
            audit_debug("agent.lifecycle", "inner_event")

        my_node({})
        entries = captured_audit()
        inner = next(e for e in entries if e["event"] == "inner_event")
        assert inner["node"] == "test_ctx"


# ── Tests: log_model_attempt ────────────────────────────────────────────────


class TestLogModelAttempt:
    def test_success(self, captured_audit):
        log_model_attempt(
            "large-cloud", "success", duration_ms=150, reason="initial_route"
        )
        entries = captured_audit()
        assert entries[0]["channel"] == "agent.model"
        assert entries[0]["event"] == "model_attempt"
        assert entries[0]["model"] == "large-cloud"
        assert entries[0]["status"] == "success"

    def test_failure(self, captured_audit):
        log_model_attempt("large-cloud", "failed", reason="auth_error_401_403")
        entries = captured_audit()
        assert entries[0]["status"] == "failed"


# ── Tests: log_hitl_event ───────────────────────────────────────────────────


class TestLogHitlEvent:
    def test_tool_classified(self, captured_audit):
        log_hitl_event(
            "tool_classified", tool="write_workspace_file", decision="sensitive"
        )
        entries = captured_audit()
        assert entries[0]["channel"] == "agent.hitl"
        assert entries[0]["event"] == "tool_classified"
        assert entries[0]["tool"] == "write_workspace_file"

    def test_hitl_approved(self, captured_audit):
        log_hitl_event(
            "hitl_approved",
            decision="approved",
            tools=["write_file"],
            sensitive_count=1,
        )
        entries = captured_audit()
        assert entries[0]["event"] == "hitl_approved"
        assert entries[0]["tools"] == ["write_file"]

    def test_hitl_denied(self, captured_audit):
        log_hitl_event(
            "hitl_denied", decision="denied", tools=["delete_file"], total_denied=1
        )
        entries = captured_audit()
        assert entries[0]["event"] == "hitl_denied"

    def test_plan_reviewed(self, captured_audit):
        log_hitl_event(
            "plan_reviewed",
            decision="approved",
            tools=["write_file"],
            pitfalls=["risk1"],
        )
        entries = captured_audit()
        assert entries[0]["event"] == "plan_reviewed"


# ── Tests: contextvar helpers ───────────────────────────────────────────────


class TestContextVars:
    def test_set_get_thread_id(self):
        set_thread_id("tid-42")
        assert get_thread_id() == "tid-42"

    def test_empty_default(self):
        set_thread_id("")
        assert get_thread_id() == ""


# ── Tests: CHANNELS ─────────────────────────────────────────────────────────


class TestChannels:
    def test_all_15_channels_present(self):
        assert len(CHANNELS) == 15
        assert "agent.lifecycle" in CHANNELS
        assert "memory.topics" in CHANNELS
        assert "system" in CHANNELS
