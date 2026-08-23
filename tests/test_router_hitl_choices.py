"""Router low-confidence HITL choice builder."""

import pytest
from langchain_core.messages import HumanMessage

from src.agent.core.state import AgentState
from src.agent.routing.router import (
    _build_low_confidence_router_choices,
    _is_simple_informational_query,
)


@pytest.mark.parametrize(
    "text,expected_labels",
    [
        (
            "how many provinces in Norway",
            ["Search the web", "Just answer directly"],
        ),
        (
            "read my workspace budget.pdf and summarize",
            ["Search the web", "Work with local files", "Just answer directly"],
        ),
        (
            "make a chart from microphone_comparison.xlsx",
            [
                "Search the web",
                "Create documents/visualizations",
                "Just answer directly",
            ],
        ),
    ],
)
def test_build_low_confidence_router_choices_contextual(text, expected_labels):
    choices = _build_low_confidence_router_choices(text, cloud_available=False)
    assert [c["label"] for c in choices] == expected_labels
    assert all(c["route"] == "complex-default" for c in choices)
    assert all("Use cloud model" not in c["label"] for c in choices)


def test_build_low_confidence_router_choices_cloud_first():
    choices = _build_low_confidence_router_choices(
        "how many provinces in Norway", cloud_available=True
    )
    assert all(c["route"] in ("complex-default", "complex-cloud") for c in choices)


def test_is_simple_informational_query():
    assert _is_simple_informational_query("What is the capital of Norway")
    assert not _is_simple_informational_query("create a chart from sales.csv")


@pytest.mark.anyio
async def test_simple_factual_query_skips_router_hitl(monkeypatch):
    """Norway-style factual follow-ups should not show toolbox picker."""
    import src.agent.routing.router as router_mod

    async def fake_small_llm():
        class LLM:
            def bind(self, **_kwargs):
                return self

            async def ainvoke(self, _messages):
                class R:
                    content = '{"routing":"complex","confidence":0.42,"toolbox":"all"}'

                return R()

        return LLM()

    monkeypatch.setattr(router_mod, "get_main_llm", fake_small_llm)
    monkeypatch.setattr(router_mod, "get_small_llm", fake_small_llm)
    monkeypatch.setattr(
        router_mod,
        "SkillMatcher",
        lambda _loader: type(
            "M",
            (),
            {
                "match_with_confidence": lambda self, _t, top_k=5: (
                    router_mod.MatchResult(
                        is_ambiguous=False,
                        top_match=None,
                        candidate_skills=[],
                        ambiguity_reason="",
                        best_score=0.0,
                    )
                )
            },
        )(),
    )

    state: AgentState = {
        "messages": [HumanMessage(content="how many provinces in Norway")],
        "web_search_enabled": True,
    }
    out = await router_mod.router_node(state)
    assert out["router_clarification_used"] is False
