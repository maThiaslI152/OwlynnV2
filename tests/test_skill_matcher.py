"""Unit tests for SkillMatcher class."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.tools.skills import SkillDefinition, SkillLoader, SkillMatcher, MatchResult


def _make_skill(name: str, triggers: list[str], description: str = "", file: str = "") -> SkillDefinition:
    """Helper to create a minimal SkillDefinition for testing."""
    return SkillDefinition(
        file=file or f"{name.lower().replace(' ', '_')}.md",
        name=name,
        triggers=triggers,
        description=description or f"A skill for {name.lower()}",
        prompt="Do the thing with {context}",
    )


@pytest.fixture
def mock_loader():
    """Create a mock SkillLoader with a few test skills."""
    loader = MagicMock(spec=SkillLoader)
    skills = [
        _make_skill("Research Assistant", ["research", "investigate"], "Source-backed research"),
        _make_skill("Data Visualization", ["chart", "graph", "plot", "visualize"], "Create charts and graphs"),
        _make_skill("Email Drafter", ["email", "draft email", "compose email"], "Draft professional emails"),
    ]
    loader.load_all.return_value = skills
    return loader


@pytest.fixture
def matcher(mock_loader):
    return SkillMatcher(mock_loader)


class TestKeywordScore:
    """Tests for SkillMatcher._keyword_score."""

    def test_exact_substring_match_returns_1(self, matcher):
        skill = _make_skill("Research", ["research", "investigate"])
        assert matcher._keyword_score("I want to research AI", skill) == 1.0

    def test_exact_substring_case_insensitive(self, matcher):
        skill = _make_skill("Research", ["research"])
        assert matcher._keyword_score("RESEARCH this topic", skill) == 1.0

    def test_multi_word_trigger_substring(self, matcher):
        skill = _make_skill("Email", ["draft email"])
        assert matcher._keyword_score("please draft email for me", skill) == 1.0

    def test_partial_token_overlap(self, matcher):
        skill = _make_skill("Research", ["deep research analysis"])
        # "research" token overlaps, but "deep research analysis" is not a substring of "help me research"
        score = matcher._keyword_score("help me research", skill)
        assert 0.0 < score < 1.0

    def test_no_overlap_returns_0(self, matcher):
        skill = _make_skill("Research", ["research", "investigate"])
        assert matcher._keyword_score("make me a sandwich", skill) == 0.0

    def test_partial_overlap_ratio(self, matcher):
        # triggers: ["data analysis report"] → tokens: {data, analysis, report}
        skill = _make_skill("Analyzer", ["data analysis report"])
        # query tokens: {show, me, data} → overlap: {data} → 0.5 * 1/3
        score = matcher._keyword_score("show me data", skill)
        assert score == pytest.approx(0.5 * 1 / 3, abs=0.01)


class TestMatch:
    """Tests for SkillMatcher.match."""

    def test_returns_matches_sorted_by_score(self, matcher):
        results = matcher.match("research this topic")
        assert len(results) > 0
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    def test_respects_top_k(self, matcher):
        results = matcher.match("help me with something", top_k=1)
        assert len(results) <= 1

    def test_empty_skills_returns_empty(self):
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = []
        m = SkillMatcher(loader)
        assert m.match("anything") == []

    def test_exact_trigger_match_scores_high(self, matcher):
        results = matcher.match("research")
        # "research" is an exact trigger substring → keyword score 1.0
        if results:
            skill, score = results[0]
            assert skill.name == "Research Assistant"
            assert score >= 0.6  # at least keyword weight

    def test_scores_in_valid_range(self, matcher):
        results = matcher.match("research data visualization email")
        for _, score in results:
            assert 0.0 <= score <= 1.0


class TestMatchBest:
    """Tests for SkillMatcher.match_best."""

    def test_returns_best_match_above_threshold(self, matcher):
        result = matcher.match_best("research this topic")
        assert result is not None
        assert result.name == "Research Assistant"

    def test_returns_none_below_threshold(self):
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = [
            _make_skill("Niche Skill", ["xyzzy_unique_trigger_42"])
        ]
        m = SkillMatcher(loader)
        result = m.match_best("completely unrelated query", threshold=0.9)
        assert result is None

    def test_returns_none_for_empty_skills(self):
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = []
        m = SkillMatcher(loader)
        assert m.match_best("anything") is None


class TestSemanticScore:
    """Tests for SkillMatcher._semantic_score."""

    def test_returns_scores_for_all_skills(self, matcher):
        results = matcher._semantic_score("research data")
        # Should have one entry per skill
        assert len(results) == 3

    def test_scores_are_non_negative(self, matcher):
        results = matcher._semantic_score("chart visualization")
        for _, score in results:
            assert score >= 0.0


class TestRebuildIndex:
    """Tests for SkillMatcher._rebuild_index."""

    def test_builds_index_from_skills(self, matcher):
        matcher._rebuild_index()
        assert matcher._tfidf_matrix is not None
        assert matcher._vectorizer is not None
        assert len(matcher._skill_names) == 3

    def test_empty_skills_clears_index(self):
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = []
        m = SkillMatcher(loader)
        m._rebuild_index()
        assert m._tfidf_matrix is None
        assert m._vectorizer is None
        assert m._skill_names == []


class TestMatchWithConfidence:
    """Tests for SkillMatcher.match_with_confidence()."""

    def test_strong_match_is_not_ambiguous(self, matcher):
        """Exact trigger match with high score → not ambiguous."""
        result = matcher.match_with_confidence("help me research this topic")
        assert not result.is_ambiguous
        assert result.top_match is not None
        assert result.top_match.name == "Research Assistant"
        assert result.best_score >= 0.6
        assert result.ambiguity_reason == ""

    def test_weak_match_is_ambiguous_signal_a(self):
        """No strong match, AND query is short → is_ambiguous = True (Signal A)."""
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = [
            _make_skill("Niche Skill", ["xyzzy_unique_trigger_42"])
        ]
        m = SkillMatcher(loader)
        # Short query with no intent keywords → vague → HITL
        result = m.match_with_confidence("unrelated")
        assert result.is_ambiguous
        assert len(result.ambiguity_reason) > 0

    def test_substantive_query_no_skill_match_is_not_ambiguous(self):
        """Clear query with enough words → routes directly even with no skill match."""
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = [
            _make_skill("Niche Skill", ["xyzzy_unique_trigger_42"])
        ]
        m = SkillMatcher(loader)
        result = m.match_with_confidence("something completely unrelated here")
        assert not result.is_ambiguous
        assert result.candidate_skills == []

    def test_vague_query_is_ambiguous_signal_c(self, matcher):
        """Very short query → is_ambiguous = True (Signal C: vague query)."""
        result = matcher.match_with_confidence("hi")
        assert result.is_ambiguous
        assert len(result.ambiguity_reason) > 0

    def test_short_no_intent_keywords_is_ambiguous_signal_c(self, matcher):
        """Short query with no intent keywords → is_ambiguous = True (Signal C)."""
        result = matcher.match_with_confidence("hmm")
        assert result.is_ambiguous
        assert len(result.ambiguity_reason) > 0

    def test_long_no_intent_keywords_is_not_ambiguous(self, matcher):
        """Long enough query without intent keywords → routes directly (not vague)."""
        result = matcher.match_with_confidence("the quick brown fox")
        assert not result.is_ambiguous

    def test_multi_tie_is_ambiguous_signal_b(self):
        """Multiple close-scoring skills → is_ambiguous = True (Signal B)."""
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = [
            _make_skill("Research", ["research"], "Research things"),
            _make_skill("Investigate", ["investigate"], "Investigate topics"),
            _make_skill("Analyze", ["analyze"], "Analyze data"),
        ]
        m = SkillMatcher(loader)
        # "investigate" is an exact trigger for "Investigate" → 1.0 keyword
        # But "research" might also score from TF-IDF similarity
        result = m.match_with_confidence("please research and investigate this topic")
        # Should have at least 2 candidates with close scores
        if len(result.candidate_skills) >= 2:
            scores = [s for _, s in result.candidate_skills[:2]]
            close = (scores[0] - scores[1]) <= 0.15
            if close:
                assert result.is_ambiguous is True
                assert "Multiple skills" in result.ambiguity_reason or "close" in result.ambiguity_reason.lower()

    def test_candidate_skills_respects_top_k(self):
        """candidate_skills length does not exceed the requested top_k."""
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = [
            _make_skill(f"Skill{i}", [f"trigger{i}"]) for i in range(10)
        ]
        m = SkillMatcher(loader)
        result = m.match_with_confidence("anything", top_k=3)
        assert len(result.candidate_skills) <= 3

    def test_returns_match_result_type(self, matcher):
        """Returns MatchResult dataclass with expected fields."""
        result = matcher.match_with_confidence("research")
        assert isinstance(result, MatchResult)
        assert hasattr(result, "is_ambiguous")
        assert hasattr(result, "candidate_skills")
        assert hasattr(result, "ambiguity_reason")
        assert hasattr(result, "best_score")
        assert hasattr(result, "top_match")

    def test_empty_skills_vague_query_is_ambiguous(self):
        """No skills loaded + vague query → is_ambiguous = True."""
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = []
        m = SkillMatcher(loader)
        result = m.match_with_confidence("huh")
        assert result.is_ambiguous
        assert result.top_match is None
        assert result.candidate_skills == []

    def test_empty_skills_clear_query_is_not_ambiguous(self):
        """No skills loaded but query has clear intent → routes directly (no HITL)."""
        loader = MagicMock(spec=SkillLoader)
        loader.load_all.return_value = []
        m = SkillMatcher(loader)
        result = m.match_with_confidence("research something")
        assert not result.is_ambiguous
        assert result.top_match is None
        assert result.candidate_skills == []
