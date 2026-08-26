"""
Thought Graph Manager & Auto-Cartographer.

Manages the homogeneous Mindmap graph state across Normal, Pentest, and Study modes,
providing autonomous semantic linking, graph layout persistence, and real-time synchronization.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import delete, or_, select, text

from src.memory.db_models import Base, ThoughtEdge, ThoughtNode
from src.models.db import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)

_SHARED_GRAPH_MODES = {"normal", "study"}
_SEMANTIC_RELATIONS = frozenset(
    {"relates_to", "merges_with", "branches_from", "related_thought"}
)

DEFAULT_NODE_LIMIT = 300
DEFAULT_MAX_EDGES_PER_NODE = 8
DORMANCY_HALF_LIFE_DAYS = 14.0
DORMANT_THRESHOLD = 0.55
FADE_MIN = 0.28
FADE_MAX = 1.0
AUTO_LINK_SIM_THRESHOLD = 0.64
MIN_EMBED_TEXT_LEN = 3

_SHAPING_COLUMNS = (
    ("topic_cluster_id", "VARCHAR(128)"),
    ("topic_label", "VARCHAR(256)"),
    ("dormancy_score", "FLOAT"),
    ("importance_score", "FLOAT"),
)


def _normalize_graph_mode(mode: str | None, scenario_id: str | None) -> str:
    """Map internal execution modes back to the user-facing graph modes."""
    if scenario_id == "pentest" or mode == "pentest":
        return "pentest"
    if scenario_id == "study" or mode == "study":
        return "study"
    return "normal"


def embedding_text_for_node(
    title: str | None,
    summary: str | None,
    tags: list[str] | None = None,
) -> str:
    """Prefer summary; fall back to title (+ tags) when summary is empty."""
    summary_text = (summary or "").strip()
    if len(summary_text) >= 10:
        return summary_text
    tag_s = " ".join(str(t) for t in (tags or []) if t)
    fallback = f"{(title or '').strip()} {tag_s}".strip()
    return fallback if fallback else summary_text


def compute_dormancy_score(
    last_active_at: float | None,
    *,
    pinned: bool = False,
    neighbor_last_active: float | None = None,
    now: float | None = None,
) -> float:
    """Monotonic dormancy in [0, 1]; pinned nodes never decay."""
    if pinned:
        return 0.0
    now_ts = now if now is not None else time.time()
    age_days = max(0.0, (now_ts - (last_active_at or 0.0)) / 86400.0)
    score = 1.0 - (0.5 ** (age_days / DORMANCY_HALF_LIFE_DAYS))
    if neighbor_last_active:
        n_age = max(0.0, (now_ts - neighbor_last_active) / 86400.0)
        n_score = 1.0 - (0.5 ** (n_age / DORMANCY_HALF_LIFE_DAYS))
        score = (0.65 * score) + (0.35 * n_score)
    return round(min(1.0, max(0.0, score)), 4)


def compute_importance_score(
    dormancy_score: float,
    *,
    pinned: bool = False,
) -> float:
    """Composite centrality for ranking (higher = more central)."""
    base = 1.0 - dormancy_score
    if pinned:
        return round(min(1.0, base + 0.35), 4)
    return round(base, 4)


def compute_fade_alpha(dormancy_score: float, *, pinned: bool = False) -> float:
    if pinned:
        return FADE_MAX
    return round(FADE_MAX - (dormancy_score * (FADE_MAX - FADE_MIN)), 4)


def compute_radial_tier(dormancy_score: float) -> int:
    if dormancy_score < 0.15:
        return 0
    if dormancy_score < 0.40:
        return 1
    if dormancy_score < 0.70:
        return 2
    return 3


class _UnionFind:
    def __init__(self, ids: list[str]) -> None:
        self.parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if ra < rb:
            self.parent[rb] = ra
        else:
            self.parent[ra] = rb


def assign_topic_clusters(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, tuple[str, str]]:
    """
    Group related threads by mode without merging identities.

    ``merges_with`` is an edge label only — cluster membership never rewrites node IDs.
    """
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        mode = node.get("mode") or "normal"
        if mode == "pentest":
            continue
        by_mode.setdefault(mode, []).append(node)

    assignments: dict[str, tuple[str, str]] = {}
    for members in by_mode.values():
        ids = [n["id"] for n in members]
        uf = _UnionFind(ids)
        id_set = set(ids)
        for edge in edges:
            src, tgt = edge.get("source"), edge.get("target")
            if src not in id_set or tgt not in id_set:
                continue
            relation = edge.get("relation") or ""
            if relation in _SEMANTIC_RELATIONS:
                uf.union(src, tgt)

        groups: dict[str, list[dict[str, Any]]] = {}
        for node in members:
            root = uf.find(node["id"])
            groups.setdefault(root, []).append(node)
        for root, group in groups.items():
            label = _cluster_label(group)
            for node in group:
                assignments[node["id"]] = (root, label)
    return assignments


def prune_edges_to_nodes(
    edges: list[dict[str, Any]],
    node_ids: set[str],
    *,
    max_edges_per_node: int | None = DEFAULT_MAX_EDGES_PER_NODE,
) -> list[dict[str, Any]]:
    """Keep edges whose endpoints are in ``node_ids``; optionally top-K by weight."""
    valid = [
        e for e in edges if e.get("source") in node_ids and e.get("target") in node_ids
    ]
    if not max_edges_per_node or max_edges_per_node <= 0:
        return valid

    ranked = sorted(valid, key=lambda e: float(e.get("weight") or 0.0), reverse=True)
    degree: dict[str, int] = {nid: 0 for nid in node_ids}
    kept: list[dict[str, Any]] = []
    for edge in ranked:
        src, tgt = edge["source"], edge["target"]
        if degree.get(src, 0) >= max_edges_per_node:
            continue
        if degree.get(tgt, 0) >= max_edges_per_node:
            continue
        kept.append(edge)
        degree[src] = degree.get(src, 0) + 1
        degree[tgt] = degree.get(tgt, 0) + 1
    return kept


def _cluster_label(group: list[dict[str, Any]]) -> str:
    tag_counts: dict[str, int] = {}
    for node in group:
        for tag in node.get("tags") or []:
            if tag:
                tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1
    if tag_counts:
        return max(tag_counts, key=lambda t: (tag_counts[t], t))[:256]
    newest = max(group, key=lambda n: float(n.get("last_active_at") or 0.0))
    title = (newest.get("title") or "Topic").strip() or "Topic"
    return title[:256]


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
                await conn.run_sync(_ensure_shaping_columns)
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
                select(ThoughtNode).where(
                    or_(
                        ThoughtNode.mode == "pentest",
                        ThoughtNode.scenario_id == "pentest",
                    )
                )
            )
            node_ids = [n.id for n in result.scalars().all()]
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
    ) -> dict[str, Any] | None:
        """Get an existing thought node or create a new one.

        Returns ``None`` when the Postgres circuit is open or the write fails —
        callers must not treat a skip as a persisted node.
        """
        from src.memory.postgres_health import (
            is_postgres_available,
            record_postgres_failure,
            record_postgres_success,
        )

        if not is_postgres_available():
            logger.debug(
                "[thought_graph] Skipping get_or_create_node — Postgres circuit open "
                "(node_id=%s)",
                node_id,
            )
            return None

        await self.ensure_tables()
        now = time.time()
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ThoughtNode).filter_by(id=node_id)
                result = await session.execute(stmt)
                node = result.scalar_one_or_none()

                if node:
                    _revive_orm_node(node, now)
                    if mode and mode != node.mode:
                        node.mode = mode
                    if scenario_id:
                        node.scenario_id = scenario_id
                    if engagement_id:
                        node.engagement_id = engagement_id
                    if course_id:
                        node.course_id = course_id
                    await session.commit()
                    record_postgres_success()
                    return self._node_to_dict(node, now=now)

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
                    dormancy_score=0.0,
                    importance_score=1.0,
                )
                session.add(new_node)
                await session.commit()
                record_postgres_success()
                return self._node_to_dict(new_node, now=now)
        except Exception as exc:
            record_postgres_failure()
            logger.warning(
                "[thought_graph] get_or_create_node failed: %s", exc, exc_info=True
            )
            return None

    async def get_node(
        self, node_id: str, *, touch_active: bool = True
    ) -> dict[str, Any] | None:
        """Get a single thought node by ID. Selecting a node immediately revives it."""
        await self.ensure_tables()
        now = time.time()
        async with AsyncSessionLocal() as session:
            stmt = select(ThoughtNode).filter_by(id=node_id)
            result = await session.execute(stmt)
            node = result.scalar_one_or_none()
            if not node:
                return None
            if touch_active:
                _revive_orm_node(node, now)
                await session.commit()
            return self._node_to_dict(node, now=now)

    async def list_nodes(
        self,
        mode: str | None = None,
        limit: int = DEFAULT_NODE_LIMIT,
        *,
        show_dormant: bool = True,
        focus_node_id: str | None = None,
        search: str | None = None,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        """List thought nodes, optionally filtered by mode, ranked by importance."""
        await self.ensure_tables()
        now_ts = now if now is not None else time.time()
        fetch_cap = max((limit or DEFAULT_NODE_LIMIT) * 4, 400)
        async with AsyncSessionLocal() as session:
            stmt = self._nodes_stmt(mode)
            stmt = stmt.order_by(
                ThoughtNode.pinned.desc(),
                ThoughtNode.last_active_at.desc(),
            )
            if fetch_cap:
                stmt = stmt.limit(fetch_cap)
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            if not rows:
                rows = await self._seed_from_chats(session, stmt)

            extra_ids = [i for i in (focus_node_id,) if i]
            if search and search.strip():
                q = f"%{search.strip()}%"
                search_stmt = self._nodes_stmt(mode).where(
                    or_(
                        ThoughtNode.title.ilike(q),
                        ThoughtNode.summary.ilike(q),
                    )
                )
                search_rows = (await session.execute(search_stmt)).scalars().all()
                extra_ids.extend(n.id for n in search_rows)

            have = {n.id for n in rows}
            missing = [i for i in extra_ids if i and i not in have]
            if missing:
                extra = (
                    (
                        await session.execute(
                            select(ThoughtNode).where(ThoughtNode.id.in_(missing))
                        )
                    )
                    .scalars()
                    .all()
                )
                rows.extend(extra)

            nodes = [self._node_to_dict(n, now=now_ts) for n in rows]
            if mode in _SHARED_GRAPH_MODES:
                nodes = [n for n in nodes if n["mode"] == mode]
            nodes = _rank_and_filter_nodes(
                nodes,
                limit=limit,
                show_dormant=show_dormant,
                focus_node_id=focus_node_id,
                search=search,
            )
            return nodes

    async def list_edges(self) -> list[dict[str, Any]]:
        """List all thought edges."""
        await self.ensure_tables()
        async with AsyncSessionLocal() as session:
            stmt = select(ThoughtEdge).order_by(ThoughtEdge.id.asc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._edge_to_dict(e) for e in rows]

    async def get_graph_data(
        self,
        mode: str | None = None,
        *,
        clustered: bool = True,
        show_dormant: bool = True,
        focus_node_id: str | None = None,
        max_nodes: int | None = None,
        max_edges_per_node: int | None = DEFAULT_MAX_EDGES_PER_NODE,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return mindmap graph payload with cluster/dormancy metadata and pruned edges."""
        if focus_node_id:
            await self.get_node(focus_node_id, touch_active=True)

        limit = max_nodes if max_nodes is not None else DEFAULT_NODE_LIMIT
        now_ts = time.time()
        await self.ensure_tables()

        async with AsyncSessionLocal() as session:
            stmt = self._nodes_stmt(mode).order_by(
                ThoughtNode.pinned.desc(),
                ThoughtNode.last_active_at.desc(),
            )
            fetch_cap = max((limit or DEFAULT_NODE_LIMIT) * 4, 400)
            result = await session.execute(stmt.limit(fetch_cap))
            rows = list(result.scalars().all())
            if not rows:
                rows = await self._seed_from_chats(session, stmt.limit(fetch_cap))

            have = {n.id for n in rows}
            extras: list[str] = []
            if focus_node_id:
                extras.append(focus_node_id)
            if search and search.strip():
                q = f"%{search.strip()}%"
                found = (
                    (
                        await session.execute(
                            self._nodes_stmt(mode).where(
                                or_(
                                    ThoughtNode.title.ilike(q),
                                    ThoughtNode.summary.ilike(q),
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                extras.extend(n.id for n in found)
            missing = [i for i in extras if i and i not in have]
            if missing:
                rows.extend(
                    (
                        await session.execute(
                            select(ThoughtNode).where(ThoughtNode.id.in_(missing))
                        )
                    )
                    .scalars()
                    .all()
                )

            all_edges = [
                self._edge_to_dict(e)
                for e in (
                    await session.execute(
                        select(ThoughtEdge).order_by(ThoughtEdge.id.asc())
                    )
                )
                .scalars()
                .all()
            ]
            neighbor_map = _neighbor_last_active_map(rows, all_edges)
            nodes = [
                self._node_to_dict(
                    n,
                    now=now_ts,
                    neighbor_last_active=neighbor_map.get(n.id),
                )
                for n in rows
            ]

        if mode in _SHARED_GRAPH_MODES:
            nodes = [n for n in nodes if n["mode"] == mode]

        if clustered:
            assignments = assign_topic_clusters(nodes, all_edges)
            for node in nodes:
                pair = assignments.get(node["id"])
                if pair:
                    node["topic_cluster_id"] = pair[0]
                    node["topic_label"] = pair[1]
            await self._persist_cluster_assignments(assignments)

        nodes = _rank_and_filter_nodes(
            nodes,
            limit=limit,
            show_dormant=show_dormant,
            focus_node_id=focus_node_id,
            search=search,
        )
        node_ids = {n["id"] for n in nodes}
        valid_edges = prune_edges_to_nodes(
            all_edges, node_ids, max_edges_per_node=max_edges_per_node
        )

        return {
            "nodes": nodes,
            "edges": valid_edges,
            "clusters": _clusters_payload(nodes),
            "total_nodes": len(nodes),
            "total_edges": len(valid_edges),
        }

    async def update_node(self, node_id: str, **kwargs) -> dict[str, Any] | None:
        """Update node properties (title, summary, position, pinned, etc.)."""
        from src.memory.postgres_health import (
            is_postgres_available,
            record_postgres_failure,
            record_postgres_success,
        )

        if not is_postgres_available():
            return None

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
            "last_active_at",
            "topic_cluster_id",
            "topic_label",
        }
        canvas_only = set(kwargs.keys()) <= {"canvas_x", "canvas_y"}
        explicit_ts = "last_active_at" in kwargs
        touch_active = kwargs.pop("touch_active", None)
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ThoughtNode).filter_by(id=node_id)
                result = await session.execute(stmt)
                node = result.scalar_one_or_none()
                if not node:
                    return None

                for k, v in kwargs.items():
                    if k in allowed and hasattr(node, k):
                        setattr(node, k, v)

                should_touch = touch_active is True or (
                    touch_active is not False and not canvas_only and not explicit_ts
                )
                now = time.time()
                if should_touch:
                    _revive_orm_node(node, now)
                await session.commit()
                record_postgres_success()
                return self._node_to_dict(node, now=now)
        except Exception as exc:
            record_postgres_failure()
            logger.warning("[thought_graph] update_node failed: %s", exc, exc_info=True)
            return None

    async def delete_node(self, node_id: str) -> bool:
        """Delete a thought node and its connected edges."""
        from src.memory.postgres_health import (
            is_postgres_available,
            record_postgres_failure,
            record_postgres_success,
        )

        if not is_postgres_available():
            return False

        await self.ensure_tables()
        try:
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
                record_postgres_success()
                return True
        except Exception as exc:
            record_postgres_failure()
            logger.warning("[thought_graph] delete_node failed: %s", exc, exc_info=True)
            return False

    async def create_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str = "relates_to",
        weight: float = 1.0,
        auto_generated: bool = False,
    ) -> dict[str, Any] | None:
        """Create a directed semantic edge between two thought nodes."""
        from src.memory.postgres_health import (
            is_postgres_available,
            record_postgres_failure,
            record_postgres_success,
        )

        if source_id == target_id:
            return None
        if not is_postgres_available():
            return None

        await self.ensure_tables()
        try:
            async with AsyncSessionLocal() as session:
                # Prevent duplicate edge
                stmt = select(ThoughtEdge).filter_by(
                    source_id=source_id, target_id=target_id, relation=relation
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    record_postgres_success()
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
                record_postgres_success()
                return self._edge_to_dict(edge)
        except Exception as exc:
            record_postgres_failure()
            logger.warning("[thought_graph] create_edge failed: %s", exc, exc_info=True)
            return None

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
        from src.memory.postgres_health import is_postgres_available

        if not is_postgres_available():
            return []

        await self.ensure_tables()
        from src.memory.long_term import get_embedding

        new_edges: list[dict[str, Any]] = []
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ThoughtNode).filter_by(id=node_id)
                result = await session.execute(stmt)
                active_node = result.scalar_one_or_none()
                if not active_node:
                    return []
                active_mode = _normalize_graph_mode(
                    active_node.mode, active_node.scenario_id
                )
                if active_mode == "pentest":
                    return []
                merged_tags = list(set((active_node.tags or []) + (tags or [])))
                embed_text = embedding_text_for_node(
                    active_node.title,
                    summary_text or active_node.summary,
                    merged_tags,
                )
                if len(embed_text) < MIN_EMBED_TEXT_LEN:
                    return []
                if summary_text and len(summary_text.strip()) >= 10:
                    active_node.summary = summary_text
                if tags:
                    active_node.tags = merged_tags
                await session.commit()

            embedding = await get_embedding(embed_text)
            if not embedding:
                return []

            async with AsyncSessionLocal() as session:
                stmt = select(ThoughtNode).filter_by(id=node_id)
                result = await session.execute(stmt)
                active_node = result.scalar_one_or_none()
                if active_node:
                    active_node.embedding = embedding
                    await session.commit()
                    active_mode = _normalize_graph_mode(
                        active_node.mode, active_node.scenario_id
                    )
                else:
                    return []

            async with AsyncSessionLocal() as session:
                stmt = (
                    select(ThoughtNode)
                    .where(
                        ThoughtNode.id != node_id,
                        ThoughtNode.mode != "pentest",
                        or_(
                            ThoughtNode.scenario_id.is_(None),
                            ThoughtNode.scenario_id != "pentest",
                        ),
                    )
                    .limit(60)
                )
                candidates = (await session.execute(stmt)).scalars().all()

            for other in candidates:
                other_mode = _normalize_graph_mode(other.mode, other.scenario_id)
                if other_mode != active_mode:
                    continue
                other_emb = other.embedding
                if other_emb is None:
                    other_text = embedding_text_for_node(
                        other.title, other.summary, other.tags
                    )
                    if len(other_text) >= MIN_EMBED_TEXT_LEN:
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
                if sim >= AUTO_LINK_SIM_THRESHOLD:
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

            if new_edges:
                await self._refresh_clusters_for_mode(active_mode)
            await self.backfill_missing_embeddings(limit=16)

            logger.info(
                "[auto_cartographer] Node '%s' auto-linked with %d edges.",
                node_id,
                len(new_edges),
            )
        except Exception as e:
            logger.warning("[auto_cartographer] Auto-linking failed: %s", e)

        return new_edges

    async def backfill_missing_embeddings(self, limit: int = 24) -> int:
        """Lazy-embed title/tag fallbacks for nodes missing vectors."""
        await self.ensure_tables()
        from src.memory.long_term import get_embedding

        filled = 0
        try:
            async with AsyncSessionLocal() as session:
                rows = (
                    (
                        await session.execute(
                            select(ThoughtNode)
                            .where(
                                ThoughtNode.embedding.is_(None),
                                ThoughtNode.mode != "pentest",
                            )
                            .limit(limit)
                        )
                    )
                    .scalars()
                    .all()
                )
                pending = [
                    (n.id, embedding_text_for_node(n.title, n.summary, n.tags))
                    for n in rows
                ]
            for nid, text in pending:
                if len(text) < MIN_EMBED_TEXT_LEN:
                    continue
                try:
                    emb = await get_embedding(text)
                except Exception as e:
                    logger.debug("[thought_graph] Embed failed for %s: %s", nid, e)
                    continue
                if not emb:
                    continue
                async with AsyncSessionLocal() as session:
                    node = await session.get(ThoughtNode, nid)
                    if node and node.embedding is None:
                        node.embedding = emb
                        await session.commit()
                        filled += 1
        except Exception as e:
            logger.debug("[thought_graph] Embedding backfill skipped: %s", e)
        return filled

    async def _refresh_clusters_for_mode(self, mode: str) -> None:
        nodes = await self.list_nodes(
            mode=mode, limit=DEFAULT_NODE_LIMIT, show_dormant=True
        )
        edges = await self.list_edges()
        await self._persist_cluster_assignments(assign_topic_clusters(nodes, edges))

    async def _persist_cluster_assignments(
        self, assignments: dict[str, tuple[str, str]]
    ) -> None:
        if not assignments:
            return
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ThoughtNode).where(ThoughtNode.id.in_(list(assignments)))
                )
                for node in result.scalars().all():
                    pair = assignments.get(node.id)
                    if not pair:
                        continue
                    cid, label = pair
                    if node.topic_cluster_id != cid or node.topic_label != label:
                        node.topic_cluster_id = cid
                        node.topic_label = label
                await session.commit()
        except Exception as e:
            logger.debug("[thought_graph] Cluster persist skipped: %s", e)

    def _nodes_stmt(self, mode: str | None):
        if mode == "pentest":
            return select(ThoughtNode).where(
                or_(ThoughtNode.mode == "pentest", ThoughtNode.scenario_id == "pentest")
            )
        stmt = self._shared_graph_stmt()
        if mode == "study":
            stmt = stmt.where(
                or_(ThoughtNode.mode == "study", ThoughtNode.scenario_id == "study")
            )
        elif mode == "normal":
            stmt = stmt.where(
                ThoughtNode.mode != "study",
                or_(
                    ThoughtNode.scenario_id.is_(None),
                    ThoughtNode.scenario_id != "study",
                ),
            )
        return stmt

    async def _seed_from_chats(self, session, stmt):
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
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.debug("[thought_graph] Seed error: %s", e)
            return []

    @staticmethod
    def _node_to_dict(
        n: ThoughtNode,
        *,
        now: float | None = None,
        neighbor_last_active: float | None = None,
    ) -> dict[str, Any]:
        now_ts = now if now is not None else time.time()
        pinned = bool(n.pinned)
        dormancy = compute_dormancy_score(
            n.last_active_at,
            pinned=pinned,
            neighbor_last_active=neighbor_last_active,
            now=now_ts,
        )
        importance = compute_importance_score(dormancy, pinned=pinned)
        is_dormant = (not pinned) and dormancy >= DORMANT_THRESHOLD
        has_saved_pos = n.canvas_x is not None and n.canvas_y is not None
        allow_radial_drift = (not pinned) and (not has_saved_pos)
        radial_tier = compute_radial_tier(dormancy) if allow_radial_drift else 0
        if pinned:
            visual_mode = "pinned"
        elif is_dormant:
            visual_mode = "dormant"
        else:
            visual_mode = "active"
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
            "pinned": pinned,
            "created_at": n.created_at or 0.0,
            "last_active_at": n.last_active_at or 0.0,
            "topic_cluster_id": n.topic_cluster_id,
            "topic_label": n.topic_label,
            "dormancy_score": dormancy,
            "importance_score": importance,
            "is_dormant": is_dormant,
            "fade_alpha": compute_fade_alpha(dormancy, pinned=pinned),
            "radial_tier": radial_tier,
            "allow_radial_drift": allow_radial_drift,
            "radial_multiplier": round(1.0 + (0.4 * radial_tier), 3)
            if allow_radial_drift
            else 1.0,
            "visual_mode": visual_mode,
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


def _ensure_shaping_columns(sync_conn) -> None:
    """Add cluster/dormancy columns on existing thought_nodes tables (dev/SQLite)."""
    try:
        from sqlalchemy import inspect as sa_inspect

        insp = sa_inspect(sync_conn)
        if "thought_nodes" not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns("thought_nodes")}
        dialect = sync_conn.dialect.name
        for name, sqltype in _SHAPING_COLUMNS:
            if name in existing:
                continue
            if dialect == "sqlite":
                sync_conn.execute(
                    text(f"ALTER TABLE thought_nodes ADD COLUMN {name} {sqltype}")
                )
            else:
                sync_conn.execute(
                    text(
                        f"ALTER TABLE thought_nodes ADD COLUMN IF NOT EXISTS {name} {sqltype}"
                    )
                )
    except Exception as e:
        logger.debug("[thought_graph] Shaping column ensure skipped: %s", e)


def _revive_orm_node(node: ThoughtNode, now: float) -> None:
    node.last_active_at = now
    node.status = "active"
    node.dormancy_score = 0.0
    node.importance_score = 1.0


def _neighbor_last_active_map(
    rows: list[ThoughtNode], edges: list[dict[str, Any]]
) -> dict[str, float]:
    by_id = {n.id: float(n.last_active_at or 0.0) for n in rows}
    neigh: dict[str, float] = {n.id: 0.0 for n in rows}
    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if src in by_id and tgt in by_id:
            neigh[src] = max(neigh[src], by_id[tgt])
            neigh[tgt] = max(neigh[tgt], by_id[src])
    return neigh


def _rank_and_filter_nodes(
    nodes: list[dict[str, Any]],
    *,
    limit: int,
    show_dormant: bool,
    focus_node_id: str | None,
    search: str | None,
) -> list[dict[str, Any]]:
    needle = (search or "").strip().lower()

    def _is_search_hit(n: dict[str, Any]) -> bool:
        if not needle:
            return False
        blob = f"{n.get('title') or ''} {n.get('summary') or ''} {' '.join(n.get('tags') or [])}".lower()
        return needle in blob

    filtered: list[dict[str, Any]] = []
    for node in nodes:
        if not show_dormant and node.get("is_dormant"):
            if (
                node.get("pinned")
                or node.get("id") == focus_node_id
                or _is_search_hit(node)
            ):
                filtered.append(node)
            continue
        filtered.append(node)

    filtered.sort(
        key=lambda n: (
            1 if n.get("id") == focus_node_id else 0,
            1 if n.get("pinned") else 0,
            float(n.get("importance_score") or 0.0),
            float(n.get("last_active_at") or 0.0),
        ),
        reverse=True,
    )
    if not limit:
        return filtered
    kept = filtered[:limit]
    kept_ids = {n["id"] for n in kept}
    if focus_node_id and focus_node_id not in kept_ids:
        extra = next((n for n in filtered if n["id"] == focus_node_id), None)
        if extra:
            kept.append(extra)
    if needle:
        for node in filtered:
            if _is_search_hit(node) and node["id"] not in kept_ids:
                kept.append(node)
                kept_ids.add(node["id"])
    return kept


def _clusters_payload(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for node in nodes:
        cid = node.get("topic_cluster_id")
        if not cid:
            continue
        bucket = groups.setdefault(
            cid,
            {
                "id": cid,
                "label": node.get("topic_label") or "",
                "mode": node.get("mode"),
                "node_ids": [],
            },
        )
        bucket["node_ids"].append(node["id"])
        if node.get("topic_label"):
            bucket["label"] = node["topic_label"]
    return list(groups.values())


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
