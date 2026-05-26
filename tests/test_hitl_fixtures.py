"""Tests for HITL fixtures loading and serialization."""

import json
from pathlib import Path
import pytest


class TestHitlFixtures:
    def test_all_fixtures_are_valid_json(self):
        fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "hitl"
        for fixture_file in sorted(fixtures_dir.glob("*.json")):
            if fixture_file.name == "__init__.py":
                continue
            data = json.loads(fixture_file.read_text())
            assert "type" in data, f"{fixture_file.name} missing 'type' field"

    def test_router_fixtures(self):
        from src.hitl.fixtures import load_fixture
        fix = load_fixture("router_skill_ambiguity")
        assert fix["type"] == "ask_user"
        assert len(fix["choices"]) >= 2

        fix2 = load_fixture("router_low_confidence")
        assert fix2["type"] == "ask_user"

    def test_security_fixture(self):
        from src.hitl.fixtures import load_fixture
        fix = load_fixture("security_delete_file")
        assert fix["type"] == "security_approval_required"
        assert "sensitive_tool_calls" in fix
        assert len(fix["sensitive_tool_calls"]) == 1

    def test_plan_review_fixture(self):
        from src.hitl.fixtures import load_fixture
        fix = load_fixture("plan_review_write_file")
        assert fix["type"] == "plan_review_required"
        assert "planned_actions" in fix
        assert "pitfalls" in fix

    def test_scope_clarification_fixture(self):
        from src.hitl.fixtures import load_fixture
        fix = load_fixture("scope_clarification_calculator")
        assert fix["type"] == "scope_clarification_required"
        assert len(fix["questions"]) == 3

    def test_ask_user_fixture(self):
        from src.hitl.fixtures import load_fixture
        fix = load_fixture("ask_user_mid_task")
        assert fix["type"] == "ask_user"
        assert len(fix["choices"]) == 3


class TestFixturesRoundTrip:
    def test_fixture_serializable(self):
        """All fixtures should be JSON-serializable."""
        from src.hitl.fixtures import load_fixture, list_fixtures
        for name in list_fixtures():
            fixture = load_fixture(name)
            # Should not raise
            serialized = json.dumps(fixture)
            assert isinstance(serialized, str)
            roundtripped = json.loads(serialized)
            assert roundtripped == fixture
