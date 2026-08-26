"""Toolbox registry and tool binding for the complex path.

See docs/TOOLS.md; implement tools in src/tools/ and register here.
"""

import os

from src.tools.ask_user import ask_user
from src.tools.core_tools import (
    delete_workspace_file,
    download_to_workspace,
    edit_workspace_file,
    forget_memory,
    list_workspace_files,
    read_workspace_file,
    recall_all_memories,
    recall_memories,
    write_workspace_file,
)
from src.tools.data_connectors import (
    ingest_github_repo,
    ingest_obsidian_vault,
    ingest_youtube_transcript,
)
from src.tools.doc_generator import create_docx, create_pdf, create_pptx, create_xlsx
from src.tools.interactive_content import render_interactive_block
from src.tools.ipynb_tools import export_ipynb_html, read_ipynb, write_ipynb
from src.tools.notebook import notebook_reset, notebook_run, notebook_vars
from src.tools.pentest_ad import PENTEST_AD_TOOLS
from src.tools.pentest_cloud import PENTEST_CLOUD_TOOLS
from src.tools.pentest_exploit import PENTEST_EXPLOIT_TOOLS
from src.tools.pentest_network import PENTEST_NETWORK_TOOLS
from src.tools.pentest_osint import PENTEST_OSINT_TOOLS
from src.tools.pentest_password import PENTEST_PASSWORD_TOOLS
from src.tools.pentest_post import PENTEST_POST_TOOLS
from src.tools.pentest_reporting import PENTEST_REPORTING_TOOLS
from src.tools.pentest_tools import PENTEST_TOOLS
from src.tools.pentest_vuln import PENTEST_VULN_TOOLS
from src.tools.pentest_web import PENTEST_WEB_TOOLS
from src.tools.screen_assist.tools import (
    NORMAL_SCREEN_ASSIST_TOOLS,
    SCREEN_ASSIST_TOOLS,
)
from src.tools.skills import invoke_skill, list_skills, skill_manage, skill_view
from src.tools.study_tools import (
    course_chat_create,
    course_get,
    course_list,
    course_register,
    course_workspace_create,
    export_study_sheet,
    flashcard_deck_create,
    flashcard_export,
    flashcard_import,
    flashcard_review,
    flashcard_suggest,
    mastery_record,
    quiz_session_answer,
    quiz_session_results,
    quiz_session_start,
    study_note_delete,
    study_note_save,
    study_note_search,
    study_session_log,
    study_weak_areas,
)
from src.tools.todo import todo_add, todo_complete, todo_filter, todo_list, todo_update
from src.tools.web_tools import (
    browser_background_fetch,
    deep_research,
    fetch_webpage,
    web_search,
)

# Full tool set with web search enabled (chat-only: no workspace file CRUD)
COMPLEX_TOOLS_WITH_WEB: list = [
    # Web
    web_search,
    fetch_webpage,
    browser_background_fetch,
    deep_research,
    # Memory
    recall_memories,
    recall_all_memories,
    forget_memory,
    # Computation (ephemeral scratch via tool_workspace_root)
    notebook_run,
    notebook_reset,
    notebook_vars,
    # Document generation
    create_docx,
    create_xlsx,
    create_pptx,
    create_pdf,
    # Task tracking
    todo_add,
    todo_list,
    todo_complete,
    todo_update,
    todo_filter,
    # Skills
    list_skills,
    invoke_skill,
    skill_view,
    skill_manage,
    render_interactive_block,
    # HITL
    ask_user,
]

# Tool set without web search
COMPLEX_TOOLS_NO_WEB: list = [
    recall_memories,
    recall_all_memories,
    forget_memory,
    notebook_run,
    notebook_reset,
    notebook_vars,
    create_docx,
    create_xlsx,
    create_pptx,
    create_pdf,
    todo_add,
    todo_list,
    todo_complete,
    todo_update,
    todo_filter,
    list_skills,
    invoke_skill,
    skill_view,
    skill_manage,
    render_interactive_block,
    ask_user,
]

# Dedicated Study Tools (Only active in Study mode or study toolbox)
STUDY_TOOLS: list = [
    course_register,
    course_list,
    course_get,
    course_workspace_create,
    course_chat_create,
    study_note_save,
    study_note_search,
    study_note_delete,
    flashcard_deck_create,
    flashcard_review,
    flashcard_suggest,
    flashcard_import,
    flashcard_export,
    quiz_session_start,
    quiz_session_answer,
    quiz_session_results,
    mastery_record,
    study_session_log,
    study_weak_areas,
    export_study_sheet,
]


def _is_packaged_build() -> bool:
    return os.environ.get("OWLYNN_PACKAGED") == "1"


_PENTEST_TOOLBOX: list = [
    *PENTEST_TOOLS,
    *PENTEST_NETWORK_TOOLS,
    *PENTEST_WEB_TOOLS,
    *PENTEST_VULN_TOOLS,
    *PENTEST_EXPLOIT_TOOLS,
    *PENTEST_POST_TOOLS,
    *PENTEST_OSINT_TOOLS,
    *PENTEST_AD_TOOLS,
    *PENTEST_PASSWORD_TOOLS,
    *PENTEST_CLOUD_TOOLS,
    *PENTEST_REPORTING_TOOLS,
    # File ops
    read_workspace_file,
    write_workspace_file,
    edit_workspace_file,
    list_workspace_files,
    delete_workspace_file,
    download_to_workspace,
    # Screen assist / Kali
    *SCREEN_ASSIST_TOOLS,
    # Web (recon)
    web_search,
    fetch_webpage,
    deep_research,
    browser_background_fetch,
    # Report generation
    create_pdf,
    create_docx,
    # Data analysis
    notebook_run,
    notebook_reset,
    notebook_vars,
    # Task tracking
    todo_add,
    todo_list,
    todo_complete,
    todo_update,
    todo_filter,
    # Skills
    list_skills,
    invoke_skill,
]


# ─── Dynamic Tool Loading: Toolbox Registry ─────────────────────────────
TOOLBOX_REGISTRY: dict[str, list] = {
    "web_search": [web_search, fetch_webpage, deep_research, browser_background_fetch],
    "file_ops": [
        read_workspace_file,
        write_workspace_file,
        edit_workspace_file,
        list_workspace_files,
        delete_workspace_file,
        download_to_workspace,
    ],
    "data_connectors": [
        ingest_github_repo,
        ingest_youtube_transcript,
        ingest_obsidian_vault,
    ],
    "data_viz": [
        create_docx,
        create_xlsx,
        create_pptx,
        create_pdf,
        notebook_run,
        notebook_reset,
        notebook_vars,
        read_ipynb,
        write_ipynb,
        export_ipynb_html,
    ],
    "productivity": [
        todo_add,
        todo_list,
        todo_complete,
        todo_update,
        todo_filter,
        list_skills,
        invoke_skill,
        render_interactive_block,
    ],
    "study": list(STUDY_TOOLS),
    "memory": [
        recall_memories,
        recall_all_memories,
        forget_memory,
    ],
    "screen_assist": list(
        NORMAL_SCREEN_ASSIST_TOOLS if _is_packaged_build() else SCREEN_ASSIST_TOOLS
    ),
    # MCP tools are loaded at runtime from mcp_config.json — see merge_mcp_tools()
    "mcp": [],
}

if not _is_packaged_build():
    TOOLBOX_REGISTRY["pentest"] = _PENTEST_TOOLBOX

# Auto-register all tools into global ToolRegistry
from src.tools.registry import registry

for _tb_name, _tb_tools in TOOLBOX_REGISTRY.items():
    for _tool in _tb_tools:
        registry.register_tool_instance(_tool, toolbox=_tb_name)

ALWAYS_INCLUDED_TOOLS: list = [ask_user]
registry.register_tool_instance(ask_user, toolbox=["all", "default"])


def should_include_mcp_tools(toolbox_names: list[str] | None) -> bool:
    """Whether MCP extension tools should be merged for this toolbox selection."""
    from src.config.config_loader import config

    if not config.get("mcp.enabled", True):
        return False
    names = list(toolbox_names or [])
    if not names or "all" in names:
        return bool(config.get("mcp.include_on_all", True))
    return "mcp" in names


def merge_mcp_tools(
    tools: list,
    *,
    toolbox_names: list[str] | None = None,
    query: str | None = None,
) -> list:
    """Append LangChain tools discovered from mcp_config.json (deduped by name).

    Caps merged MCP tools to ``mcp.max_tools_per_turn``, preferring tools whose
    names overlap query keywords when a query is provided.
    """
    if not should_include_mcp_tools(toolbox_names):
        return tools
    from src.config.config_loader import config
    from src.tools.mcp_client import get_mcp_tools

    mcp_tools = get_mcp_tools()
    if not mcp_tools:
        return tools

    max_mcp = int(config.get("mcp.max_tools_per_turn", 8))
    if max_mcp > 0 and len(mcp_tools) > max_mcp:
        mcp_tools = _prefer_mcp_tools_for_query(mcp_tools, query, max_mcp)

    seen = {getattr(t, "name", "") for t in tools}
    merged = list(tools)
    for tool in mcp_tools:
        name = getattr(tool, "name", "")
        if name and name not in seen:
            seen.add(name)
            merged.append(tool)
    return merged


def _prefer_mcp_tools_for_query(
    mcp_tools: list, query: str | None, max_count: int
) -> list:
    """Prefer MCP tools whose names match query keywords; fill remainder alphabetically."""
    if not query or not str(query).strip():
        return sorted(mcp_tools, key=lambda t: getattr(t, "name", str(t)))[:max_count]

    tokens = {t.lower() for t in str(query).split() if len(t) > 2}
    scored: list[tuple[int, str, object]] = []
    for tool in mcp_tools:
        name = getattr(tool, "name", "") or ""
        name_l = name.lower()
        hit = sum(1 for tok in tokens if tok in name_l)
        scored.append((-hit, name_l, tool))
    scored.sort()
    return [t for _, _, t in scored[:max_count]]


def resolve_tools(toolbox_names: list[str], web_search_enabled: bool = True) -> list:
    """
    Return the union of tools from requested toolboxes + always-included tools.

    - "all" in toolbox_names → full tool set (equivalent to COMPLEX_TOOLS_WITH_WEB/NO_WEB)
    - web_search_enabled=False → exclude web_search toolbox tools even if requested
    - ask_user is always included regardless of selection
    - MCP extension tools merged when enabled (see defaults.yaml mcp.*)
    """
    if not toolbox_names or "all" in toolbox_names:
        base = list(
            COMPLEX_TOOLS_WITH_WEB if web_search_enabled else COMPLEX_TOOLS_NO_WEB
        )
        for t in ALWAYS_INCLUDED_TOOLS:
            if t not in base:
                base.append(t)
        return merge_mcp_tools(base, toolbox_names=toolbox_names or ["all"])

    tools: list = []
    seen_ids: set = set()
    web_tool_ids = set(id(t) for t in TOOLBOX_REGISTRY.get("web_search", []))
    for name in toolbox_names:
        if name == "web_search" and not web_search_enabled:
            continue
        if name == "mcp":
            continue
        if name in TOOLBOX_REGISTRY:
            for t in TOOLBOX_REGISTRY[name]:
                tid = id(t)
                if tid not in seen_ids:
                    # Skip web tools when web is disabled (even if embedded in pentest box)
                    if not web_search_enabled and tid in web_tool_ids:
                        continue
                    seen_ids.add(tid)
                    tools.append(t)

    for t in ALWAYS_INCLUDED_TOOLS:
        if id(t) not in seen_ids:
            seen_ids.add(id(t))
            tools.append(t)

    return merge_mcp_tools(tools, toolbox_names=toolbox_names)


def all_complex_tools(web_search_enabled: bool = True) -> list:
    """Built-in complex tools plus MCP extensions (for tool-loop replay)."""
    base = list(COMPLEX_TOOLS_WITH_WEB if web_search_enabled else COMPLEX_TOOLS_NO_WEB)
    return merge_mcp_tools(base, toolbox_names=["all"])
