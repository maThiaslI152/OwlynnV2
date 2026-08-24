"""Per-request workspace scope for tools.

Normal/Study use an ephemeral per-thread scratch directory (chat-only organic map).
Pentest keeps a durable project workspace so report/file tools still have a path.
"""

from __future__ import annotations

import tempfile
from contextvars import ContextVar, Token
from pathlib import Path

from src.config.settings import get_project_workspace, normalize_project_id

_active_project_id: ContextVar[str | None] = ContextVar(
    "owlynn_active_project_id", default=None
)

_active_scenario_id: ContextVar[str | None] = ContextVar(
    "owlynn_active_scenario_id", default=None
)

_scratch_dirs: dict[str, str] = {}


def _ephemeral_scratch_dir() -> str:
    """Return a durable-for-this-process temp dir keyed by conversation thread."""
    from src.config.audit_log import get_thread_id

    tid = get_thread_id() or "default"
    key = str(tid)
    existing = _scratch_dirs.get(key)
    if existing and Path(existing).is_dir():
        return existing
    path = tempfile.mkdtemp(prefix=f"owlynn-scratch-{key[:24]}-")
    _scratch_dirs[key] = path
    return path


def tool_workspace_root() -> str:
    """Directory tools may write into for this turn.

    Pentest keeps project folders for engagement artifacts.
    Normal/Study use ephemeral scratch (no workspace/projects tree).
    """
    if get_active_scenario_id() == "pentest":
        return get_project_workspace(_active_project_id.get())
    return _ephemeral_scratch_dir()


def get_active_project_id() -> str:
    return normalize_project_id(_active_project_id.get())


def get_active_scenario_id() -> str | None:
    """Return the active scenario_id for this turn (e.g. 'pentest', 'study')."""
    return _active_scenario_id.get()


def set_active_project_for_run(project_id: str | None) -> Token:
    token = _active_project_id.set(normalize_project_id(project_id))
    return token


def set_active_scenario_for_run(scenario_id: str | None) -> Token:
    """Set the active scenario for this graph run."""
    return _active_scenario_id.set(scenario_id)


def reset_active_project(token: Token) -> None:
    _active_project_id.reset(token)


def reset_active_scenario(token: Token) -> None:
    _active_scenario_id.reset(token)
