"""Tests for context window category breakdown estimation."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent.nodes.complex_utils.context_breakdown import (
    enrich_token_usage_with_breakdown,
    estimate_context_breakdown,
)


def test_estimate_context_breakdown_categories():
    messages = [
        SystemMessage(content="You are Owlynn." * 50),
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there"),
        ToolMessage(
            content="search results " * 200, tool_call_id="c1", name="web_search"
        ),
    ]
    bd = estimate_context_breakdown(messages, max_context=100_000, output_tokens=500)
    assert bd["categories"]["system"] > bd["categories"]["conversation"]
    assert bd["categories"]["tools"] > 0
    assert bd["categories"]["output"] == 500
    assert bd["max_context"] == 100_000
    assert 0 < bd["used_pct"] <= 100


def test_enrich_scales_categories_to_actual_prompt_tokens():
    messages = [
        SystemMessage(content="sys"),
        HumanMessage(content="user"),
        ToolMessage(content="tool output", tool_call_id="c1", name="fetch"),
    ]
    api = {"prompt_tokens": 10_000, "completion_tokens": 800}
    enriched = enrich_token_usage_with_breakdown(api, messages, max_context=1_048_576)
    assert enriched is not None
    assert "context_breakdown" in enriched
    assert enriched["context_breakdown"]["input_estimated"] == 10_000
    assert enriched["context_breakdown"]["total_used"] == 10_800
