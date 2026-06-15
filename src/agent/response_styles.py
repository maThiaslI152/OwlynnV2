"""User-selected response style → short system-prompt extension."""

from __future__ import annotations

STYLE_INSTRUCTIONS: dict[str, str] = {
    "normal": (
        "\n\nResponse style: Normal — when a diagram, collapsible section, or inline widget "
        "(quiz, steps, callout via render_interactive_block) would clarify the answer, prefer "
        "that over long prose."
    ),
    "learning": (
        "\n\nResponse style: Learning mode — teach clearly: define terms, use a concrete example "
        "where helpful, and build from simple to more detailed. "
        "Prefer interactive blocks (`render_interactive_block` or owlynn-* fences) over walls "
        "of text: one brief intro sentence, then the widget. "
        "When the user criticizes your answer, acknowledge the correction, revisit the source "
        "material if available, and revise. "
        'When the user self-reinforces ("I think…", "I finally understand…"), confirm what is '
        "correct, gently fix misconceptions, and extend with one helpful detail. "
        "End study answers with an inline quiz or check-for-understanding when appropriate."
    ),
    "concise": (
        "\n\nResponse style: Concise — short paragraphs, no filler, bullet points when listing items."
    ),
    "explanatory": (
        "\n\nResponse style: Explanatory — structured answer with clear sections or bullets; "
        "assume the reader is new to the topic."
    ),
    "formal": ("\n\nResponse style: Formal and professional tone throughout."),
}


def style_instruction_for_prompt(style: str | None) -> str:
    key = (style or "normal").strip().lower()
    return STYLE_INSTRUCTIONS.get(key, "")
