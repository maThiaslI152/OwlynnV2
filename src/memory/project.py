"""
Project Manager for the Local Cowork Agent, backed by PostgreSQL / SQLAlchemy.
"""

import logging
import time
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.config.settings import get_project_workspace
from src.memory.db_models import PentestEngagement
from src.models.db import AsyncSessionLocal
from src.models.project import Chat, KnowledgeFile, Project

logger = logging.getLogger(__name__)

_DEFAULT_PROJECT_ID = "default"
_PROJECT_WRITABLE_FIELDS = {"name", "instructions", "category", "mode"}


class ProjectManager:
    """PostgreSQL-backed project registry."""

    def __init__(self):
        pass

    async def _ensure_default(self):
        """Ensure the 'default' project exists in the DB."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Project).filter_by(id=_DEFAULT_PROJECT_ID)
            )
            if not result.scalars().first():
                proj = Project(
                    id=_DEFAULT_PROJECT_ID,
                    name="General Workspace",
                    instructions="You are a helpful AI assistant in a local-first workspace. Help the user with coding, research, and data analysis tasks.",
                    category="general",
                    mode="normal",
                )
                session.add(proj)
                await session.commit()

    async def create_project(
        self,
        name: str,
        instructions: str = "",
        category: str = "general",
        mode: str = "normal",
    ) -> dict[str, Any]:
        """Create a new workspace project."""
        pid = str(uuid.uuid4())[:8]
        async with AsyncSessionLocal() as session:
            proj = Project(
                id=pid,
                name=name,
                instructions=instructions or "You are a helpful AI assistant.",
                category=category,
                mode=mode,
            )
            session.add(proj)
            await session.commit()

        get_project_workspace(pid)
        return await self.get_project(pid)

    async def get_project(self, project_id: str) -> dict | None:
        await self._ensure_default()
        async with AsyncSessionLocal() as session:
            hidden_chat_ids = await self._get_hidden_chat_ids(session)
            stmt = (
                select(Project)
                .options(selectinload(Project.chats), selectinload(Project.files))
                .filter_by(id=project_id)
            )
            result = await session.execute(stmt)
            proj = result.scalars().first()
            if not proj:
                return None
            return self._to_dict(proj, hidden_chat_ids)

    async def list_projects(self) -> list[dict]:
        await self._ensure_default()
        async with AsyncSessionLocal() as session:
            hidden_chat_ids = await self._get_hidden_chat_ids(session)
            stmt = select(Project).options(
                selectinload(Project.chats), selectinload(Project.files)
            )
            result = await session.execute(stmt)
            return [self._to_dict(p, hidden_chat_ids) for p in result.scalars().all()]

    async def update_project(self, project_id: str, **kwargs) -> dict | None:
        async with AsyncSessionLocal() as session:
            stmt = select(Project).filter_by(id=project_id)
            result = await session.execute(stmt)
            proj = result.scalars().first()
            if not proj:
                return None
            for key, val in kwargs.items():
                if key in _PROJECT_WRITABLE_FIELDS and hasattr(proj, key):
                    setattr(proj, key, val)
            await session.commit()
        return await self.get_project(project_id)

    async def delete_project(self, project_id: str) -> bool:
        if project_id == _DEFAULT_PROJECT_ID:
            return False
        async with AsyncSessionLocal() as session:
            stmt = select(Project).filter_by(id=project_id)
            result = await session.execute(stmt)
            proj = result.scalars().first()
            if not proj:
                return False
            await session.execute(delete(Chat).filter_by(project_id=project_id))
            await session.execute(
                delete(KnowledgeFile).filter_by(project_id=project_id)
            )
            await session.execute(delete(Project).filter_by(id=project_id))
            await session.commit()

        import shutil
        from pathlib import Path

        workspace = Path(get_project_workspace(project_id))
        if workspace.exists():
            try:
                shutil.rmtree(workspace)
            except OSError as exc:
                logger.warning("Could not remove workspace %s: %s", workspace, exc)
        return True

    async def add_chat_to_project(self, project_id: str, chat_info: dict) -> None:
        chat_id = chat_info.get("id")
        if not chat_id:
            return

        from sqlalchemy.exc import IntegrityError

        try:
            async with AsyncSessionLocal() as session:
                # Check if chat already exists to ignore duplicate inserts
                existing = await session.execute(select(Chat).filter_by(id=chat_id))
                if existing.scalars().first():
                    return

                chat = Chat(
                    id=chat_id,
                    project_id=project_id,
                    name=chat_info.get("name", "New Chat"),
                    created_at=chat_info.get("created_at", time.time()),
                )
                session.add(chat)
                await session.commit()
        except IntegrityError:
            # Another concurrent request already inserted this chat, safe to ignore
            pass

    async def remove_chat_references(self, chat_ids: set[str]) -> None:
        """Delete hidden/system chat references from all projects."""
        if not chat_ids:
            return
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Chat).where(Chat.id.in_(chat_ids)))

    async def delete_chat_from_project(self, project_id: str, chat_id: str) -> None:
        async with AsyncSessionLocal() as session:
            stmt = select(Chat).filter_by(id=chat_id, project_id=project_id)
            result = await session.execute(stmt)
            chat = result.scalars().first()
            if chat:
                await session.delete(chat)
                await session.commit()

    async def update_chat_in_project(
        self, project_id: str, chat_id: str, **kwargs
    ) -> None:
        async with AsyncSessionLocal() as session:
            stmt = select(Chat).filter_by(id=chat_id, project_id=project_id)
            result = await session.execute(stmt)
            chat = result.scalars().first()
            if chat:
                for k, v in kwargs.items():
                    if hasattr(chat, k) and k not in ("id", "project_id"):
                        setattr(chat, k, v)
                await session.commit()

    async def add_knowledge(self, project_id: str, name: str, content: str) -> bool:
        # Save to Mem0 Qdrant
        from src.memory.long_term import memory

        if memory is None:
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

        async with AsyncSessionLocal() as session:
            file = KnowledgeFile(project_id=project_id, name=name, added_at=time.time())
            session.add(file)
            await session.commit()
        return True

    async def index_knowledge_document(
        self, project_id: str, filename: str, chunks: list[str]
    ) -> bool:
        cleaned = [c.strip() for c in chunks if c and c.strip()]
        if not cleaned:
            return False

        await self.remove_knowledge(project_id, filename)
        from src.memory.long_term import memory

        if memory is None:
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

        async with AsyncSessionLocal() as session:
            file = KnowledgeFile(
                project_id=project_id, name=filename, added_at=time.time()
            )
            session.add(file)
            await session.commit()
        return True

    async def remove_knowledge(self, project_id: str, name: str) -> None:
        async with AsyncSessionLocal() as session:
            stmt = select(KnowledgeFile).filter_by(project_id=project_id, name=name)
            result = await session.execute(stmt)
            for f in result.scalars().all():
                await session.delete(f)
            await session.commit()

        try:
            from src.memory.long_term import _async_delete

            await _async_delete(
                user_id=f"project:{project_id}", metadata={"filename": name}
            )
            for i in range(21):
                await _async_delete(
                    user_id=f"project:{project_id}",
                    metadata={"filename": f"{name}#chunk{i}"},
                )
        except Exception as exc:
            logger.warning("Failed to remove knowledge vectors for %s: %s", name, exc)

    async def _get_hidden_chat_ids(self, session) -> set[str]:
        result = await session.execute(select(PentestEngagement))
        return {e.id for e in result.scalars().all()}

    def _to_dict(self, proj: Project, hidden_chat_ids: set[str] | None = None) -> dict:
        hidden_chat_ids = hidden_chat_ids or set()
        return {
            "id": proj.id,
            "name": proj.name,
            "instructions": proj.instructions,
            "category": proj.category,
            "mode": proj.mode,
            "chats": [
                {
                    "id": c.id,
                    "name": c.name,
                    "created_at": c.created_at,
                    "pinned": c.pinned,
                    "tags": c.tags,
                }
                for c in proj.chats
                if c.id not in hidden_chat_ids
            ],
            "files": [
                {"name": f.name, "type": f.type, "added_at": f.added_at}
                for f in proj.files
            ],
        }


project_manager = ProjectManager()
