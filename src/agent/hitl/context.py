"""
HITL context builder — shared helper used by router, plan_review, security_proxy,
and scope_clarify to build enriched interrupt payloads.
"""

from typing import Any
from langchain_core.messages import HumanMessage, AIMessage

# Map tool names to human-readable action descriptions
_TOOL_ACTION_LABELS = {
    "write_workspace_file": "write to file",
    "edit_workspace_file": "edit file",
    "delete_workspace_file": "delete file",
    "notebook_run": "run Python code",
    "web_search": "search the web",
    "fetch_webpage": "fetch a web page",
    "read_workspace_file": "read a file",
    "list_workspace_files": "list files",
    "recall_memories": "recall memories",
    "recall_all_memories": "recall all memories",
    "search_workspace_docs": "search documentation",
    "notebook_reset": "reset Python REPL",
    "create_docx": "create a Word document",
    "create_xlsx": "create a spreadsheet",
    "create_pptx": "create a PowerPoint",
    "create_pdf": "create a PDF",
    "ask_user": "ask you a question",
    "todo_add": "add a task",
    "todo_list": "list tasks",
    "todo_complete": "complete a task",
    "list_skills": "list available skills",
    "invoke_skill": "run a skill",
    "forget_memory": "forget a memory",
}


def build_hitl_context(state: dict) -> dict[str, Any]:
    """Extract conversation context fields for HITL interrupt enrichment.

    Returns a dict with keys usable across all interrupt types:
    - conversation_snippet: Last user + last assistant message (truncated)
    - stated_intent: Tool-aware description derived from pending tool calls + args
    - affected_resources: Parsed paths from tool args
    """
    messages = list(state.get("messages") or [])

    # Last user and assistant messages for snippet
    last_user = ""
    last_assistant = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and not last_user:
            last_user = _truncate(str(msg.content), 200)
        elif isinstance(msg, AIMessage) and not last_assistant:
            last_assistant = _truncate(str(msg.content), 200)
        if last_user and last_assistant:
            break

    snippet = f"User: {last_user}\nOwlynn: {last_assistant}" if last_user or last_assistant else ""

    # Stated intent from tool calls (more accurate than last AI content)
    intent = _build_intent_from_tool_calls(messages)

    # Affected resources from pending tool calls
    affected = _extract_affected_resources(messages)

    return {
        "conversation_snippet": snippet,
        "stated_intent": intent,
        "affected_resources": affected,
    }


def enrich_interrupt(interrupt_payload: dict, state: dict) -> dict:
    """Attach conversation context fields to an interrupt payload dict."""
    ctx = build_hitl_context(state)
    enriched = dict(interrupt_payload)
    if ctx["conversation_snippet"]:
        enriched.setdefault("conversation_snippet", ctx["conversation_snippet"])
    if ctx["stated_intent"]:
        enriched.setdefault("stated_intent", ctx["stated_intent"])
    if ctx["affected_resources"]:
        enriched.setdefault("affected_resources", ctx["affected_resources"])
    return enriched


def _build_intent_from_tool_calls(messages: list) -> str:
    """Build a tool-aware intent description from pending tool calls.

    Preferred over the old heuristic of extracting from last AI content
    because tool names + args give a much more accurate picture of intent.
    """
    import json

    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            continue

        descriptions = []
        for call in tool_calls[:3]:  # max 3 tools in intent
            name = str(call.get("name", ""))
            args = call.get("args", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}

            label = _TOOL_ACTION_LABELS.get(name, name.replace("_", " "))

            # Extract primary resource argument
            resource = ""
            if isinstance(args, dict):
                for key in ("path", "file_path", "filename", "name", "file_name",
                            "target", "source_path", "question", "query", "url"):
                    val = args.get(key)
                    if val:
                        resource = str(val)
                        if len(resource) > 60:
                            resource = resource[:57] + "..."
                        break

            if resource:
                descriptions.append(f"{label} {resource}")
            else:
                descriptions.append(label)

        if descriptions:
            return "Owlynn wants to " + "; ".join(descriptions)

    # Fallback: use last AI content
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = str(msg.content or "")
            return f"Owlynn wants to {_truncate(content, 150)}" if content.strip() else ""

    return ""


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _extract_affected_resources(messages: list) -> list[str]:
    """Extract file paths from pending tool call args."""
    import json
    paths = []
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None) or []
        for call in tool_calls:
            args = call.get("args", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(args, dict):
                for key in ("path", "file_path", "source_path", "target_path"):
                    if key in args:
                        paths.append(str(args[key]))
        if paths:
            break
    return paths[:10]
