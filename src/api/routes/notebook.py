"""HTTP API for inline notebook cell execution from chat widgets."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter

from src.config.settings import get_project_workspace, normalize_project_id
from src.tools.notebook import execute_notebook_code

router = APIRouter()


class NotebookRunRequest(BaseModel):
    code: str = Field(..., min_length=1)
    project_id: str = "default"
    thread_id: str = "api-notebook"


@router.post("/api/notebook/run")
async def api_notebook_run(body: NotebookRunRequest):
    """Execute Python in the thread-scoped notebook worker (inline owlynn-cell Run button)."""
    project_id = normalize_project_id(body.project_id)
    ws_dir = get_project_workspace(project_id)
    output = execute_notebook_code(
        body.code,
        workspace_dir=ws_dir,
        session_key=body.thread_id,
    )
    if output.startswith("Error:") or "Error:" in output.split("\n", 1)[0]:
        return {"status": "error", "message": output, "output": output}
    return {"status": "ok", "output": output}
