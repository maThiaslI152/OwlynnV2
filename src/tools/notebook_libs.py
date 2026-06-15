"""Probe libraries available to the notebook_run worker (same Python env)."""

from __future__ import annotations

import importlib.util
import re
from functools import lru_cache

from langchain_core.messages import AIMessage, ToolMessage

_NOTEBOOK_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("matplotlib", "matplotlib"),
    ("seaborn", "seaborn"),
    ("plotly", "plotly"),
    ("scipy", "scipy"),
    ("sklearn", "scikit-learn"),
    ("openpyxl", "openpyxl"),
    ("xlsxwriter", "xlsxwriter"),
    ("PIL", "pillow"),
    ("sympy", "sympy"),
    ("chardet", "chardet"),
    ("tabulate", "tabulate"),
    ("jinja2", "jinja2"),
)

_VIZ_MODULES = frozenset({"matplotlib", "seaborn", "plotly", "mpl_toolkits"})


@lru_cache(maxsize=1)
def available_notebook_libraries() -> tuple[str, ...]:
    """Return display names of importable modules in the notebook worker env."""
    found: list[str] = []
    for mod, label in _NOTEBOOK_CANDIDATES:
        if importlib.util.find_spec(mod) is not None:
            found.append(label)
    return tuple(found)


def format_available_libraries() -> str:
    libs = available_notebook_libraries()
    return ", ".join(libs) if libs else "none detected"


def has_viz_libraries() -> bool:
    return any(
        importlib.util.find_spec(mod) is not None
        for mod in ("matplotlib", "seaborn", "plotly")
    )


def notebook_module_missing_nudge(module_name: str) -> str:
    """Build an accurate recovery nudge after ModuleNotFoundError in notebook_run."""
    available = format_available_libraries()
    viz_missing = module_name in _VIZ_MODULES or module_name.startswith("mpl")
    base = (
        f"[Internal reminder] notebook_run failed because '{module_name}' is not installed. "
        f"Actually available libraries: {available}. "
    )
    if viz_missing:
        return (
            base + "Do NOT retry matplotlib, seaborn, or plotly. "
            "Instead, visualize using inline HTML bar charts in your assistant reply "
            "(simple div/table markup the UI can render), or summarize key numbers in a "
            "markdown table from the prior conversation context."
        )
    return base + "Retry using only the libraries listed above."


_CHART_FILENAME_RE = re.compile(
    r"([\w.-]+\.(?:png|jpe?g|gif|webp|svg|html))",
    re.IGNORECASE,
)
_INTERACTIVE_CHART_RE = re.compile(r"([\w.-]+\.html)", re.IGNORECASE)

PLOTLY_SAVE_SNIPPET = 'fig.write_html(f"{WORKSPACE_DIR}/chart.html", include_plotlyjs="cdn", full_html=True)'


def notebook_interactive_viz_guidance(project_id: str = "default") -> str:
    """Guidance for interactive Plotly charts rendered in the chat UI."""
    return (
        "For user-facing visualizations, prefer **interactive Plotly** charts (hover tooltips, zoom, pan). "
        "Use notebook_run with plotly.express or plotly.graph_objects, then save:\n"
        f"  {PLOTLY_SAVE_SNIPPET}\n"
        "Embed in your final reply as a markdown link (not an image):\n"
        f"  [Interactive chart](/api/files/chart.html?project_id={project_id})\n"
        "Use matplotlib PNG only when Plotly is unsuitable."
    )


_MIME_BY_EXT: dict[str, str] = {
    "html": "text/html",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}


def parse_chart_artifact(
    content: str, project_id: str = "default"
) -> dict[str, str] | None:
    """Extract chart file metadata from notebook_run output for UI auto-embed."""
    if not content or "Error" in content:
        return None
    lowered = content.lower()
    if "saved" not in lowered and not _CHART_FILENAME_RE.search(content):
        return None

    html_match = _INTERACTIVE_CHART_RE.search(content)
    if html_match:
        filename = html_match.group(1)
    else:
        match = _CHART_FILENAME_RE.search(content)
        if not match:
            return None
        filename = match.group(1)
        if filename.lower().endswith(".html"):
            return None

    ext = filename.rsplit(".", 1)[-1].lower()
    kind = "interactive" if ext == "html" else "static"
    mime_type = _MIME_BY_EXT.get(ext, "application/octet-stream")
    return {
        "filename": filename,
        "url": f"/api/files/{filename}?project_id={project_id}",
        "kind": kind,
        "mime_type": mime_type,
    }


def chart_completion_message(
    content: str, *, project_id: str = "default"
) -> str | None:
    """Short user-visible reply after notebook_run saved a chart artifact."""
    artifact = parse_chart_artifact(content, project_id=project_id)
    if not artifact:
        return None
    if artifact["kind"] == "interactive":
        return (
            "I've created an interactive chart from our conversation — "
            "hover, zoom, and pan to explore the breakdown."
        )
    return (
        "I've created a chart from our conversation. "
        "Click it to enlarge and explore the details."
    )


def turn_ends_with_chart_completion(
    turn_messages: list, project_id: str = "default"
) -> bool:
    """True when the current turn already has a final reply after a chart notebook_run."""
    if len(turn_messages) < 2:
        return False
    last = turn_messages[-1]
    if not isinstance(last, AIMessage) or getattr(last, "tool_calls", None):
        return False
    if not str(last.content or "").strip():
        return False
    return any(
        isinstance(m, ToolMessage)
        and getattr(m, "name", "") == "notebook_run"
        and parse_chart_artifact(str(m.content or ""), project_id=project_id)
        for m in turn_messages
    )


def notebook_chart_embed_nudge(content: str, project_id: str = "default") -> str | None:
    """Return a reply-style reminder when notebook_run saved a chart artifact."""
    artifact = parse_chart_artifact(content, project_id=project_id)
    if not artifact:
        return None

    filename = artifact["filename"]
    if artifact["kind"] == "interactive":
        return (
            f"[Internal reminder] Interactive chart `{filename}` was saved and will auto-render "
            "in the chat UI (Plotly hover/zoom/pan). Your **final user-visible reply** must be "
            "1–2 short sentences describing the chart insight only — do NOT include markdown "
            "image links, file paths, or `/api/files/` URLs."
        )

    return (
        f"[Internal reminder] Chart `{filename}` was saved and will auto-render in the chat UI. "
        "Your **final user-visible reply** must be 1–2 short sentences describing the chart "
        "insight only — do NOT include markdown image links, file paths, or `/api/files/` URLs. "
        "For interactive charts next time, prefer Plotly HTML:\n"
        f"  {PLOTLY_SAVE_SNIPPET}"
    )


def clear_notebook_libs_cache() -> None:
    """Test helper — invalidate cached probe results."""
    available_notebook_libraries.cache_clear()
