"""Study/educator memory atom helpers."""

from scripts.run_educator_eval import score_educator_exchange

from src.memory.educator import (
    STUDY_STRUGGLE_PREFIX,
    build_mastery_atom,
    build_misconception_atom,
    is_struggle_recall_query,
    is_study_correction,
    is_study_mastery,
    resolve_study_scenario,
)


def test_is_study_correction_detects_wrong_explanation():
    human = (
        "Your explanation of Digital Literacy was wrong — the PDF emphasizes "
        "online learning guidelines. Please correct your answer."
    )
    assert is_study_correction(human)


def test_is_study_mastery_detects_final_understanding():
    assert is_study_mastery("I finally understand Digital Literacy now.")


def test_build_misconception_atom_includes_topic_and_struggle():
    human = (
        "Your explanation of Digital Literacy was wrong — the PDF emphasizes "
        "online learning guidelines. Please correct."
    )
    ai = "You're right; the PDF focuses on online learning guidelines."
    atom = build_misconception_atom(human, ai)
    assert STUDY_STRUGGLE_PREFIX in atom
    assert "Digital Literacy" in atom
    assert "struggled" in atom.lower()
    assert "misconception" in atom.lower()
    assert "online learning guidelines" in atom


def test_build_mastery_atom_includes_topic():
    atom = build_mastery_atom("I finally understand Digital Literacy now.")
    assert "Digital Literacy" in atom
    assert "mastery" in atom.lower()


def test_resolve_study_scenario_learning_mode():
    assert resolve_study_scenario("learning", "hello") == "study"


def test_resolve_study_scenario_keywords_without_style():
    assert resolve_study_scenario(None, "Quiz me on chapter 1") == "study"
    assert resolve_study_scenario("normal", "What is the weather?") is None


def test_format_struggle_recall_block():
    from src.memory.educator import format_struggle_recall_block

    block = format_struggle_recall_block(
        [
            {
                "memory": "User struggled with Digital Literacy — corrected misconception about online learning"
            }
        ]
    )
    assert "STUDY STRUGGLE RECALL" in block
    assert "online learning" in block
    assert format_struggle_recall_block([]) == ""


def test_is_struggle_recall_query():
    assert is_struggle_recall_query("What did I struggle with in Digital Literacy?")
    assert not is_struggle_recall_query("Quiz me on chapter 1")


def test_edu5_scoring_rejects_denial_without_substance():
    exchange = {
        "assistant_response_full": (
            "I don't have a specific record of what you struggled with in Digital Literacy."
        ),
        "executed_tools": [],
    }
    expected = {
        "educator_keywords_topic": ["Digital Literacy"],
        "educator_keywords_substantive": ["wrong", "misconception", "online learning"],
        "min_topic_hits": 1,
        "min_substantive_hits": 1,
        "forbid_phrases": ["don't have a specific record"],
    }
    scores = score_educator_exchange(exchange, expected, profile="cloud")
    assert scores["pass"] is False
    assert scores.get("forbid_phrases_ok") is False


def test_edu5_scoring_accepts_substantive_recall():
    exchange = {
        "assistant_response_full": (
            "You struggled with Digital Literacy — your misconception was about the "
            "online learning guidelines and digital competency emphasis in the PDF."
        ),
        "executed_tools": ["recall_all_memories"],
        "route": "complex-cloud",
    }
    expected = {
        "expected_route": "complex",
        "min_response_chars": 20,
        "educator_keywords_topic": ["Digital Literacy"],
        "educator_keywords_substantive": ["wrong", "misconception", "online learning"],
        "min_topic_hits": 1,
        "min_substantive_hits": 1,
        "forbid_phrases": ["don't have a specific record"],
    }
    scores = score_educator_exchange(exchange, expected, profile="cloud")
    assert scores["pass"] is True
    assert scores.get("recall_substantive_ok") is True
