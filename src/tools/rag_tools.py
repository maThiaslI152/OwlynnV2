"""
RAG Tools — Automatic Document Indexing & Retrieval
===================================================

Provides the tool set for targeted semantic search over indexed documents in the active project workspace.
"""

from langchain_core.tools import tool
import logging
import os
from src.tools.workspace_context import _active_project_id
from src.config.settings import get_project_workspace

logger = logging.getLogger(__name__)


def _keyword_search_local(project_id: str, query: str, limit: int = 5) -> list[dict]:
    """Helper to perform BM25 keyword searches inside processed files."""
    import math
    from collections import Counter

    project_workspace = get_project_workspace(project_id)
    processed_dir = os.path.join(project_workspace, ".processed")

    if not os.path.exists(processed_dir):
        return []

    query_lower = query.lower().strip()
    query_words = [w.strip() for w in query_lower.split() if len(w.strip()) >= 3]
    if not query_words and not query_lower:
        return []

    # 1. Parse corpus and build paragraphs
    corpus_paragraphs = []
    for f in os.listdir(processed_dir):
        if not f.endswith((".txt", ".md")):
            continue
        filepath = os.path.join(processed_dir, f)
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as src:
                content = src.read()
        except Exception:
            continue

        filename = os.path.splitext(f)[0]
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in content.split("\n") if p.strip()]

        for p in paragraphs:
            corpus_paragraphs.append(
                {"text": p, "filename": filename, "words": p.lower().split()}
            )

    N = len(corpus_paragraphs)
    if N == 0:
        return []

    # 2. Compute BM25 statistics
    avgdl = sum(len(doc["words"]) for doc in corpus_paragraphs) / N
    k1 = 1.2
    b = 0.75

    # Document frequencies for each query word
    df = Counter()
    for doc in corpus_paragraphs:
        doc_words_set = set(doc["words"])
        for qw in query_words:
            # simple substring or exact match check for the word in the document words
            if any(qw in dw for dw in doc_words_set):
                df[qw] += 1

    # IDF for each query word
    idf = {}
    for qw in query_words:
        n_q = df[qw]
        # Standard BM25 IDF formula
        idf[qw] = math.log(((N - n_q + 0.5) / (n_q + 0.5)) + 1.0)

    # 3. Score documents
    hits = []
    for doc in corpus_paragraphs:
        score = 0.0
        doc_len = len(doc["words"])
        if doc_len == 0:
            continue

        doc_words_counter = Counter(doc["words"])

        for qw in query_words:
            # Term frequency (allow substring matches for partial keywords)
            f_q_d = sum(count for dw, count in doc_words_counter.items() if qw in dw)
            if f_q_d > 0:
                numerator = f_q_d * (k1 + 1)
                denominator = f_q_d + k1 * (1 - b + b * (doc_len / avgdl))
                score += idf[qw] * (numerator / denominator)

        # Bonus for exact substring match of the full query
        if query_lower in doc["text"].lower():
            score += 5.0

        if score > 0:
            hits.append(
                {
                    "memory": doc["text"],
                    "metadata": {
                        "filename": doc["filename"],
                        "source": "bm25",
                    },
                    "score": score,
                }
            )

    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits[:limit]


@tool
def search_workspace_docs(query: str) -> str:
    """
    Performs a deep hybrid semantic search (vector + keyword matching) over all
    indexed workspace documents (PDF, DOCX, XLSX, Markdown, code files)
    within the active project workspace.
    Use this when you need to answer specific questions about files in the workspace
    or retrieve content matching a concept.

    Args:
        query: Semantic query text or specific question/keyword to search for.
    """
    try:
        from src.memory.long_term import memory as mem0_memory
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return "Error: Mem0 memory not available."

    try:
        project_id = _active_project_id.get() or "default"
        user_id = f"project:{project_id}"

        # 1. Vector semantic search (Qdrant)
        vector_hits = []
        if mem0_memory is not None:
            try:
                results_dict = mem0_memory.search(
                    query, filters={"user_id": user_id}, limit=8
                )
                vector_hits = (
                    results_dict.get("results", [])
                    if isinstance(results_dict, dict)
                    else results_dict
                )
            except Exception as e:
                logger.warning("Mem0 vector search failed: %s", e)

        # 2. Local exact keyword scan
        keyword_hits = _keyword_search_local(project_id, query, limit=8)

        # 3. Fuse and deduplicate
        merged = {}
        for rank, item in enumerate(vector_hits):
            text = item.get("memory", item.get("text", ""))
            filename = item.get("metadata", {}).get("filename", "unknown file")
            key = (filename, text[:150].strip())
            merged[key] = {
                "memory": text,
                "metadata": item.get("metadata", {}),
                "vector_rank": rank + 1,
                "keyword_score": 0.0,
            }

        for item in keyword_hits:
            text = item["memory"]
            filename = item["metadata"]["filename"]
            key = (filename, text[:150].strip())
            if key in merged:
                merged[key]["keyword_score"] = item["score"]
            else:
                merged[key] = {
                    "memory": text,
                    "metadata": item["metadata"],
                    "vector_rank": None,
                    "keyword_score": item["score"],
                }

        # Calculate final fused scores
        scored_items = []
        for key, val in merged.items():
            score = 0.0
            if val["vector_rank"] is not None:
                score += 1.0 / (val["vector_rank"] + 60)
            if val["keyword_score"] > 0:
                score += val["keyword_score"] * 0.05
            scored_items.append((score, val))

        scored_items.sort(key=lambda x: x[0], reverse=True)
        final_results = [item for _, item in scored_items[:8]]

        if not final_results:
            return f"No matching workspace document content found for: '{query}'"

        lines = [f"📚 Found relevant document sections in workspace '{project_id}':"]
        for item in final_results:
            memory_text = item.get("memory", "")
            metadata = item.get("metadata", {})
            filename = metadata.get("filename", "unknown file")
            source = metadata.get("source", "vector_search")
            lines.append(f"\n📄 From: {filename} (source: {source})")
            lines.append(f"   {memory_text}")
        return "\n".join(lines)
    except Exception as e:
        logger.error("Error searching workspace documents: %s", e)
        return f"Error searching workspace documents: {e}"
