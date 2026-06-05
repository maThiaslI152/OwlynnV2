from fastapi import APIRouter

router = APIRouter()
from fastapi import Response
from fastapi import HTTPException
from src.agent.nodes.router import generate_chat_title_router_llm
import logging

logger = logging.getLogger(__name__)

from src.memory.project import project_manager
from src.memory.personal_assistant import (
    get_relevant_topics,
    get_user_interests_summary,
    load_conversations_history,
    track_topic,
    update_interests,
)


# Personal Assistant Endpoints - Topics, Interests, Conversation History


@router.get("/api/topics")
async def api_get_topics():
    """Get tracked topics with relevance scores and recency."""
    try:
        topics = get_relevant_topics(limit=10)
        return {"status": "ok", "topics": topics}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/interests")
async def api_get_interests():
    """Get detected interests with occurrence counts."""
    try:
        interests = get_user_interests_summary()
        return {"status": "ok", "interests": interests}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/conversations")
async def api_get_conversations(limit: int = 10):
    """Get recent conversation history with summaries."""
    try:
        conversations = load_conversations_history(limit=limit)
        return {"status": "ok", "conversations": conversations}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/chats/generate-title")
async def api_generate_chat_title(body: dict):
    """
    Generate a short chat title using the router's small LLM.
    Input: { "message": string, "files": [{ "name": string }] } (files optional)
    Output: { "status": "ok", "title": string }
    """
    try:
        message = body.get("message", "") if isinstance(body, dict) else ""
        files = body.get("files", []) if isinstance(body, dict) else []

        file_names: list[str] = []
        if isinstance(files, list):
            for f in files:
                if isinstance(f, str):
                    file_names.append(f)
                elif isinstance(f, dict) and f.get("name"):
                    file_names.append(str(f.get("name")))

        title = await generate_chat_title_router_llm(message, file_names=file_names)
        return {"status": "ok", "title": title or ""}
    except Exception as e:
        return {"status": "error", "message": str(e), "title": ""}


@router.post("/api/topics/track")
async def api_track_topic(body: dict):
    """Manually track a topic of interest."""
    try:
        topic = body.get("topic")
        category = body.get("category", "other")
        if not topic:
            return {"status": "error", "message": "Topic required"}
        result = track_topic(topic, category)
        topics = get_relevant_topics(limit=10)
        return {"status": "ok", "message": result, "topics": topics}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/interests/update")
async def api_update_interests(body: dict):
    """Manually update detected interests."""
    try:
        interests = body.get("interests", {})
        if not interests:
            return {"status": "error", "message": "Interests required"}
        update_interests(interests)
        updated = get_user_interests_summary()
        return {"status": "ok", "interests": updated}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/projects")
async def api_list_projects(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return project_manager.list_projects()


@router.post("/api/projects")
async def api_create_project(body: dict):
    name = body.get("name", "New Project")
    instructions = body.get("instructions")
    return project_manager.create_project(name, instructions)


@router.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/api/projects/{project_id}/chats")
async def api_add_project_chat(project_id: str, body: dict):
    # body: {id, name?}
    chat_id = body.get("id")
    if not chat_id:
        raise HTTPException(status_code=400, detail="Missing 'id' in body")
    name = body.get("name", "")
    # Generate a title from the first message if one was provided
    if not name and body.get("first_message"):
        try:
            title = await generate_chat_title_router_llm(body["first_message"])
            if title:
                name = title
        except Exception as e:
            logger.warning("[chat_title] generation failed: %s", e)
    project_manager.add_chat_to_project(
        project_id,
        {
            "id": chat_id,
            "name": name or "New Chat",
            "created_at": __import__("time").time(),
        },
    )
    return {"status": "ok", "chat": {"id": chat_id, "name": name or "New Chat"}}


@router.delete("/api/projects/{project_id}/chats/{chat_id}")
async def api_delete_project_chat(project_id: str, chat_id: str):
    try:
        project_manager.delete_chat_from_project(project_id, chat_id)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.put("/api/projects/{project_id}/chats/{chat_id}")
async def api_update_project_chat(project_id: str, chat_id: str, body: dict):
    project_manager.update_chat_in_project(project_id, chat_id, **body)
    return {"status": "ok"}


@router.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
    """Delete a project by its ID."""
    try:
        from src.memory.vector_lifecycle import VectorLifecycleManager

        success = VectorLifecycleManager.delete_project_cascade(project_id)
        if success:
            return {"status": "ok"}
        else:
            return {
                "status": "error",
                "message": "Failed to delete project or cannot delete default project",
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/projects/{project_id}/knowledge")
async def api_add_project_knowledge(project_id: str, body: dict):
    """
    Index a file's text content into the project's Qdrant knowledge base.
    Body: { "filename": "report.pdf", "content": "extracted text..." }
    """
    filename = body.get("filename", "")
    content = body.get("content", "")
    if not filename or not content:
        return {"status": "error", "message": "filename and content are required"}

    # Truncate very large content to avoid overwhelming Qdrant
    max_chars = 20_000
    if len(content) > max_chars:
        content = content[:max_chars]

    success = await project_manager.add_knowledge(project_id, filename, content)
    if success:
        return {
            "status": "ok",
            "message": f"Indexed {filename} into project knowledge base",
        }
    return {
        "status": "error",
        "message": "Failed to index — Mem0/Qdrant may be unavailable",
    }


@router.delete("/api/projects/{project_id}/knowledge/{filename}")
async def api_remove_project_knowledge(project_id: str, filename: str):
    """Remove a knowledge file from the project's tracking."""
    import urllib.parse

    filename = urllib.parse.unquote(filename)
    project_manager.remove_knowledge(project_id, filename)
    return {"status": "ok"}


@router.get("/api/history/{thread_id}")
async def api_get_history(thread_id: str):
    """Retrieves full chat history for a specific thread."""
    from src.api.server import app
    from src.api.shared import serialize_message, logger

    try:
        agent = app.state.agent
        if not agent:
            return []

        config = {"configurable": {"thread_id": thread_id}}
        state = await agent.aget_state(config)

        if not state or not state.values:
            return []

        messages = state.values.get("messages", [])
        return [serialize_message(m) for m in messages]
    except Exception as e:
        logger.warning("Failed to fetch history: %s", e)
        return []


@router.put("/api/projects/{project_id}")
async def api_update_project(project_id: str, body: dict):
    project = project_manager.update_project(project_id, **body)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
