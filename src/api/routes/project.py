from fastapi import APIRouter

router = APIRouter()
from fastapi import Response
from fastapi import HTTPException
from src.agent.routing.router import generate_chat_title_router_llm
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
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/interests")
async def api_get_interests():
    """Get detected interests with occurrence counts."""
    try:
        interests = get_user_interests_summary()
        return {"status": "ok", "interests": interests}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/conversations")
async def api_get_conversations(limit: int = 10):
    """Get recent conversation history with summaries."""
    try:
        conversations = load_conversations_history(limit=limit)
        return {"status": "ok", "conversations": conversations}
    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/api/projects/{project_id}/knowledge/directory")
async def api_add_project_directory_knowledge(project_id: str, body: dict):
    """
    Recursively walk a directory inside the project workspace and index all supported files.
    Body: { "directory_path": "docs" } (relative or absolute, will be validated)
    """
    directory_path = body.get("directory_path", "")
    if not directory_path:
        raise HTTPException(status_code=400, detail="directory_path is required")

    import os
    from src.config.settings import get_project_workspace

    project_workspace = get_project_workspace(project_id)

    # Resolve paths and validate directory is within the project workspace
    abs_workspace = os.path.abspath(project_workspace)
    if os.path.isabs(directory_path):
        abs_dir = os.path.abspath(directory_path)
    else:
        abs_dir = os.path.abspath(os.path.join(abs_workspace, directory_path))

    if not abs_dir.startswith(abs_workspace):
        raise HTTPException(
            status_code=403,
            detail="Access denied. Path must be inside project workspace.",
        )
    if not os.path.exists(abs_dir) or not os.path.isdir(abs_dir):
        raise HTTPException(status_code=404, detail="Directory not found")

    # Supported file extensions for processing and indexing
    supported_exts = {
        ".txt",
        ".md",
        ".py",
        ".js",
        ".ts",
        ".json",
        ".csv",
        ".html",
        ".xml",
        ".yaml",
        ".yml",
        ".pdf",
        ".docx",
        ".xlsx",
        ".pptx",
        ".toml",
    }

    files_to_index = []
    for root, dirs, files in os.walk(abs_dir):
        # Skip hidden directories (.processed, .git)
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file in files:
            if file.startswith("."):
                continue
            ext = os.path.splitext(file)[1].lower()
            if ext in supported_exts:
                files_to_index.append(os.path.join(root, file))

    if not files_to_index:
        return {
            "status": "ok",
            "message": "No supported files found in directory",
            "count": 0,
        }

    # Process files in a background task to prevent blocking the HTTP response
    async def index_directory_background():
        from src.api.file_processor import FileWatcherHandler
        from src.api.routes.files import notify_file_processed
        import asyncio

        handler = FileWatcherHandler(
            project_workspace, on_processed_callback=notify_file_processed
        )
        for filepath in files_to_index:
            try:
                # Trigger file status "indexing" before processing
                notify_file_processed(filepath, status="indexing")
                # Run the processor
                await asyncio.to_thread(handler.process_file, filepath)
            except Exception as e:
                logger.error(
                    "Failed to index file %s in directory scan: %s", filepath, e
                )

    # Dispatch to the app event loop
    from src.api.server import app
    import asyncio

    loop = getattr(app.state, "loop", None)
    if loop:
        asyncio.run_coroutine_threadsafe(index_directory_background(), loop)
    else:
        asyncio.create_task(index_directory_background())

    return {
        "status": "ok",
        "message": f"Started indexing {len(files_to_index)} files in the background",
        "count": len(files_to_index),
    }


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
