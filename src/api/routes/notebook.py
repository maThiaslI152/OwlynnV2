"""HTTP API for inline notebook cell execution from chat widgets."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.local_auth import (
    RUN_TOKEN_HEADER,
    is_loopback_client,
    verify_local_run_token,
)
from src.config.settings import get_project_workspace, normalize_project_id
from src.tools.notebook import execute_notebook_code

router = APIRouter()

_MAX_CELL_CHARS = 12_000


class NotebookRunRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=_MAX_CELL_CHARS)
    project_id: str = "default"
    thread_id: str = "api-notebook"


@router.get("/api/local-run-token")
async def api_local_run_token(request: Request):
    """
    Return the per-process local run token (loopback clients only).

    Required header on POST /api/notebook/run to mitigate drive-by execution from
    arbitrary websites when combined with restricted CORS.
    """
    if not is_loopback_client(request):
        raise HTTPException(status_code=403, detail="Loopback only")
    from src.api.local_auth import get_local_run_token

    token = get_local_run_token(request.app)
    return {"status": "ok", "token": token}


@router.post("/api/notebook/run")
async def api_notebook_run(
    request: Request,
    body: NotebookRunRequest,
    x_owlynn_run_token: str | None = Header(default=None, alias=RUN_TOKEN_HEADER),
):
    """Execute Python in the thread-scoped notebook worker (inline owlynn-cell Run button)."""
    verify_local_run_token(request, x_owlynn_run_token)
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
