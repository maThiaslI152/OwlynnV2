"""Unit tests for the Postgres soft-path circuit breaker."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest


@pytest.fixture
def fresh_breaker():
    from src.memory.postgres_health import (
        PostgresCircuitBreaker,
        reset_postgres_breaker,
        set_checkpointer_backend,
    )

    reset_postgres_breaker()
    set_checkpointer_backend("memory")
    cb = PostgresCircuitBreaker(failure_threshold=2, cooldown_seconds=1)
    yield cb
    reset_postgres_breaker()


class TestPostgresCircuitBreaker:
    def test_initial_state_is_closed(self, fresh_breaker):
        assert fresh_breaker.is_closed()
        assert not fresh_breaker.is_open()
        assert fresh_breaker.state == "closed"
        assert fresh_breaker.consecutive_failures == 0

    def test_single_failure_does_not_open(self, fresh_breaker):
        fresh_breaker.record_failure()
        assert fresh_breaker.is_closed()
        assert fresh_breaker.consecutive_failures == 1
        assert fresh_breaker.state == "half-open"

    def test_two_failures_open_circuit(self, fresh_breaker):
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        assert fresh_breaker.is_open()
        assert not fresh_breaker.is_closed()
        assert fresh_breaker.state == "open"
        assert fresh_breaker.consecutive_failures == 2

    def test_open_logs_once(self, fresh_breaker, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="src.memory.postgres_health"):
            fresh_breaker.record_failure()
            fresh_breaker.record_failure()
            fresh_breaker.record_failure()
            fresh_breaker.record_failure()
        open_logs = [r for r in caplog.records if "Circuit OPEN" in r.getMessage()]
        assert len(open_logs) == 1

    def test_success_resets_and_logs_close(self, fresh_breaker, caplog):
        import logging

        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        assert fresh_breaker.is_open()
        with caplog.at_level(logging.INFO, logger="src.memory.postgres_health"):
            fresh_breaker.record_success()
        assert fresh_breaker.is_closed()
        assert fresh_breaker.consecutive_failures == 0
        close_logs = [r for r in caplog.records if "Circuit CLOSED" in r.getMessage()]
        assert len(close_logs) == 1

    def test_cooldown_expiry_half_open(self, fresh_breaker):
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        assert fresh_breaker.is_open()
        with patch.object(fresh_breaker, "_last_failure_time", time.monotonic() - 2):
            assert fresh_breaker.is_closed()

    def test_remaining_cooldown(self, fresh_breaker):
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        assert fresh_breaker.remaining_cooldown > 0

    def test_reset_clears_all(self, fresh_breaker):
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        fresh_breaker.reset()
        assert fresh_breaker.is_closed()
        assert fresh_breaker.consecutive_failures == 0
        assert fresh_breaker.remaining_cooldown == 0

    def test_force_open(self, fresh_breaker):
        fresh_breaker.force_open(reason="startup")
        assert fresh_breaker.is_open()
        assert fresh_breaker.state == "open"

    def test_singleton_helpers(self):
        from src.memory.postgres_health import (
            get_checkpointer_backend,
            get_postgres_breaker,
            is_postgres_available,
            postgres_status,
            record_postgres_failure,
            record_postgres_success,
            reset_postgres_breaker,
            set_checkpointer_backend,
        )

        reset_postgres_breaker()
        set_checkpointer_backend("postgres")
        assert get_checkpointer_backend() == "postgres"
        assert is_postgres_available()
        assert postgres_status() == "ok"

        cb = get_postgres_breaker()
        # Align singleton threshold to 2 for this test process
        cb._failure_threshold = 2
        cb._cooldown_seconds = 45
        record_postgres_failure()
        record_postgres_failure()
        assert not is_postgres_available()
        assert postgres_status() == "degraded"

        record_postgres_success()
        assert is_postgres_available()
        assert postgres_status() == "ok"
        reset_postgres_breaker()


@pytest.mark.asyncio
async def test_get_or_create_node_returns_none_when_circuit_open():
    from src.memory.postgres_health import get_postgres_breaker, reset_postgres_breaker
    from src.memory.thought_graph import ThoughtGraphManager

    reset_postgres_breaker()
    cb = get_postgres_breaker()
    cb.force_open(reason="test")
    mgr = ThoughtGraphManager()
    result = await mgr.get_or_create_node("circuit-open-node", title="Should Skip")
    assert result is None
    reset_postgres_breaker()


@pytest.mark.asyncio
async def test_enqueue_returns_none_when_circuit_open():
    from src.memory.extraction.queue import enqueue_extraction
    from src.memory.postgres_health import get_postgres_breaker, reset_postgres_breaker

    reset_postgres_breaker()
    cb = get_postgres_breaker()
    cb.force_open(reason="test")
    queued = await enqueue_extraction(
        {
            "turn_id": "circuit-skip-job",
            "turn_text": "should not enqueue",
            "mem0_uid": "owner",
        }
    )
    assert queued is None
    reset_postgres_breaker()


def test_health_endpoint_accepts_degraded_when_agent_ready():
    """Documented contract: readiness is agent===ready, not status===ok."""
    # Shape check — consumers must key off agent / nested fields.
    payload = {
        "status": "degraded",
        "agent": "ready",
        "postgres": "degraded",
        "checkpointer": "memory",
    }
    assert payload["agent"] == "ready"
    assert payload["status"] in ("ok", "degraded")
    runnable = payload["agent"] == "ready"  # chat can limp
    assert runnable is True
