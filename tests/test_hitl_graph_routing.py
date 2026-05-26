"""Tests for HITL graph routing with new nodes."""

import pytest


class TestGraphRouting:
    def test_complex_route_goes_to_scope_clarify(self):
        from src.agent.graph import route_decision
        for route in ("complex-default", "complex-vision", "complex-longctx", "complex-cloud"):
            assert route_decision({"route": route}) == "scope_clarify"

    def test_simple_route_skips_scope_clarify(self):
        from src.agent.graph import route_decision
        assert route_decision({"route": "simple"}) == "simple"

    def test_scope_clarify_always_goes_to_complex_llm(self):
        from src.agent.graph import scope_clarify_next
        assert scope_clarify_next({}) == "complex_llm"

    def test_no_tool_calls_goes_to_memory_write(self):
        from src.agent.graph import llm_next_step
        assert llm_next_step({"pending_tool_calls": False, "messages": []}) == "memory_write"

    def test_plan_review_approved_goes_to_security(self):
        from src.agent.graph import plan_review_next
        assert plan_review_next({"execution_approved": True}) == "security_proxy"

    def test_plan_review_denied_goes_to_memory_write(self):
        from src.agent.graph import plan_review_next
        assert plan_review_next({"execution_approved": False}) == "memory_write"

    def test_security_next_approved(self):
        from src.agent.graph import security_next_step
        assert security_next_step({"execution_approved": True}) == "tool_action"

    def test_security_next_denied(self):
        from src.agent.graph import security_next_step
        assert security_next_step({"execution_approved": False}) == "memory_write"


class TestPolicyShared:
    def test_policy_exports(self):
        from src.agent.hitl.policy import SENSITIVE_TOOLS, is_sensitive_call, CATEGORY_REMEDIATION
        assert "write_workspace_file" in SENSITIVE_TOOLS
        assert "delete_workspace_file" in SENSITIVE_TOOLS
        assert callable(is_sensitive_call)
        assert "destructive_action" in CATEGORY_REMEDIATION


class TestHitlContext:
    def test_build_hitl_context_empty(self):
        from src.agent.hitl.context import build_hitl_context
        ctx = build_hitl_context({"messages": []})
        assert "conversation_snippet" in ctx
        assert ctx["conversation_snippet"] == ""

    def test_build_hitl_context_with_messages(self):
        from src.agent.hitl.context import build_hitl_context
        from langchain_core.messages import HumanMessage, AIMessage
        state = {
            "messages": [
                HumanMessage(content="Build a calculator"),
                AIMessage(content="I'll help you build it."),
            ]
        }
        ctx = build_hitl_context(state)
        assert "User: Build a calculator" in ctx["conversation_snippet"]
        assert "Owlynn" in ctx["conversation_snippet"]
        assert ctx["stated_intent"] != ""

    def test_enrich_interrupt(self):
        from src.agent.hitl.context import enrich_interrupt
        from langchain_core.messages import HumanMessage
        state = {"messages": [HumanMessage(content="Delete the old files")]}
        enriched = enrich_interrupt({"type": "test"}, state)
        assert enriched["type"] == "test"
        assert "conversation_snippet" in enriched
