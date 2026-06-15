"""Router / skill intent for workspace PDF study."""

from src.agent.nodes.router import _toolbox_for_skill
from src.tools.skills import SkillMatcher, _default_loader


def test_study_tutor_skill_matches_pdf_study_prompt():
    matcher = SkillMatcher(_default_loader)
    result = matcher.match_with_confidence("Help me study this PDF for exam prep")
    names = [s.name for s, _ in (result.candidate_skills or [])]
    if result.top_match:
        names.insert(0, result.top_match.name)
    assert any("Study Tutor" in n for n in names)


def test_study_tutor_toolbox_includes_file_ops():
    matcher = SkillMatcher(_default_loader)
    result = matcher.match_with_confidence("Help me study chapter 1 Digital Literacy")
    assert result.top_match is not None
    toolbox = _toolbox_for_skill(result.top_match)
    assert "file_ops" in toolbox
    assert "web_search" not in toolbox or toolbox.index("file_ops") == 0


def test_research_assistant_does_not_hijack_pdf_study():
    matcher = SkillMatcher(_default_loader)
    result = matcher.match_with_confidence(
        "Help me study this PDF file in my workspace"
    )
    top = result.top_match.name if result.top_match else ""
    assert "Research Assistant" != top


def test_exam_prep_skill_matches_mock_exam():
    matcher = SkillMatcher(_default_loader)
    result = matcher.match_with_confidence("Give me a mock exam on chapter 1")
    top = result.top_match.name if result.top_match else ""
    assert "Exam Prep" in top or "Study Tutor" in top


def test_flashcard_builder_matches():
    matcher = SkillMatcher(_default_loader)
    result = matcher.match_with_confidence("Make flashcards from this chapter")
    assert result.top_match is not None
    assert "Flashcard" in result.top_match.name
