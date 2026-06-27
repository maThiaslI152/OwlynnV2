"""
Project Manager for the Local Cowork Agent.

Manages projects, their custom instructions, workspace directories,
knowledge base associations, and chat thread registrations.

Design decisions:
- Atomic writes via temp-file + rename to prevent data corruption.
- The ``"default"`` project is auto-created and cannot be deleted.
- All workspace paths go through ``get_project_workspace()`` from settings
  so there is exactly one source of truth for the directory layout.
- Thread-safe for concurrent async access (single-writer via the GIL).
"""

import json
import logging
import time
import threading
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from src.config.settings import DATA_DIR, get_project_workspace

logger = logging.getLogger(__name__)

_PROJECTS_PATH = DATA_DIR / "projects.json"

_DEFAULT_PROJECT: dict = {
    "id": "default",
    "name": "General Workspace",
    "instructions": (
        "You are a helpful AI assistant in a local-first workspace. "
        "Help the user with coding, research, and data analysis tasks."
    ),
    "files": [],
    "chats": [],
    "category": "general",
    "mode": "normal",
}

_IMMUTABLE_FIELDS = frozenset({"id"})
_PROJECT_WRITABLE_FIELDS = frozenset({"name", "instructions", "category", "mode"})
_CHAT_WRITABLE_FIELDS = frozenset({"name", "pinned"})


def _deep_copy(d: dict) -> dict:
    """Cheap deep-copy for plain JSON-serialisable dicts."""
    return json.loads(json.dumps(d))


def _knowledge_doc_base(name: str) -> str:
    """Strip legacy per-chunk suffixes so UI shows one row per source file."""
    if not name:
        return name
    if "#chunk" in name:
        return name.split("#chunk", 1)[0]
    return name


def _collapse_knowledge_file_entries(files: list) -> list:
    """Merge ``filename#chunkN`` rows into a single entry per source filename."""
    other: list = []
    by_base: dict[str, dict] = {}
    for entry in files:
        if entry.get("type") != "knowledge":
            other.append(entry)
            continue
        base = _knowledge_doc_base(entry.get("name", ""))
        if not base:
            continue
        added_at = entry.get("added_at") or 0
        prev = by_base.get(base)
        if prev is None or added_at > prev.get("added_at", 0):
            by_base[base] = {
                "name": base,
                "type": "knowledge",
                "added_at": added_at,
            }
    return other + list(by_base.values())


class ProjectManager:
    """In-memory project registry backed by a JSON file on disk."""

    def __init__(self) -> None:
        self.projects: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        with self._lock:
            if not _PROJECTS_PATH.exists():
                self.projects = {"default": _deep_copy(_DEFAULT_PROJECT)}
                self._save()
                return
            try:
                raw = json.loads(_PROJECTS_PATH.read_text(encoding="utf-8"))
                self.projects = raw if isinstance(raw, dict) else {}
            except (json.JSONDecodeError, OSError) as exc:
                logger.error(
                    "Failed to load %s — starting with defaults: %s",
                    _PROJECTS_PATH,
                    exc,
                )
                self.projects = {"default": _deep_copy(_DEFAULT_PROJECT)}
                self._save()
                return
            self._migrate()

    def _migrate(self) -> None:
        """Ensure every project has the keys introduced after v1."""
        changed = False
        for proj in self.projects.values():
            for key, default in (
                ("chats", []),
                ("files", []),
                ("category", "general"),
                ("mode", "normal"),
            ):
                if key not in proj:
                    proj[key] = default
                    changed = True
        if "default" not in self.projects:
            self.projects["default"] = _deep_copy(_DEFAULT_PROJECT)
            changed = True
        for proj in self.projects.values():
            collapsed = _collapse_knowledge_file_entries(proj.get("files", []))
            if collapsed != proj.get("files", []):
                proj["files"] = collapsed
                changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=DATA_DIR,
                prefix="projects.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_file.write(
                    json.dumps(self.projects, ensure_ascii=False, indent=2) + "\n"
                )
                tmp_path = Path(tmp_file.name)
            tmp_path.replace(_PROJECTS_PATH)
        except OSError as exc:
            logger.error("Failed to write %s: %s", _PROJECTS_PATH, exc)
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            raise

    # ── CRUD — projects ──────────────────────────────────────────────────

    def create_project(self, name: str, instructions: Optional[str] = None) -> dict:
        import uuid

        with self._lock:
            pid = str(uuid.uuid4())[:8]
            while pid in self.projects:
                pid = str(uuid.uuid4())[:8]
            project = {
                "id": pid,
                "name": name,
                "instructions": instructions or _DEFAULT_PROJECT["instructions"],
                "files": [],
                "chats": [],
                "category": "general",
            }
            self.projects[pid] = project
            self._save()
        get_project_workspace(pid)
        return project

    def get_project(self, project_id: str) -> Optional[dict]:
        with self._lock:
            return self.projects.get(project_id)

    def list_projects(self) -> List[dict]:
        with self._lock:
            return list(self.projects.values())

    def update_project(self, project_id: str, **kwargs) -> Optional[dict]:
        with self._lock:
            project = self.projects.get(project_id)
            if project is None:
                return None
            for key, value in kwargs.items():
                if key in _IMMUTABLE_FIELDS or key not in _PROJECT_WRITABLE_FIELDS:
                    continue
                project[key] = value
            self._save()
            return project

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            if project_id == "default" or project_id not in self.projects:
                return False
            del self.projects[project_id]
            self._save()

        workspace = Path(get_project_workspace(project_id))
        if workspace.exists():
            import shutil

            try:
                shutil.rmtree(workspace)
            except OSError as exc:
                logger.warning("Could not remove workspace %s: %s", workspace, exc)
        return True

    # ── CRUD — chats ─────────────────────────────────────────────────────

    def add_chat_to_project(self, project_id: str, chat_info: dict) -> None:
        with self._lock:
            project = self.projects.get(project_id)
            if project is None:
                return
            chats: list = project.setdefault("chats", [])
            chat_id = chat_info.get("id")
            if chat_id and any(c.get("id") == chat_id for c in chats):
                return  # duplicate
            chats.append(chat_info)
            self._save()

    def delete_chat_from_project(self, project_id: str, chat_id: str) -> None:
        with self._lock:
            project = self.projects.get(project_id)
            if project is None:
                return
            project["chats"] = [
                c for c in project.get("chats", []) if c.get("id") != chat_id
            ]
            self._save()

    def update_chat_in_project(self, project_id: str, chat_id: str, **kwargs) -> None:
        with self._lock:
            project = self.projects.get(project_id)
            if project is None:
                return
            for chat in project.get("chats", []):
                if chat.get("id") == chat_id:
                    for k, v in kwargs.items():
                        if k in _IMMUTABLE_FIELDS or k not in _CHAT_WRITABLE_FIELDS:
                            continue
                        chat[k] = v
                    break
            self._save()

    # ── CRUD — knowledge files ───────────────────────────────────────────

    async def add_knowledge(self, project_id: str, name: str, content: str) -> bool:
        with self._lock:
            project = self.projects.get(project_id)
            if project is None:
                return False

        from src.memory.long_term import memory

        if memory is None:
            logger.info("Mem0 unavailable — skipping knowledge indexing for %s", name)
            return False

        try:
            import asyncio

            await asyncio.to_thread(
                memory.add,
                content,
                user_id=f"project:{project_id}",
                metadata={"filename": name},
                infer=False,
            )
        except Exception as exc:
            logger.warning("Failed to index %s into Qdrant: %s", name, exc)
            return False

        with self._lock:
            current_project = self.projects.get(project_id)
            if current_project is None:
                return False
            files: list = current_project.setdefault("files", [])
            if not any(f.get("name") == name for f in files):
                files.append(
                    {"name": name, "type": "knowledge", "added_at": time.time()}
                )
                self._save()
        return True

    async def index_knowledge_document(
        self, project_id: str, filename: str, chunks: list[str]
    ) -> bool:
        """Index chunked document text into Mem0; one UI row per source file."""
        cleaned = [c.strip() for c in chunks if c and c.strip()]
        if not cleaned:
            return False

        self.remove_knowledge(project_id, filename)

        from src.memory.long_term import memory

        if memory is None:
            logger.info(
                "Mem0 unavailable — skipping knowledge indexing for %s", filename
            )
            return False

        try:
            import asyncio

            for i, chunk_text in enumerate(cleaned):
                await asyncio.to_thread(
                    memory.add,
                    chunk_text,
                    user_id=f"project:{project_id}",
                    metadata={"filename": filename, "chunk": i},
                    infer=False,
                )
        except Exception as exc:
            logger.warning("Failed to index %s into Qdrant: %s", filename, exc)
            return False

        with self._lock:
            project = self.projects.get(project_id)
            if project is None:
                return False
            files: list = project.setdefault("files", [])
            files[:] = [
                f for f in files if _knowledge_doc_base(f.get("name", "")) != filename
            ]
            files.append(
                {"name": filename, "type": "knowledge", "added_at": time.time()}
            )
            self._save()
        return True

    def remove_knowledge(self, project_id: str, name: str) -> None:
        with self._lock:
            project = self.projects.get(project_id)
            if project is None:
                return
            project["files"] = [
                f
                for f in project.get("files", [])
                if _knowledge_doc_base(f.get("name", "")) != name
            ]
            self._save()

        # Also remove vectors from Qdrant/Mem0 to avoid orphaned embeddings
        try:
            from src.memory.long_term import memory

            if memory is not None:
                memory.delete(
                    user_id=f"project:{project_id}", metadata={"filename": name}
                )
                for i in range(21):
                    memory.delete(
                        user_id=f"project:{project_id}",
                        metadata={"filename": f"{name}#chunk{i}"},
                    )
        except Exception as exc:
            logger.warning("Failed to remove knowledge vectors for %s: %s", name, exc)

    # ── helpers ──────────────────────────────────────────────────────────

    def add_file_to_project(self, project_id: str, file_info: dict) -> None:
        with self._lock:
            project = self.projects.get(project_id)
            if project is None:
                return
            project.setdefault("files", []).append(file_info)
            self._save()

    def get_workspace_path(self, project_id: str) -> Path:
        """Return the workspace Path for project_id (creates it if needed)."""
        return Path(get_project_workspace(project_id))


# Module-level singleton used by the rest of the application.
project_manager = ProjectManager()
