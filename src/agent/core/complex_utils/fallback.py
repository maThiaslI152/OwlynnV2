from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .formatter import _synthetic_answer_from_web_search_tool, latest_user_text
from .helpers import _web_search_tool_output_has_results

_FETCH_TOOLS = frozenset({"fetch_webpage", "fetch_webpage_dynamic", "deep_research"})
_GAME_CONTEXT_KEYWORDS = (
    "stalker",
    "anomaly",
    "modpack",
    "gamma",
    "game",
    "steam",
    "moddb",
    "github",
    "grokitach",
)
_MEDICAL_ZONA_MARKERS = (
    "thần kinh",
    "herpes",
    "shingles",
    "bệnh",
    "triệu chứng",
    "vinmec",
    "bacsi",
    "varicella",
    "giời leo",
)


def _user_expects_gaming_context(user_text: str) -> bool:
    low = (user_text or "").lower()
    return any(
        k in low for k in ("modpack", "gamma", "stalker", "anomaly", "game", "zona")
    )


def _web_search_content_relevant(content: str, user_text: str) -> bool:
    """Drop medical/ambiguous Zona hits when the user asked about a game modpack."""
    if not _user_expects_gaming_context(user_text):
        return True
    c_low = (content or "").lower()
    medical = sum(1 for m in _MEDICAL_ZONA_MARKERS if m in c_low)
    gaming = sum(1 for g in _GAME_CONTEXT_KEYWORDS if g in c_low)
    return gaming > 0 and gaming >= medical


def _answer_from_fetch_excerpts(messages: list) -> AIMessage | None:
    """Prefer fetched page excerpts over raw search listings for fallback answers."""
    excerpts: list[str] = []
    for m in reversed(messages):
        if not isinstance(m, ToolMessage):
            continue
        name = getattr(m, "name", "") or ""
        if name not in _FETCH_TOOLS:
            continue
        c = m.content if isinstance(m.content, str) else str(m.content or "")
        if "[fetch_webpage] HTTP error" in c or c.startswith("[web_search]"):
            continue
        if "📄" in c or "Retrieved excerpts" in c or len(c.strip()) > 150:
            excerpts.append(c.strip())
    if not excerpts:
        return None
    body = "\n\n---\n\n".join(excerpts[:3])
    cap = 4500
    if len(body) > cap:
        body = body[:cap] + "\n\n… [truncated]"
    return AIMessage(
        content=(
            "I could not get a polished summary from the cloud model, but here is what "
            "was retrieved from the relevant pages during research:\n\n" + body
        )
    )


def _answer_from_notebook_chart(
    messages: list, *, project_id: str = "default"
) -> AIMessage | None:
    """Use chart completion copy when notebook_run saved a chart this turn."""
    from src.tools.notebook_libs import chart_completion_message

    for m in reversed(messages):
        if not isinstance(m, ToolMessage) or getattr(m, "name", "") != "notebook_run":
            continue
        content = m.content if isinstance(m.content, str) else str(m.content or "")
        completion = chart_completion_message(content, project_id=project_id)
        if completion:
            return AIMessage(content=completion)
        break
    return None


def _fallback_for_blank_response(
    messages: list, *, web_search_enabled: bool
) -> AIMessage:
    """
    When the model returns empty assistant content, synthesize a safe user-visible reply.

    Prefers fetch/deep_research excerpts, then filtered web_search listings.
    """
    user_text = latest_user_text(messages)

    chart_answer = _answer_from_notebook_chart(messages)
    if chart_answer is not None:
        return chart_answer

    fetch_answer = _answer_from_fetch_excerpts(messages)
    if fetch_answer is not None:
        return fetch_answer

    for m in reversed(messages):
        if not isinstance(m, ToolMessage):
            continue
        c = m.content if isinstance(m.content, str) else str(m.content or "")
        if (getattr(m, "name", None) or "") == "web_search":
            if _web_search_tool_output_has_results(c):
                if _web_search_content_relevant(c, user_text):
                    return AIMessage(content=_synthetic_answer_from_web_search_tool(c))
                return AIMessage(
                    content=(
                        "Web search returned mostly unrelated results (likely because "
                        '"ZONA" matched medical pages instead of the STALKER modpack). '
                        "Try rephrasing with full context, e.g. "
                        '"STALKER Anomaly GAMMA vs ZONA modpack comparison".'
                    )
                )
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
