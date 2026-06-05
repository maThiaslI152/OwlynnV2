"""Integration tests for the cloud circuit breaker."""

import sys
from unittest.mock import MagicMock, patch

import pytest

sys.modules["mem0"] = MagicMock()


@pytest.fixture
def fresh_breaker():
    from src.agent.cloud_circuit_breaker import (
        CloudCircuitBreaker,
        reset_circuit_breaker,
    )

    reset_circuit_breaker()
    cb = CloudCircuitBreaker(failure_threshold=3, cooldown_seconds=1)
    yield cb


class TestCloudCircuitBreaker:
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

    def test_three_failures_open_circuit(self, fresh_breaker):
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        assert fresh_breaker.is_open()
        assert not fresh_breaker.is_closed()
        assert fresh_breaker.state == "open"
        assert fresh_breaker.consecutive_failures == 3

    def test_success_resets_circuit(self, fresh_breaker):
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        fresh_breaker.record_success()
        assert fresh_breaker.is_closed()
        assert fresh_breaker.consecutive_failures == 0

    def test_cooldown_expiry_half_open(self, fresh_breaker):
        import time

        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        assert fresh_breaker.is_open()
        # Fast-forward past cooldown by patching time
        with patch.object(fresh_breaker, "_last_failure_time", time.monotonic() - 2):
            assert fresh_breaker.is_closed()  # Half-open — allows trial

    def test_success_after_cooldown_closes(self, fresh_breaker):
        import time

        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        # Simulate cooldown expiry
        with patch.object(fresh_breaker, "_last_failure_time", time.monotonic() - 2):
            assert fresh_breaker.is_closed()
            fresh_breaker.record_success()
            assert fresh_breaker.consecutive_failures == 0

    def test_remaining_cooldown(self, fresh_breaker):
        import time

        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        assert fresh_breaker.remaining_cooldown > 0

    def test_reset_clears_all(self, fresh_breaker):
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        fresh_breaker.record_failure()
        fresh_breaker.reset()
        assert fresh_breaker.is_closed()
        assert fresh_breaker.consecutive_failures == 0
        assert fresh_breaker.remaining_cooldown == 0

    def test_singleton_is_shared(self):
        from src.agent.cloud_circuit_breaker import (
            get_circuit_breaker,
            reset_circuit_breaker,
        )

        reset_circuit_breaker()
        cb1 = get_circuit_breaker()
        cb2 = get_circuit_breaker()
        assert cb1 is cb2
