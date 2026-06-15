"""Tests for learning / educator response styles."""

from src.agent.response_styles import style_instruction_for_prompt


def test_learning_style_includes_scaffolding():
    hint = style_instruction_for_prompt("learning")
    assert "define terms" in hint.lower()
    assert "example" in hint.lower()


def test_learning_style_handles_criticism_and_reinforcement():
    hint = style_instruction_for_prompt("learning").lower()
    assert "critic" in hint or "correction" in hint
    assert "self-reinfor" in hint or "i think" in hint or "finally understand" in hint


def test_normal_style_empty():
    assert style_instruction_for_prompt("normal") == ""
    assert style_instruction_for_prompt(None) == ""
