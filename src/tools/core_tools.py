"""
Core Tools — File Operations, Memory Recall, and Workspace Management
======================================================================

Provides the fundamental tool set for the agent:

- **read_workspace_file**: Read files with smart truncation (20K char cap).
  Checks ``.processed/`` cache first for pre-extracted content (PDF, DOCX, etc.).
- **write_workspace_file**: Write/overwrite files in the project workspace.
- **edit_workspace_file**: Search-and-replace within a file.
- **list_workspace_files**: Directory listing with file sizes.
- **delete_workspace_file**: Remove a file from the workspace.
- **recall_memories**: Keyword search against JSON-based long-term memory.

All file operations are sandboxed to the active project workspace via
``get_safe_workspace_path()``, which prevents path traversal attacks.
"""

import os
import re
from langchain_core.tools import tool
from ..memory.memory_manager import search_memories
from ..config.settings import WORKSPACE_DIR as _WORKSPACE_PATH
from .workspace_context import tool_workspace_root

import logging

logger = logging.getLogger(__name__)
BASE_WORKSPACE_DIR = str(_WORKSPACE_PATH.resolve())


def _normalize_workspace_filename(filename: str) -> str:
    """Strip chat/LLM wrappers so tool args match on-disk names."""
    fn = (filename or "").strip().strip("`\"'")
    attached = re.match(r"^\[Attached:\s*(.+?)\s*\]$", fn, re.IGNORECASE)
    if attached:
        fn = attached.group(1).strip()
    if fn.lower().startswith("attached:"):
        fn = fn.split(":", 1)[1].strip()
    return fn.lstrip("/")


def get_safe_workspace_path(filename: str) -> tuple[str, str | None]:
    """Resolve a path inside the active project workspace."""
    filename = _normalize_workspace_filename(filename)
    if ".." in filename or filename.startswith("~"):
        return (
            "",
            "Error: Access denied. Path traversal or absolute home paths are not allowed.",
        )

    filename = filename.lstrip("/")
    if filename.startswith("workspace/"):
        filename = filename[len("workspace/") :]
    if filename.startswith("projects/"):
        workspace_root = BASE_WORKSPACE_DIR
    else:
        workspace_root = tool_workspace_root()

    filepath = os.path.realpath(os.path.join(workspace_root, filename))
    root_abs = os.path.realpath(workspace_root)
    base_abs = os.path.realpath(BASE_WORKSPACE_DIR)

    # Symlink protection: ensure the resolved path is strictly within the allowed root
    if not filepath.startswith(root_abs) or not filepath.startswith(base_abs):
        return "", "Error: Access denied. Path is outside workspace."
    return filepath, None


@tool
def read_workspace_file(filename: str) -> str:
    """Reads the content of a file in the workspace."""
    filepath, err = get_safe_workspace_path(filename)
    if err:
        return err
    if not os.path.exists(filepath):
        try:
            fn = os.path.basename(filepath)
            search_dir = os.path.dirname(filepath) or tool_workspace_root()
            # Only match files that START with the requested name (prefix match)
            # to avoid accidentally opening unrelated files like "test_results_confidential.csv"
            # when the user asked for "test".
            matches = [
                f
                for f in os.listdir(search_dir)
                if f.startswith(fn) or fn.startswith(f)
            ]
            if len(matches) == 1:
                filepath = os.path.join(search_dir, matches[0])
            elif matches:
                return f"Error: File '{filename}' not found. Did you mean one of: {', '.join(sorted(matches)[:5])}?"
            else:
                return f"Error: File '{filename}' not found."
        except Exception as e:
            logger.warning("Error suppressed: %s", e)
            return f"Error: File '{filename}' not found."

    processed_dir = os.path.join(tool_workspace_root(), ".processed")
    fn_only = os.path.basename(filepath)
    cached_txt = os.path.join(processed_dir, fn_only + ".txt")
    cached_md = os.path.join(processed_dir, fn_only + ".md")

    try:
        if os.path.exists(cached_txt):
            with open(cached_txt, "r", encoding="utf-8") as f:
                content = f.read()
        elif os.path.exists(cached_md):
            with open(cached_md, "r", encoding="utf-8") as f:
                content = f.read()
        elif filepath.lower().endswith(".pdf"):
            from src.pdf.intake import extract_pdf_text_from_path

            content = extract_pdf_text_from_path(filepath)
            if not content.strip():
                return "This PDF has no extractable text layer."
        elif filepath.lower().endswith(".docx"):
            from src.api.shared import extract_docx_text

            with open(filepath, "rb") as f:
                raw_bytes = f.read()
            content = extract_docx_text(raw_bytes)
            if not content.strip():
                return "This DOCX has no extractable text."
        elif filepath.lower().endswith(".doc"):
            from src.api.shared import extract_doc_text

            with open(filepath, "rb") as f:
                raw_bytes = f.read()
            content = extract_doc_text(raw_bytes)
            if not content.strip():
                return "This DOC has no extractable text."
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        # Smart truncation for large files — keep enough for the model to
        # understand the structure, then tell it to use notebook_run for full data.
        from src.config.config_loader import config

        _MAX_READ_CHARS = int(config.get("tool_output.max_read_chars", 20000))
        if len(content) > _MAX_READ_CHARS:
            ext = os.path.splitext(filepath)[1].lower()
            if ext in {".csv", ".tsv"}:
                # For tabular data: show header + first rows + summary
                lines = content.split("\n")
                header_and_sample = "\n".join(lines[:25])
                content = (
                    f"{header_and_sample}\n\n"
                    f"[... {len(lines)} total rows. Showing first 25. "
                    f"Use notebook_run with pandas to analyze the full dataset at: "
                    f'pd.read_csv(f"{{WORKSPACE_DIR}}/{os.path.basename(filepath)}")]'
                )
            else:
                content = (
                    content[:_MAX_READ_CHARS]
                    + f"\n\n[... truncated at {_MAX_READ_CHARS} chars. "
                    f"Full file is {len(content)} chars. Use notebook_run for full processing.]"
                )

        return content
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return f"Error reading file {filename}: {e}"


@tool
def write_workspace_file(filename: str, content: str) -> str:
    """Writes content to a file in the workspace. Overwrites if it exists."""
    filepath, err = get_safe_workspace_path(filename)
    if err:
        return err
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ Written to {filename}"
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return f"Error writing file: {e}"


@tool
def edit_workspace_file(
    filename: str, search_pattern: str, replacement_text: str
) -> str:
    """
    Search-and-replace in a workspace file. The search_pattern must match exactly.

    Args:
        filename: Path to the file.
        search_pattern: Exact text to find.
        replacement_text: Text to replace it with.
    """
    filepath, err = get_safe_workspace_path(filename)
    if err:
        return err
    if not os.path.exists(filepath):
        return f"Error: File '{filename}' not found."
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        if search_pattern not in content:
            return f"Error: Pattern not found in {filename}."
        count = content.count(search_pattern)
        new_content = content.replace(search_pattern, replacement_text, 1)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        suffix = f" ({count} occurrences found, replaced first)" if count > 1 else ""
        return f"✅ Updated {filename}{suffix}"
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return f"Error editing file: {e}"


@tool
def list_workspace_files(directory: str = ".") -> str:
    """Lists files in a workspace directory."""
    target_dir, err = get_safe_workspace_path(directory)
    if err:
        return err
    if not os.path.exists(target_dir):
        return f"Error: Directory '{directory}' not found."
    try:
        files = sorted(f for f in os.listdir(target_dir) if not f.startswith("."))
        if not files:
            return "Directory is empty."
        lines = []
        for f in files:
            fp = os.path.join(target_dir, f)
            if os.path.isdir(fp):
                lines.append(f"📁 {f}/")
            else:
                size = os.path.getsize(fp)
                lines.append(f"📄 {f} ({size:,} bytes)")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return f"Error listing files: {e}"


@tool
def delete_workspace_file(filename: str) -> str:
    """Deletes a file from the workspace."""
    filepath, err = get_safe_workspace_path(filename)
    if err:
        return err
    if not os.path.exists(filepath):
        return f"Error: File '{filename}' not found."
    try:
        os.remove(filepath)
        return f"✅ Deleted {filename}"
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return f"Error deleting file: {e}"


@tool
def recall_memories(query: str) -> str:
    """
    Searches long-term memory for facts about the user.

    Args:
        query: Topic or question to search for.
    """
    memories = search_memories(query, top_k=8)
    if not memories:
        return "No relevant memories found."
    lines = ["Relevant memories:"]
    for m in memories:
        lines.append(f"  - {m['fact']}  [{m['timestamp'][:10]}]")
    return "\n".join(lines)


@tool
def recall_all_memories(query: str = "", project_id: str = "") -> str:
    """
    Searches ALL long-term memory (including Mem0/Qdrant vector memory) for facts about the user.

    Use this when recall_memories returns nothing or you need deeper semantic search.

    Args:
        query: Optional search text. If empty, returns recent memories.
        project_id: Optional project ID to scope search (e.g. "my-project"). Leave empty for global.
    """
    try:
        from ..memory.long_term import memory as mem0_memory
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return "Error: Mem0 memory not available."

    if mem0_memory is None:
        return "Mem0/Qdrant vector memory is not initialized."

    try:
        from .workspace_context import _active_project_id

        active_pid = project_id or _active_project_id.get()
        user_id = (
            f"project:{active_pid}"
            if active_pid and active_pid != "default"
            else "owner"
        )
        search_query = query if query else " "
        results_dict = mem0_memory.search(
            search_query, filters={"user_id": user_id}, limit=20
        )
        results = (
            results_dict.get("results", [])
            if isinstance(results_dict, dict)
            else results_dict
        )

        if not results:
            return "No long-term memories found in vector store."

        lines = [f"Long-term memories from '{user_id}':"]
        for item in results:
            if isinstance(item, dict):
                memory_text = item.get("memory", item.get("text", ""))
                memory_id = item.get("id", "")
                lines.append(f"  [{memory_id}] {memory_text}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return f"Error searching vector memory: {e}"


@tool
def forget_memory(memory_hashes: str) -> str:
    """
    Deletes specific long-term memories by their IDs (hashes).

    Use recall_all_memories first to find the memory ID you want to delete.
    If you want to forget a specific fact, call this with the ID hash.

    Args:
        memory_hashes: Comma-separated list of memory IDs to delete (e.g. "abc123,def456").
    """
    try:
        from ..memory.long_term import memory as mem0_memory
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return "Error: Mem0 memory not available."

    if mem0_memory is None:
        return "Mem0/Qdrant vector memory is not initialized."

    ids = [h.strip() for h in memory_hashes.split(",") if h.strip()]
    if not ids:
        return "No valid memory IDs provided."

    deleted = 0
    errors = []
    for memory_id in ids:
        try:
            mem0_memory.delete(memory_id=memory_id)
            deleted += 1
        except Exception as e:
            logger.warning("Error suppressed: %s", e)
            errors.append(f"{memory_id}: {e}")

    result = f"Deleted {deleted}/{len(ids)} memories."
    if errors:
        result += f" Errors: {'; '.join(errors)}"
    return result
