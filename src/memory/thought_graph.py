"""
Thought Graph Manager & Auto-Cartographer.

Manages the homogeneous Mindmap graph state across Normal, Pentest, and Study modes,
providing autonomous semantic linking, graph layout persistence, and real-time synchronization.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import delete, or_, select

from src.memory.db_models import Base, ThoughtEdge, ThoughtNode
from src.models.db import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)

_SHARED_GRAPH_MODES = {"normal", "study"}


def _normalize_graph_mode(mode: str | None, scenario_id: str | None) -> str:
    """Map internal execution modes back to the user-facing graph modes."""
    if scenario_id == "pentest" or mode == "pentest":
        return "pentest"
    if scenario_id == "study" or mode == "study":
        return "study"
    return "normal"


class ThoughtGraphManager:
    """Async PostgreSQL / SQLite graph manager for thought nodes and semantic edges."""

    _initialized: bool = False

    async def ensure_tables(self) -> None:
        """Create thought graph tables if they don't exist."""
        if self._initialized:
            return
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self._initialized = True
            # Auto-seed from existing chats if thought_nodes is empty
            try:
                from src.models.project import Chat

                async with AsyncSessionLocal() as session:
                    count_res = await session.execute(select(ThoughtNode).limit(1))
                    if not count_res.scalar_one_or_none():
                        chat_res = await session.execute(select(Chat))
                        chats = chat_res.scalars().all()
                        for c in chats:
                            n = ThoughtNode(
                                id=c.id,
                                title=c.name or "Conversation",
                                summary="",
                                mode="normal",
                                status="active",
                                pinned=bool(c.pinned),
                                created_at=c.created_at or time.time(),
                                last_active_at=c.created_at or time.time(),
                            )
                            session.add(n)
                        await session.commit()
                        logger.info(
                            "[thought_graph] Seeded %d nodes from chats table.",
                            len(chats),
                        )
                    await self.delete_legacy_pentest_graph_data(session=session)
            except Exception as e:
                logger.debug("[thought_graph] Seed check skipped: %s", e)
        except Exception as e:
            logger.warning("[thought_graph] Table creation check: %s", e)

    @staticmethod
    def _shared_graph_stmt():
        return select(ThoughtNode).where(
            ThoughtNode.mode != "pentest",
            or_(
                ThoughtNode.scenario_id.is_(None),
                ThoughtNode.scenario_id != "pentest",
            ),
        )

    async def delete_legacy_pentest_graph_data(self, session=None) -> int:
        """Delete legacy pentest rows from the shared thought graph tables."""
        owns_session = session is None
        if owns_session:
            await self.ensure_tables()
            session_ctx = AsyncSessionLocal()
            session = await session_ctx.__aenter__()
        try:
            result = await session.execute(
                select(ThoughtNode.id).where(
                    or_(
                        ThoughtNode.mode == "pentest",
                        ThoughtNode.scenario_id == "pentest",
                    )
                )
            )
            node_ids = list(result.scalars().all())
            if not node_ids:
                if owns_session:
                    await session.commit()
                return 0
            await session.execute(
                delete(ThoughtEdge).where(
                    (ThoughtEdge.source_id.in_(node_ids))
                    | (ThoughtEdge.target_id.in_(node_ids))
                )
            )
            await session.execute(
                delete(ThoughtNode).where(ThoughtNode.id.in_(node_ids))
            )
            await session.commit()
            logger.info(
                "[thought_graph] Removed %d legacy pentest nodes from shared graph.",
                len(node_ids),
            )
            return len(node_ids)
        finally:
            if owns_session:
                await session_ctx.__aexit__(None, None, None)

    async def get_or_create_node(
        self,
        node_id: str,
        title: str = "New Thought",
        mode: str = "normal",
        scenario_id: str | None = None,
        engagement_id: str | None = None,
        course_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get an existing thought node or create a new one."""
        await self.ensure_tables()
        now = time.time()
        async with AsyncSessionLocal() as session:
            stmt = select(ThoughtNode).filter_by(id=node_id)
            result = await session.execute(stmt)
            node = result.scalar_one_or_none()

            if node:
                node.last_active_at = now
                if mode and mode != node.mode:
                    node.mode = mode
                if scenario_id:
                    node.scenario_id = scenario_id
                if engagement_id:
                    node.engagement_id = engagement_id
                if course_id:
                    node.course_id = course_id
                await session.commit()
                return self._node_to_dict(node)

            new_node = ThoughtNode(
                id=node_id,
                title=title,
                summary="",
                mode=mode,
                scenario_id=scenario_id,
                engagement_id=engagement_id,
                course_id=course_id,
                status="active",
                tags=tags or [],
                pinned=False,
                created_at=now,
                last_active_at=now,
            )
            session.add(new_node)
            await session.commit()
            return self._node_to_dict(new_node)

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a single thought node by ID."""
        await self.ensure_tables()
        async with AsyncSessionLocal() as session:
            stmt = select(ThoughtNode).filter_by(id=node_id)
            result = await session.execute(stmt)
            node = result.scalar_one_or_none()
            return self._node_to_dict(node) if node else None

    async def list_nodes(
        self, mode: str | None = None, limit: int = 300
    ) -> list[dict[str, Any]]:
        """List thought nodes, optionally filtered by mode."""
        await self.ensure_tables()
        async with AsyncSessionLocal() as session:
            if mode == "pentest":
                stmt = select(ThoughtNode).where(
                    or_(ThoughtNode.mode == "pentest", ThoughtNode.scenario_id == "pentest")
                )
            else:
                stmt = self._shared_graph_stmt()
            stmt = stmt.order_by(ThoughtNode.last_active_at.desc())
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            if not rows:
                # Seed from Chat table
                try:
                    from src.models.project import Chat

                    chat_res = await session.execute(select(Chat))
                    chats = chat_res.scalars().all()
                    for c in chats:
                        n = ThoughtNode(
                            id=c.id,
                            title=c.name or "Conversation",
                            summary="",
                            mode="normal",
                            status="active",
                            pinned=bool(c.pinned),
                            created_at=c.created_at or time.time(),
                            last_active_at=c.created_at or time.time(),
                        )
                        session.add(n)
                    # Seed connecting edges between chats
                    if len(chats) >= 2:
                        for i in range(len(chats) - 1):
                            session.add(
                                ThoughtEdge(
                                    source_id=chats[i].id,
                                    target_id=chats[i + 1].id,
                                    relation="related_thought",
                                    weight=0.8,
                                    auto_generated=True,
                                )
                            )
                    await session.commit()
                    # Re-fetch
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                except Exception as e:
                    logger.debug("[thought_graph] Seed error: %s", e)

            nodes = [self._node_to_dict(n) for n in rows]
            if mode in _SHARED_GRAPH_MODES:
                nodes = [n for n in nodes if n["mode"] == mode]
            return nodes

    async def list_edges(self) -> list[dict[str, Any]]:
        """List all thought edges."""
        await self.ensure_tables()
        async with AsyncSessionLocal() as session:
            stmt = select(ThoughtEdge).order_by(ThoughtEdge.id.asc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._edge_to_dict(e) for e in rows]

    async def get_graph_data(self, mode: str | None = None) -> dict[str, Any]:
        """Return full mindmap graph payload with nodes and valid connecting edges."""
        nodes = await self.list_nodes(mode=mode)
        node_ids = {n["id"] for n in nodes}

        all_edges = await self.list_edges()
        # Only return edges whose endpoints exist in the active node set
        valid_edges = [
            e for e in all_edges if e["source"] in node_ids and e["target"] in node_ids
        ]

        return {
            "nodes": nodes,
            "edges": valid_edges,
            "total_nodes": len(nodes),
            "total_edges": len(valid_edges),
        }

    async def update_node(self, node_id: str, **kwargs) -> dict[str, Any] | None:
        """Update node properties (title, summary, position, pinned, etc.)."""
        await self.ensure_tables()
        allowed = {
            "title",
            "summary",
            "mode",
            "scenario_id",
            "engagement_id",
            "course_id",
            "status",
            "tags",
            "canvas_x",
            "canvas_y",
            "pinned",
        }
        async with AsyncSessionLocal() as session:
            stmt = select(ThoughtNode).filter_by(id=node_id)
            result = await session.execute(stmt)
            node = result.scalar_one_or_none()
            if not node:
                return None

            for k, v in kwargs.items():
                if k in allowed and hasattr(node, k):
                    setattr(node, k, v)
            node.last_active_at = time.time()
            await session.commit()
            return self._node_to_dict(node)

    async def delete_node(self, node_id: str) -> bool:
        """Delete a thought node and its connected edges."""
        await self.ensure_tables()
        async with AsyncSessionLocal() as session:
            stmt = select(ThoughtNode).filter_by(id=node_id)
            result = await session.execute(stmt)
            node = result.scalar_one_or_none()
            if not node:
                return False

            await session.execute(
                delete(ThoughtEdge).where(
                    (ThoughtEdge.source_id == node_id)
                    | (ThoughtEdge.target_id == node_id)
                )
            )
            await session.delete(node)
            await session.commit()
            return True

    async def create_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str = "relates_to",
        weight: float = 1.0,
        auto_generated: bool = False,
    ) -> dict[str, Any] | None:
        """Create a directed semantic edge between two thought nodes."""
        if source_id == target_id:
            return None
        await self.ensure_tables()
        async with AsyncSessionLocal() as session:
            # Prevent duplicate edge
            stmt = select(ThoughtEdge).filter_by(
                source_id=source_id, target_id=target_id, relation=relation
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                return self._edge_to_dict(existing)

            edge = ThoughtEdge(
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                weight=weight,
                auto_generated=auto_generated,
            )
            session.add(edge)
            await session.commit()
            return self._edge_to_dict(edge)

    async def auto_link_node(
        self,
        node_id: str,
        summary_text: str,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Autonomous Cartographer: Generates embedding for the node summary and
        links to top semantically related nodes in the graph.
        """
        if not summary_text or len(summary_text.strip()) < 10:
            return []

        await self.ensure_tables()
        from src.memory.long_term import get_embedding

        new_edges = []
        try:
            embedding = await get_embedding(summary_text)
            if not embedding:
                return []

            # Save embedding to the active node
            async with AsyncSessionLocal() as session:
                stmt = select(ThoughtNode).filter_by(id=node_id)
                result = await session.execute(stmt)
                active_node = result.scalar_one_or_none()
                if active_node:
                    active_node.summary = summary_text
                    if tags:
                        active_node.tags = list(set((active_node.tags or []) + tags))
                    active_node.embedding = embedding
                    await session.commit()

            # Query candidate nodes for semantic similarity
            async with AsyncSessionLocal() as session:
                stmt = select(ThoughtNode).where(ThoughtNode.id != node_id).limit(60)
                candidates = (await session.execute(stmt)).scalars().all()

            for other in candidates:
                other_emb = other.embedding
                if other_emb is None:
                    other_text = f"{other.title}: {other.summary}".strip()
                    if len(other_text) >= 5:
                        try:
                            other_emb = await get_embedding(other_text)
                            if other_emb:
                                async with AsyncSessionLocal() as s2:
                                    o_node = await s2.get(ThoughtNode, other.id)
                                    if o_node:
                                        o_node.embedding = other_emb
                                        await s2.commit()
                        except Exception:
                            other_emb = None

                if other_emb is None:
                    continue

                sim = _cosine_similarity(embedding, other_emb)
                if sim >= 0.64:
                    relation = (
                        "merges_with"
                        if sim >= 0.80
                        else ("branches_from" if sim >= 0.72 else "relates_to")
                    )
                    edge = await self.create_edge(
                        source_id=node_id,
                        target_id=other.id,
                        relation=relation,
                        weight=round(sim, 3),
                        auto_generated=True,
                    )
                    if edge:
                        new_edges.append(edge)

            logger.info(
                "[auto_cartographer] Node '%s' auto-linked with %d edges.",
                node_id,
                len(new_edges),
            )
        except Exception as e:
            logger.warning("[auto_cartographer] Auto-linking failed: %s", e)

        return new_edges

    @staticmethod
    def _node_to_dict(n: ThoughtNode) -> dict[str, Any]:
        return {
            "id": n.id,
            "title": n.title or "New Thought",
            "summary": n.summary or "",
            "mode": _normalize_graph_mode(n.mode, n.scenario_id),
            "scenario_id": n.scenario_id,
            "engagement_id": n.engagement_id,
            "course_id": n.course_id,
            "status": n.status or "active",
            "tags": n.tags or [],
            "canvas_x": n.canvas_x,
            "canvas_y": n.canvas_y,
            "pinned": bool(n.pinned),
            "created_at": n.created_at or 0.0,
            "last_active_at": n.last_active_at or 0.0,
        }

    @staticmethod
    def _edge_to_dict(e: ThoughtEdge) -> dict[str, Any]:
        return {
            "id": e.id,
            "source": e.source_id,
            "target": e.target_id,
            "relation": e.relation,
            "weight": e.weight,
            "auto_generated": e.auto_generated,
        }


def _cosine_similarity(a: list[float] | Any, b: list[float] | Any) -> float:
    """Compute cosine similarity between two float vectors."""
    try:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
    except Exception:
        return 0.0


thought_graph_manager = ThoughtGraphManager()
