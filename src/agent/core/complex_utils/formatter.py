import re
from src.config.config_loader import config

# DeepSeek V4 sometimes emits tool calls as DSML markup in ``content`` instead of
# structured ``tool_calls`` (especially when tools are unbound on synthesis turns).
_DSML_TAG = r"<\s*[\uFF5C|]{1,3}\s*DSML\s*[\uFF5C|]{1,3}"
_DSML_ELEMENT_RE = re.compile(
    _DSML_TAG + r"(\w+)[^>]*>(.*?)</\s*[\uFF5C|]{1,3}\s*DSML\s*[\uFF5C|]{1,3}\s*\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
_DSML_MARKER_RE = re.compile(_DSML_TAG, re.IGNORECASE)


_ALT_TOOL_SYNTAX_RE = re.compile(r"<tool_call>|<function=", re.IGNORECASE)
_ALT_TOOL_CALL_BLOCK_RE = re.compile(
    r"<tool_call>.*?(?:</tool_call>|$)", re.DOTALL | re.IGNORECASE
)
_ALT_FUNCTION_BLOCK_RE = re.compile(
    r"<function=[^>]*>.*?(?:</function>|(?=<tool_call>)|$)", re.DOTALL | re.IGNORECASE
)


def _content_has_dsml_tool_syntax(text: str) -> bool:
    """Return True when assistant text contains pseudo-tool-call markup."""
    t = text or ""
    return bool(
        _DSML_MARKER_RE.search(t)
        or _ALT_TOOL_SYNTAX_RE.search(t)
        or "</tool_call>" in t
        or "</function>" in t
    )


def _strip_dsml_blocks(text: str) -> str:
    """Remove DeepSeek DSML tool-call blocks and Qwen XML blocks from visible assistant content."""
    if not text:
        return text
    cleaned = text
    for _ in range(8):
        new = _DSML_ELEMENT_RE.sub("", cleaned)
        if new == cleaned:
            break
        cleaned = new
    if _DSML_MARKER_RE.search(cleaned):
        cleaned = _DSML_MARKER_RE.split(cleaned, maxsplit=1)[0]
    for _ in range(4):
        new = _ALT_TOOL_CALL_BLOCK_RE.sub("", cleaned)
        new = _ALT_FUNCTION_BLOCK_RE.sub("", new)
        if new == cleaned:
            break
        cleaned = new
    if _ALT_TOOL_SYNTAX_RE.search(cleaned):
        cleaned = _ALT_TOOL_SYNTAX_RE.split(cleaned, maxsplit=1)[0]

    # Strip any remaining orphan/partial tags to prevent eval leaks
    orphan_tags = [
        r"</tool_call>",
        r"</function>",
        r"<tool_call>",
        r"<function=[^>]*>",
        r"<\s*[\uFF5C|]{1,3}\s*DSML\s*[\uFF5C|]{1,3}[^>]*>",
        r"</\s*[\uFF5C|]{1,3}\s*DSML\s*[\uFF5C|]{1,3}[^>]*>",
    ]
    for tag_pattern in orphan_tags:
        cleaned = re.sub(tag_pattern, "", cleaned, flags=re.IGNORECASE)

    # Do not blindly call .strip() here, otherwise streaming deltas will lose their spaces!
    return cleaned


def needs_web_synthesis_retry(
    *,
    has_tool_calls: bool,
    raw_visible: str,
    cleaned_visible: str,
    min_chars: int = 80,
) -> bool:
    """True when forced web synthesis produced stall markup or too little prose."""
    if has_tool_calls:
        return False
    if _content_has_dsml_tool_syntax(raw_visible):
        return True
    return len((cleaned_visible or "").strip()) < min_chars


def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks from reasoning output."""
    if not text:
        return text
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return cleaned if cleaned else text


def _synthetic_answer_from_web_search_tool(content: str) -> str:
    """
    When the LLM returns empty after a successful web_search, surface the tool text
    so the user still gets a usable answer in the UI.
    """
    c = (content or "").strip()
    if not c:
        return (
            "I ran **web_search** but the tool returned no text. "
            "Try again or narrow the query."
        )
    pref = (
        "The model returned an empty message after **web_search**, so here is the "
        "search payload directly (you can use the links below):\n\n"
    )
    cap = int(config.get("complex.synthetic_answer_max_chars", 4500))
    if len(c) > cap:
        return pref + c[:cap] + "\n\n… [truncated]"
    return pref + c


def _flatten_human_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return str(content or "")


_TOOL_ONLY_PLACEHOLDERS: dict[str, str] = {
    "notebook_run": "Generating chart with **notebook_run** — this may take a moment…",
    "web_search": "Searching the web…",
    "fetch_webpage": "Fetching page content…",
    "fetch_webpage_dynamic": "Loading rendered page content…",
    "deep_research": "Running deep research…",
    "read_workspace_file": "Reading workspace file…",
    "write_workspace_file": "Writing to workspace…",
}


def placeholder_for_tool_only_turn(tool_calls: list) -> str:
    """Short visible text when the model returns tool_calls with empty content."""
    names: list[str] = []
    for tc in tool_calls or []:
        if isinstance(tc, dict):
            names.append(str(tc.get("name") or ""))
        else:
            names.append(str(getattr(tc, "name", "") or ""))
    for name in names:
        if name in _TOOL_ONLY_PLACEHOLDERS:
            return _TOOL_ONLY_PLACEHOLDERS[name]
    if "notebook_run" in names:
        return _TOOL_ONLY_PLACEHOLDERS["notebook_run"]
    if names:
        return f"Running **{names[0]}**…"
    return "Working on your request…"
