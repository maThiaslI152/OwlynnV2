from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse

router = APIRouter()


@router.get("/api/projects/{project_id}/chats/{chat_id}/export")
async def export_chat(
    request: Request, project_id: str, chat_id: str, format: str = "json"
):
    from src.api.shared import serialize_message

    agent = getattr(request.app.state, "agent", None)
    if not agent:
        raise HTTPException(status_code=500, detail="Agent unavailable")

    state = await agent.aget_state({"configurable": {"thread_id": chat_id}})
    messages = [
        serialize_message(m)
        for m in (state.values.get("messages", []) if state and state.values else [])
        if serialize_message(m)
    ]

    if format == "json":
        return JSONResponse(
            content={"messages": messages},
            headers={
                "Content-Disposition": f'attachment; filename="chat_{chat_id}.json"'
            },
        )

    md = [f"# Chat Export: {chat_id}\n"]
    for msg in messages:
        md.append(
            f"**{msg.get('role', 'unknown').capitalize()}**:\n{msg.get('content', '')}\n"
        )
    return PlainTextResponse(
        "\n".join(md),
        headers={"Content-Disposition": f'attachment; filename="chat_{chat_id}.md"'},
    )
