"""Tests for context window category breakdown estimation."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent.core.complex_utils.context_breakdown import (
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


def test_schemas_included_in_input_estimated_and_total_used():
    from types import SimpleNamespace

    tools = [
        SimpleNamespace(name="web_search", description="Search the live web."),
        SimpleNamespace(name="ask_user", description="Ask a clarifying question."),
    ]
    messages = [HumanMessage(content="hello")]
    with_schemas = estimate_context_breakdown(
        messages, max_context=100_000, bound_tools=tools
    )
    without_schemas = estimate_context_breakdown(messages, max_context=100_000)
    assert (
        with_schemas["categories"]["schemas"] == with_schemas["tool_schema_tokens_est"]
    )
    assert with_schemas["categories"]["schemas"] > 0
    assert with_schemas["input_estimated"] == (
        without_schemas["input_estimated"] + with_schemas["tool_schema_tokens_est"]
    )
    assert with_schemas["total_used"] == with_schemas["input_estimated"]
    assert with_schemas["category_pct"]["schemas"] > 0


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
