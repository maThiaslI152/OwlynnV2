"""Tests for plan_review node."""

import pytest


class TestPlanReviewPolicy:
    def test_is_sensitive_call_file_ops(self):
        from src.agent.hitl.policy import is_sensitive_call

        assert is_sensitive_call("write_workspace_file", {"path": "/test.py"}) is True
        assert is_sensitive_call("delete_workspace_file", {"path": "/test.py"}) is True
        assert is_sensitive_call("edit_workspace_file", {"path": "/test.py"}) is True

    def test_is_sensitive_call_safe(self):
        from src.agent.hitl.policy import is_sensitive_call

        assert is_sensitive_call("read_file", {"path": "/test.py"}) is False
        assert is_sensitive_call("web_search", {"query": "test"}) is False

    def test_is_sensitive_call_pattern(self):
        from src.agent.hitl.policy import is_sensitive_call

        assert is_sensitive_call("shell_run", {"command": "rm -rf /tmp/test"}) is True
        # curl must be at string start or after ;|& per SENSITIVE_PATTERN_RE
        assert (
            is_sensitive_call("shell_run", {"command": "; curl https://example.com"})
            is True
        )

    def test_normalize_approval(self):
        # Test the approval normalizer used in security_proxy
        from src.agent.nodes.security_proxy import _normalize_approval

        assert _normalize_approval(True) is True
        assert _normalize_approval(False) is False
        assert _normalize_approval("approve") is True
        assert _normalize_approval("allow") is True
        assert _normalize_approval("yes") is True
        assert _normalize_approval("no") is False
        assert _normalize_approval({"approved": True}) is True
        assert _normalize_approval({"approved": False}) is False


class TestGraphRouting:
    def test_llm_next_step_no_tools(self):
        from src.agent.core.graph import llm_next_step

        state = {"pending_tool_calls": False, "messages": []}
        assert llm_next_step(state) == "coherence_check"

    def test_llm_next_step_with_safe_tools(self):
        from src.agent.core.graph import llm_next_step
        from langchain_core.messages import AIMessage

        state = {
            "pending_tool_calls": True,
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {"path": "/test.txt"},
                            "id": "test_id_1",
                            "type": "function",
                        }
                    ],
                )
            ],
        }
        result = llm_next_step(state)
        assert result in ("security_proxy", "plan_review")

    def test_route_decision_complex(self):
        from src.agent.core.graph import route_decision

        assert route_decision({"route": "complex-cloud"}) == "scope_clarify"
        assert route_decision({"route": "simple"}) == "simple"
