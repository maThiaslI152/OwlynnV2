"""
FastAPI Routes for Thought Graph & Mindmap Canvas.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from src.memory.thought_graph import thought_graph_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/graph", tags=["thought_graph"])


@router.get("/data")
async def api_get_graph_data(mode: str | None = None) -> dict[str, Any]:
    """Get all thought nodes and valid edges for the Mindmap Canvas."""
    try:
        if mode == "pentest":
            raise HTTPException(
                status_code=400,
                detail="Pentest graph data must be requested from pentest-specific endpoints",
            )
        data = await thought_graph_manager.get_graph_data(mode=mode)
        return {"status": "ok", **data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[graph_api] Failed to get graph data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nodes")
async def api_create_node(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new thought node or branch."""
    node_id = body.get("id")
    if not node_id:
        import uuid

        node_id = f"thread-{uuid.uuid4().hex[:12]}"

    title = body.get("title", "New Thought")
    mode = body.get("mode", "normal")
    parent_id = body.get("parent_id")
    scenario_id = body.get("scenario_id")
    engagement_id = body.get("engagement_id")
    course_id = body.get("course_id")
    tags = body.get("tags", [])

    try:
        if mode == "pentest" or scenario_id == "pentest":
            raise HTTPException(
                status_code=400,
                detail="Pentest graph nodes are managed through pentest engagement APIs",
            )
        node = await thought_graph_manager.get_or_create_node(
            node_id=node_id,
            title=title,
            mode=mode,
            scenario_id=scenario_id,
            engagement_id=engagement_id,
            course_id=course_id,
            tags=tags,
        )

        # If branched from a parent node, automatically establish a branches_to edge
        if parent_id and parent_id != node_id:
            await thought_graph_manager.create_edge(
                source_id=parent_id,
                target_id=node_id,
                relation="branches_to",
                weight=1.0,
                auto_generated=False,
            )

        return {"status": "ok", "node": node}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[graph_api] Failed to create node: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes/{node_id}")
async def api_get_node(node_id: str) -> dict[str, Any]:
    """Get a specific thought node."""
    try:
        node = await thought_graph_manager.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Thought node not found")
        return {"status": "ok", "node": node}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[graph_api] Failed to get node %s: %s", node_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/nodes/{node_id}")
async def api_update_node(node_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update node properties (title, summary, canvas_x, canvas_y, pinned, etc.)."""
    try:
        node = await thought_graph_manager.update_node(node_id, **body)
        if not node:
            raise HTTPException(status_code=404, detail="Thought node not found")
        return {"status": "ok", "node": node}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[graph_api] Failed to update node %s: %s", node_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/nodes/{node_id}")
async def api_delete_node(node_id: str) -> dict[str, Any]:
    """Delete a thought node and its connected edges."""
    try:
        success = await thought_graph_manager.delete_node(node_id)
        if not success:
            raise HTTPException(status_code=404, detail="Thought node not found")
        return {"status": "ok", "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[graph_api] Failed to delete node %s: %s", node_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/edges")
async def api_create_edge(body: dict[str, Any]) -> dict[str, Any]:
    """Manually link two thought nodes."""
    source_id = body.get("source") or body.get("source_id")
    target_id = body.get("target") or body.get("target_id")
    relation = body.get("relation", "relates_to")
    weight = float(body.get("weight", 1.0))

    if not source_id or not target_id:
        raise HTTPException(status_code=400, detail="Missing source or target node ID")

    try:
        edge = await thought_graph_manager.create_edge(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=weight,
            auto_generated=False,
        )
        return {"status": "ok", "edge": edge}
    except Exception as e:
        logger.error("[graph_api] Failed to create edge: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
