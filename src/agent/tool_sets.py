"""Toolbox registry and tool binding for the complex path.

See docs/TOOLS.md; implement tools in src/tools/ and register here.
"""

from src.tools.web_tools import (
    web_search,
    fetch_webpage,
    deep_research,
    browser_background_fetch,
)
from src.tools.core_tools import (
    read_workspace_file,
    write_workspace_file,
    edit_workspace_file,
    list_workspace_files,
    delete_workspace_file,
    download_to_workspace,
)
from src.tools.core_tools import recall_memories, recall_all_memories, forget_memory
from src.tools.doc_generator import create_docx, create_xlsx, create_pptx, create_pdf
from src.tools.notebook import notebook_run, notebook_reset, notebook_vars
from src.tools.interactive_content import render_interactive_block
from src.tools.ipynb_tools import read_ipynb, write_ipynb, export_ipynb_html
from src.tools.todo import todo_add, todo_list, todo_complete, todo_update, todo_filter
from src.tools.ask_user import ask_user
from src.tools.skills import list_skills, invoke_skill
from src.tools.study_tools import (
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
)
from src.tools.rag_tools import search_workspace_docs
from src.tools.screen_assist.tools import SCREEN_ASSIST_TOOLS

# Full tool set with web search enabled
COMPLEX_TOOLS_WITH_WEB: list = [
    # Web
    web_search,
    fetch_webpage,
    browser_background_fetch,
    deep_research,
    # File management
    read_workspace_file,
    write_workspace_file,
    edit_workspace_file,
    list_workspace_files,
    delete_workspace_file,
    download_to_workspace,
    # Memory
    recall_memories,
    recall_all_memories,
    forget_memory,
    search_workspace_docs,
    # Computation
    notebook_run,
    notebook_reset,
    notebook_vars,
    read_ipynb,
    write_ipynb,
    export_ipynb_html,
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
    render_interactive_block,
    # Study PA
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
    # Screen assist / browser bridge
    *SCREEN_ASSIST_TOOLS,
    # HITL
    ask_user,
]

# Tool set without web search
COMPLEX_TOOLS_NO_WEB: list = [
    read_workspace_file,
    write_workspace_file,
    edit_workspace_file,
    list_workspace_files,
    delete_workspace_file,
    download_to_workspace,
    recall_memories,
    recall_all_memories,
    forget_memory,
    search_workspace_docs,
    notebook_run,
    notebook_reset,
    notebook_vars,
    read_ipynb,
    write_ipynb,
    export_ipynb_html,
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
    render_interactive_block,
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
    # Screen assist / browser bridge
    *SCREEN_ASSIST_TOOLS,
    ask_user,
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
    "study": [
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
        render_interactive_block,
    ],
    "memory": [
        recall_memories,
        recall_all_memories,
        forget_memory,
        search_workspace_docs,
    ],
    "screen_assist": list(SCREEN_ASSIST_TOOLS),
    # MCP tools are loaded at runtime from mcp_config.json — see merge_mcp_tools()
    "mcp": [],
}

ALWAYS_INCLUDED_TOOLS: list = [ask_user]


def should_include_mcp_tools(toolbox_names: list[str] | None) -> bool:
    """Whether MCP extension tools should be merged for this toolbox selection."""
    from src.config.config_loader import config

    if not config.get("mcp.enabled", True):
        return False
    names = list(toolbox_names or [])
    if not names or "all" in names:
        return bool(config.get("mcp.include_on_all", True))
    return "mcp" in names


def merge_mcp_tools(tools: list, *, toolbox_names: list[str] | None = None) -> list:
    """Append LangChain tools discovered from mcp_config.json (deduped by name)."""
    if not should_include_mcp_tools(toolbox_names):
        return tools
    from src.tools.mcp_client import get_mcp_tools

    mcp_tools = get_mcp_tools()
    if not mcp_tools:
        return tools
    seen = {getattr(t, "name", "") for t in tools}
    merged = list(tools)
    for tool in mcp_tools:
        name = getattr(tool, "name", "")
        if name and name not in seen:
            seen.add(name)
            merged.append(tool)
    return merged


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
    for name in toolbox_names:
        if name == "web_search" and not web_search_enabled:
            continue
        if name == "mcp":
            continue
        if name in TOOLBOX_REGISTRY:
            for t in TOOLBOX_REGISTRY[name]:
                tid = id(t)
                if tid not in seen_ids:
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
