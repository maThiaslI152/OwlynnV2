import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()
from src.memory.long_term import memory as mem0_memory
from src.memory.memory_manager import delete_memory, load_memories, save_memory

_LTM_UNAVAILABLE = "Long-term memory unavailable"


@router.get("/api/memories")
async def api_get_memories():
    return await load_memories()


@router.get("/api/templates/{template_id}")
async def api_get_template(template_id: str):
    from src.memory.ui_templates import get_ui_template

    tpl = await get_ui_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "ok", "template": tpl}


@router.post("/api/templates/cleanup")
async def api_cleanup_templates(body: dict = None):
    from src.memory.ui_templates import cleanup_old_templates

    days = 30
    if body and "days" in body:
        days = body["days"]
    deleted_count = await cleanup_old_templates(days)
    return {
        "status": "ok",
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} templates older than {days} days.",
    }


@router.post("/api/memories")
async def api_add_memory(body: dict):
    fact = body.get("fact")
    if not fact:
        return {"status": "error", "message": "Fact required"}
    result = await save_memory(fact)
    return {"status": "ok", "message": result, "memories": await load_memories()}


@router.delete("/api/memories")
async def api_delete_memory(body: dict):
    fact = body.get("fact")
    if not fact:
        return {"status": "error", "message": "Fact required"}
    success = await delete_memory(fact)
    return {"status": "ok" if success else "error", "memories": await load_memories()}


# ─── Long-term memory (pgvector) — canonical /api/memory/*, legacy /api/mem0/* ─


@router.get("/api/memory/search")
@router.get("/api/mem0/search")
async def api_memory_search(query: str = "", limit: int = 50, project_id: str = ""):
    """Search long-term memory (pgvector).

    - query: optional search text (empty returns recent memories)
    - limit: max results (default 50)
    - project_id: if provided, scopes search to that project's memory space;
      otherwise searches global ("owner") memory.
    """
    if mem0_memory is None:
        return {
            "status": "error",
            "message": _LTM_UNAVAILABLE,
            "memories": [],
            "count": 0,
        }
    try:
        user_id = f"project:{project_id}" if project_id else "owner"
        search_query = query if query else " "
        results_dict = mem0_memory.search(
            search_query, filters={"user_id": user_id}, limit=limit
        )
        results = (
            results_dict.get("results", [])
            if isinstance(results_dict, dict)
            else results_dict
        )
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
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/memory/count")
@router.get("/api/mem0/count")
async def api_memory_count(project_id: str = ""):
    """Get the count of memories for a given user/project."""
    if mem0_memory is None:
        return {"status": "error", "message": _LTM_UNAVAILABLE, "count": 0}
    try:
        user_id = f"project:{project_id}" if project_id else "owner"
        results_dict = mem0_memory.search(" ", filters={"user_id": user_id}, limit=1000)
        results = (
            results_dict.get("results", [])
            if isinstance(results_dict, dict)
            else results_dict
        )
        count = len(results) if isinstance(results, list) else 0
        return {"status": "ok", "count": count, "user_id": user_id}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/memory/add")
@router.post("/api/mem0/add")
async def api_memory_add(body: dict):
    """Manually add a memory.

    Body: { "memory": "fact text here", "user_id": "owner" }
    """
    if mem0_memory is None:
        return {"status": "error", "message": _LTM_UNAVAILABLE}
    try:
        memory_text = body.get("memory")
        if not memory_text:
            return {"status": "error", "message": "memory text is required"}
        user_id = body.get("user_id", "owner")
        mem0_memory.add(memory_text, user_id=user_id)
        return {"status": "ok", "message": f"Added memory for {user_id}"}
    except Exception as e:
        logger.error("Error adding memory: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/memory/delete")
@router.post("/api/mem0/delete")
async def api_memory_delete(body: dict):
    """Delete a specific memory by its ID.

    Body: { "memory_id": "..." }
    """
    if mem0_memory is None:
        return {"status": "error", "message": _LTM_UNAVAILABLE}
    try:
        memory_id = body.get("memory_id", "")
        if not memory_id:
            return {"status": "error", "message": "memory_id is required"}
        mem0_memory.delete(memory_id=memory_id)
        return {"status": "ok", "message": f"Deleted memory {memory_id}"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/memory/clear")
@router.post("/api/mem0/clear")
async def api_memory_clear(body: dict):
    """Clear all memories for a given user_id.

    Body: { "user_id": "owner" } (defaults to "owner")
    """
    if mem0_memory is None:
        return {"status": "error", "message": _LTM_UNAVAILABLE}
    try:
        user_id = body.get("user_id", "owner")
        mem0_memory.delete_all(user_id=user_id)
        return (
            {"status": "ok", "message": f"Cleared all memories for {user_id}"}
            if user_id
            else {"status": "error", "message": "user_id required"}
        )
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/memory/reset")
@router.post("/api/mem0/reset")
async def api_memory_reset():
    """Reset ALL long-term memories (global). Use with caution."""
    if mem0_memory is None:
        return {"status": "error", "message": _LTM_UNAVAILABLE}
    try:
        mem0_memory.reset()
        return {"status": "ok", "message": "All long-term memories reset"}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
