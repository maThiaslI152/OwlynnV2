from langchain_core.messages import AIMessage, ToolMessage
from .helpers import _web_search_tool_output_has_results
from .formatter import _synthetic_answer_from_web_search_tool


def _fallback_for_blank_response(
    messages: list, *, web_search_enabled: bool
) -> AIMessage:
    """
    When the model returns empty assistant content, synthesize a safe user-visible reply.

    Prefers context from recent ``ToolMessage`` outputs (successful or failed ``web_search``).
    If there are no tool messages yet (first LLM turn before any tools) or no match, returns a
    generic message so the thread does not stay blank.
    """
    for m in reversed(messages):
        if not isinstance(m, ToolMessage):
            continue
        c = m.content if isinstance(m.content, str) else str(m.content or "")
        if (getattr(m, "name", None) or "") == "web_search":
            if _web_search_tool_output_has_results(c):
                return AIMessage(content=_synthetic_answer_from_web_search_tool(c))
            if (
                c.startswith("[web_search]")
                or "Unable to retrieve online results" in c
                or "blocked_by_captcha" in c
            ):
                return AIMessage(
                    content=(
                        "I couldn't verify this online right now because web search providers returned "
                        "errors or bot challenges. I did not find reliable live sources in this run. "
                        "If you want, I can retry with a narrower query, a different provider, or use "
                        "another source you provide."
                    )
                )
    if web_search_enabled:
        return AIMessage(
            content=(
                "I didn't get a usable reply from the model this time (empty response). "
                "Try rephrasing or shortening your message, confirm your LLM server is running, "
                "or retry. If you need live web facts, we can try again once the model responds normally."
            )
        )
    return AIMessage(
        content=(
            "I didn't get a usable reply from the model this time (empty response). "
            "Try rephrasing your question or confirm your local LLM is running correctly, then retry."
        )
    )
