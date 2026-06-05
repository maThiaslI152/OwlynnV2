"""
RAG Tools — Automatic Document Indexing & Retrieval
===================================================

Provides the tool set for targeted semantic search over indexed documents in the active project workspace.
"""

from langchain_core.tools import tool
import logging
from src.tools.workspace_context import _active_project_id

logger = logging.getLogger(__name__)


@tool
def search_workspace_docs(query: str) -> str:
    """
    Performs a deep semantic vector search over all indexed workspace documents
    (PDF, DOCX, XLSX, Markdown, code files) within the active project workspace.
    Use this when you need to answer specific questions about files in the workspace
    or retrieve content matching a concept.

    Args:
        query: Semantic query text or specific question to search for.
    """
    try:
        from src.memory.long_term import memory as mem0_memory
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return "Error: Mem0 memory not available."

    if mem0_memory is None:
        return "Error: Mem0/Qdrant vector memory is not initialized."

    try:
        project_id = _active_project_id.get() or "default"
        user_id = f"project:{project_id}"

        # Search the project vector store (Qdrant)
        results_dict = mem0_memory.search(query, filters={"user_id": user_id}, limit=8)
        results = (
            results_dict.get("results", [])
            if isinstance(results_dict, dict)
            else results_dict
        )

        if not results:
            return f"No matching workspace document content found for: '{query}'"

        lines = [f"📚 Found relevant document sections in workspace '{project_id}':"]
        for item in results:
            if isinstance(item, dict):
                memory_text = item.get("memory", item.get("text", ""))
                metadata = item.get("metadata", {})
                filename = metadata.get("filename", "unknown file")
                lines.append(f"\n📄 From: {filename}")
                lines.append(f"   {memory_text}")
        return "\n".join(lines)
    except Exception as e:
        logger.error("Error searching workspace documents: %s", e)
        return f"Error searching workspace documents: {e}"
