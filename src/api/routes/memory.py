from fastapi import APIRouter

import logging

logger = logging.getLogger(__name__)
router = APIRouter()
from src.memory.memory_manager import load_memories, save_memory, delete_memory
from src.memory.long_term import memory as mem0_memory


@router.get("/api/memories")
async def api_get_memories():
    return load_memories()


@router.post("/api/memories")
async def api_add_memory(body: dict):
    fact = body.get("fact")
    if not fact:
        return {"status": "error", "message": "Fact required"}
    result = save_memory(fact)
    return {"status": "ok", "message": result, "memories": load_memories()}


@router.delete("/api/memories")
async def api_delete_memory(body: dict):
    fact = body.get("fact")
    if not fact:
        return {"status": "error", "message": "Fact required"}
    success = delete_memory(fact)
    return {"status": "ok" if success else "error", "memories": load_memories()}


# ─── Mem0 LTM API endpoints ──────────────────────────────────────────


@router.get("/api/mem0/search")
async def api_mem0_search(query: str = "", limit: int = 50, project_id: str = ""):
    """Search Mem0 long-term memory.

    - query: optional search text (empty returns recent memories)
    - limit: max results (default 50)
    - project_id: if provided, scopes search to that project's memory space;
      otherwise searches global ("owner") memory.
    """
    if mem0_memory is None:
        return {
            "status": "error",
            "message": "Mem0/Qdrant not available",
            "memories": [],
            "count": 0,
        }
    try:
        user_id = f"project:{project_id}" if project_id else "owner"
        # Use a broad query to retrieve memories; if empty, use a space to get recent ones
        search_query = query if query else " "
        results_dict = mem0_memory.search(
            search_query, filters={"user_id": user_id}, limit=limit
        )
        results = (
            results_dict.get("results", [])
            if isinstance(results_dict, dict)
            else results_dict
        )
        # Normalize: Mem0 results may have 'memory' or 'id' keys
        memories = []
        for item in results:
            if isinstance(item, dict):
                memories.append(
                    {
                        "id": item.get("id", ""),
                        "memory": item.get("memory", item.get("text", "")),
                        "text": item.get("memory", item.get("text", "")),
                        "created_at": item.get("created_at", ""),
                        "user_id": user_id,
                    }
                )
        return {"status": "ok", "memories": memories, "count": len(memories)}
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return {"status": "error", "message": str(e), "memories": [], "count": 0}


@router.get("/api/mem0/count")
async def api_mem0_count(project_id: str = ""):
    """Get the count of memories for a given user/project.

    - project_id: if provided, counts project-scoped memories
    """
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available", "count": 0}
    try:
        user_id = f"project:{project_id}" if project_id else "owner"
        # Search with a large limit to get all memories and count them
        results_dict = mem0_memory.search(" ", filters={"user_id": user_id}, limit=1000)
        results = (
            results_dict.get("results", [])
            if isinstance(results_dict, dict)
            else results_dict
        )
        count = len(results) if isinstance(results, list) else 0
        return {"status": "ok", "count": count, "user_id": user_id}
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return {"status": "error", "message": str(e), "count": 0}


@router.post("/api/mem0/delete")
async def api_mem0_delete(body: dict):
    """Delete a specific memory from Mem0 by its ID.

    Body: { "memory_id": "..." }
    """
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available"}
    try:
        memory_id = body.get("memory_id", "")
        if not memory_id:
            return {"status": "error", "message": "memory_id is required"}
        mem0_memory.delete(memory_id=memory_id)
        return {"status": "ok", "message": f"Deleted memory {memory_id}"}
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/api/mem0/clear")
async def api_mem0_clear(body: dict):
    """Clear all memories for a given user_id.

    Body: { "user_id": "owner" } (defaults to "owner")
    """
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available"}
    try:
        user_id = body.get("user_id", "owner")
        mem0_memory.delete_all(user_id=user_id)
        return (
            {"status": "ok", "message": f"Cleared all memories for {user_id}"}
            if user_id
            else {"status": "error", "message": "user_id required"}
        )
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/api/mem0/reset")
async def api_mem0_reset():
    """Reset ALL Mem0 memories (global). Use with caution."""
    if mem0_memory is None:
        return {"status": "error", "message": "Mem0/Qdrant not available"}
    try:
        mem0_memory.reset()
        return {"status": "ok", "message": "All Mem0 memories reset"}
    except Exception as e:
        logger.warning("Error suppressed: %s", e)
        return {"status": "error", "message": str(e)}
