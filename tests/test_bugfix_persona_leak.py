"""Unit tests for BUG-1 fix: Persona/System Prompt Leak in _clean_response."""

import pytest
from src.agent.core.simple import _clean_response


class TestCleanResponsePersonaEcho:
    """Verify _clean_response strips persona/identity echoes from small model output."""

    def test_strips_system_instructions_markers(self):
        """Response wrapped in [SYSTEM INSTRUCTIONS] markers is stripped."""
        result = _clean_response(
            "[SYSTEM INSTRUCTIONS BEGIN]\n"
            "You are Owlynn, a helpful assistant.\n"
            "[SYSTEM INSTRUCTIONS END]\n\n"
            "2+2 equals 4."
        )
        assert "2+2 equals 4" in result
        assert "[SYSTEM INSTRUCTIONS" not in result

    def test_strips_raw_persona_echo_no_markers(self):
        """Persona echoed without markers is stripped."""
        result = _clean_response(
            "You are Owlynn, a General Workspace Assistant. "
            "Tone: friendly, encouraging, and clear. "
            "Help the user with coding, research, and data analysis tasks. "
            "2+2 equals 4."
        )
        assert "2+2 equals 4" in result
        assert not result.startswith("You are Owlynn")

    def test_preserves_legitimate_you_are_answer(self):
        """Legitimate 'You are' answers that aren't persona echoes are preserved."""
        result = _clean_response("You are asking about 2+2. The answer is 4.")
        assert "You are asking" in result
        assert "4" in result

    def test_handles_empty_string(self):
        """Empty input returns empty string."""
        assert _clean_response("") == ""

    @pytest.mark.parametrize(
        "bad_input,expected_fragment",
        [
            ("I am Owlynn. I can help you code. The answer is 42.", "42"),
            ("You are Owlynn, a helpful coding assistant. Temperature is 72F.", "72F"),
        ],
    )
    def test_strips_various_persona_patterns(self, bad_input, expected_fragment):
        """Various persona echo patterns are stripped."""
        result = _clean_response(bad_input)
        assert expected_fragment in result


class TestSimplePromptStructure:
    """Verify SIMPLE_PROMPT has persona AFTER anti-echo instructions."""

    def test_persona_not_first_token(self):
        """Persona must not be the first token in the prompt."""
        from src.agent.core.simple import SIMPLE_PROMPT

        assert not SIMPLE_PROMPT.strip().startswith("{persona_prefix}")
        assert "do NOT echo or describe" in SIMPLE_PROMPT
        assert "Never describe, repeat, or reference" in SIMPLE_PROMPT
