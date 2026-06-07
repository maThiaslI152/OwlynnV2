"""Tests for cloud_brief module."""

import pytest


class TestCloudBrief:
    def test_build_empty_brief(self):
        from src.agent.hitl.cloud_brief import build_cloud_brief

        brief = build_cloud_brief()
        assert brief == ""

    def test_build_brief_with_scope(self):
        from src.agent.hitl.cloud_brief import build_cloud_brief

        brief = build_cloud_brief(
            clarified_scope={
                "language": {"label": "Python"},
                "ui_surface": {"label": "CLI"},
            },
            last_user_message="Build a calculator app",
        )
        assert "Python" in brief
        assert "CLI" in brief
        assert "OWLYNN CLOUD BRIEF" in brief

    def test_build_brief_with_plan_review(self):
        from src.agent.hitl.cloud_brief import build_cloud_brief

        brief = build_cloud_brief(
            plan_review_summary={
                "approved": True,
                "stated_intent": "Write calculator script",
                "pitfalls": ["Memory risk"],
            },
            last_user_message="Write a calculator",
        )
        assert "Plan approved" in brief or "calculator" in brief.lower()

    def test_brief_token_estimation(self):
        from src.agent.hitl.cloud_brief import build_cloud_brief, estimate_brief_tokens

        brief = build_cloud_brief(last_user_message="Build a calculator")
        tokens = estimate_brief_tokens(brief)
        assert tokens > 0

    def test_brief_caps_size(self):
        from src.agent.hitl.cloud_brief import build_cloud_brief

        long_msg = "x" * 20000
        brief = build_cloud_brief(
            last_user_message=long_msg,
            max_chars=1000,
        )
        assert len(brief) <= 1003  # +3 for "..."

    def test_brief_preserves_user_task_after_assistant_turn(self):
        """Multi-turn: user task must not be replaced by prior assistant greeting."""
        from src.agent.hitl.cloud_brief import build_cloud_brief

        brief = build_cloud_brief(
            last_user_message="Compare REST vs GraphQL for a mobile backend",
            last_assistant_summary="Hi! I'm here to assist you. What would you like to discuss?",
        )
        assert "Compare REST vs GraphQL" in brief
        assert "Current user request:" in brief
        assert "Prior assistant context:" in brief
        # Task line must be the user question, not the greeting alone
        task_line = [
            ln for ln in brief.splitlines() if ln.startswith("Current user request:")
        ][0]
        assert "Compare REST" in task_line
        assert task_line.count("Hi!") == 0


class TestCloudBriefAnonymization:
    def test_memory_filter_strips_keys(self):
        from src.agent.hitl.cloud_brief import _filter_memory_context

        filtered = _filter_memory_context(
            "User has api_key=sk-abc123 and password=secret"
        )
        assert "sk-abc123" not in filtered
        assert "secret" not in filtered

    def test_scope_format_skipped(self):
        from src.agent.hitl.cloud_brief import _format_scope

        result = _format_scope({"skipped": True})
        assert "skipped" in result
