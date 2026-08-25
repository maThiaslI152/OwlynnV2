"""
AskUserQuestion Tool — Let the agent ask clarifying questions mid-task.

Supports 1-3 suggested choices plus a free-text option.
Uses LangGraph interrupt() to pause and wait for user input.
"""

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def ask_user(question: str, choices: str = "") -> str:
    """
    Asks the user a clarifying question and waits for their response.
    Use this ONCE when a request is clearly ambiguous. Don't over-ask.

    Do NOT use this when the user asked for a code review but provided no code
    or attachment — reply briefly that you need the code pasted/attached instead.

    The user sees the question with clickable choice buttons (if provided)
    plus a free-text input for custom answers.

    Args:
        question: The question to ask.
        choices: Optional comma-separated choices (1-3 max). Example: "PDF,Word,PowerPoint"
    """
    raw_choices = (
        [c.strip() for c in choices.split(",") if c.strip()][:3] if choices else []
    )
    choice_list = [{"label": c, "allows_user_input": False} for c in raw_choices]
    choice_list.append({"label": "Type custom answer...", "allows_user_input": True})
    response = interrupt(
        {
            "type": "ask_user",
            "question": question,
            "choices": choice_list,
        }
    )
    if isinstance(response, dict):
        return response.get("answer", str(response))
    return str(response)
