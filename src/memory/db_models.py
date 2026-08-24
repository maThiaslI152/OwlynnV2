"""
Database models for unified PostgreSQL state management.

Covers all stores previously on JSON flat files, Redis, and Qdrant:
  - STM (memories)
  - Personal context (topics, interests, conversations)
  - User config (user_profile, personas)
  - Study (courses, quiz_sessions)
  - Pentest engagement (pentest_engagements + related tables)
  - Extraction job queue (extraction_jobs)
  - Vector stores (memory_vectors, engagement_vectors, semantic_cache)
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from src.models.base import Base

Base.__allow_unmapped__ = True

# pgvector type — loaded lazily so SQLite test env doesn't break
try:
    from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]

    from src.config.config_loader import config

    _EMBED_DIMS = config.get_embedding_dimensions()
    VECTOR_TYPE = Vector(_EMBED_DIMS)
except ImportError:  # pragma: no cover
    from sqlalchemy import PickleType

    VECTOR_TYPE = PickleType()


# ---------------------------------------------------------------------------
# Short-Term Memory (STM)
# ---------------------------------------------------------------------------


class Memory(Base):
    """Atomic fact saved across chat sessions (replaces data/memories.json)."""

    __tablename__ = "memories"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    fact: str = Column(Text, nullable=False, unique=True)
    created_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Personal Context
# ---------------------------------------------------------------------------


class Topic(Base):
    """User interest topic with decay tracking (replaces data/topics.json)."""

    __tablename__ = "topics"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    category: str = Column(String(64), nullable=False)
    name: str = Column(String(128), nullable=False)
    occurrences: int = Column(Integer, default=1, nullable=False)
    first_mentioned: datetime.datetime = Column(DateTime(timezone=True))
    last_mentioned: datetime.datetime = Column(DateTime(timezone=True))
    strength: float = Column(Float, default=1.0, nullable=False)

    __table_args__ = (
        # category+name is the natural key
        __import__("sqlalchemy").UniqueConstraint(
            "category", "name", name="uq_topic_cat_name"
        ),
    )


class Interest(Base):
    """User behavioural interest with decay tracking (replaces data/interests.json)."""

    __tablename__ = "interests"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(128), nullable=False, unique=True)
    count: int = Column(Integer, default=1, nullable=False)
    first_observed: datetime.datetime = Column(DateTime(timezone=True))
    last_observed: datetime.datetime = Column(DateTime(timezone=True))
    strength: float = Column(Float, default=1.0, nullable=False)


class Conversation(Base):
    """Summarised conversation record (replaces data/conversations.json)."""

    __tablename__ = "conversations"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: str = Column(String(64))
    message_count: int = Column(Integer, default=0)
    user_messages: int = Column(Integer, default=0)
    topics: dict[str, Any] = Column(JSON, default=dict)
    interests: dict[str, Any] = Column(JSON, default=dict)
    key_questions: list[Any] = Column(JSON, default=list)
    summary_text: str = Column(Text)
    recorded_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# User config
# ---------------------------------------------------------------------------


class UserProfile(Base):
    """Single-row user configuration (replaces data/user_profile.json)."""

    __tablename__ = "user_profile"

    id: int = Column(Integer, primary_key=True, default=1)  # always row 1
    data: dict[str, Any] = Column(JSON, nullable=False, default=dict)


class Persona(Base):
    """Named persona (replaces data/persona.json + data/personas/)."""

    __tablename__ = "personas"

    id: str = Column(String(64), primary_key=True)
    data: dict[str, Any] = Column(JSON, nullable=False, default=dict)
    is_active: bool = Column(Boolean, default=False, nullable=False)


# ---------------------------------------------------------------------------
# Study
# ---------------------------------------------------------------------------


class Course(Base):
    """Registered study course (replaces data/courses.json)."""

    __tablename__ = "courses"

    id: str = Column(String(64), primary_key=True)
    data: dict[str, Any] = Column(JSON, nullable=False, default=dict)
    created_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QuizSession(Base):
    """Quiz session state (replaces data/quiz_sessions/*.json)."""

    __tablename__ = "quiz_sessions"

    id: str = Column(String(64), primary_key=True)
    course_id: str = Column(String(64))
    status: str = Column(String(32))  # pending / active / completed
    score: float = Column(Float)
    questions: list[Any] = Column(JSON, default=list)
    answers: list[Any] = Column(JSON, default=list)
    started_at: datetime.datetime = Column(DateTime(timezone=True))
    completed_at: datetime.datetime = Column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Pentest Engagement
# ---------------------------------------------------------------------------


class PentestEngagement(Base):
    """Top-level pentest engagement (replaces engagement.json)."""

    __tablename__ = "pentest_engagements"

    id: str = Column(String(64), primary_key=True)
    name: str = Column(Text)
    client: str = Column(Text)
    phase: str = Column(String(32))  # scope/recon/exploit/report/completed
    status: str = Column(String(32))  # active/paused/completed/archived
    description: str = Column(Text)
    assessor: str = Column(Text)
    notes: str = Column(Text)  # replaces notes.md
    engagement_data: dict[str, Any] = Column(
        JSON, default=dict
    )  # replaces engagement_data.json
    task_graph: dict[str, Any] = Column(JSON, default=dict)  # replaces task_graph.json
    created_at: datetime.datetime = Column(DateTime(timezone=True))
    updated_at: datetime.datetime = Column(DateTime(timezone=True))

    scope: PentestScope = relationship(
        "PentestScope",
        back_populates="engagement",
        uselist=False,
        cascade="all, delete-orphan",
    )
    findings: list[PentestFinding] = relationship(
        "PentestFinding", back_populates="engagement", cascade="all, delete-orphan"
    )
    targets: list[PentestTarget] = relationship(
        "PentestTarget", back_populates="engagement", cascade="all, delete-orphan"
    )
    timeline: list[PentestTimeline] = relationship(
        "PentestTimeline", back_populates="engagement", cascade="all, delete-orphan"
    )
    credentials: list[PentestCredentials] = relationship(
        "PentestCredentials", back_populates="engagement", cascade="all, delete-orphan"
    )


class PentestScope(Base):
    """Scope definition (replaces scope.json)."""

    __tablename__ = "pentest_scope"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    engagement_id: str = Column(
        String(64),
        ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    targets: list[Any] = Column(JSON, default=list)
    exclusions: list[Any] = Column(JSON, default=list)
    rules_of_engagement: str = Column(Text)

    engagement: PentestEngagement = relationship(
        "PentestEngagement", back_populates="scope"
    )


class PentestFinding(Base):
    """Security finding (replaces findings.json entries)."""

    __tablename__ = "pentest_findings"

    id: str = Column(String(64), primary_key=True)
    engagement_id: str = Column(
        String(64),
        ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: str = Column(Text)
    severity: str = Column(String(16))  # critical/high/medium/low/info
    cvss: float = Column(Float)
    cwe: str = Column(String(32))
    cve: str = Column(String(32))
    owasp_category: str = Column(Text)
    target: str = Column(Text)
    description: str = Column(Text)
    remediation: str = Column(Text)
    phase: str = Column(String(32))
    status: str = Column(String(32))  # suspected/confirmed/remediated/…
    tags: list[Any] = Column(JSON, default=list)
    evidence_refs: list[Any] = Column(JSON, default=list)
    discovered_at: datetime.datetime = Column(DateTime(timezone=True))
    retested_at: datetime.datetime = Column(DateTime(timezone=True))

    engagement: PentestEngagement = relationship(
        "PentestEngagement", back_populates="findings"
    )


class PentestTarget(Base):
    """Discovered host/target (replaces targets.json entries)."""

    __tablename__ = "pentest_targets"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    engagement_id: str = Column(
        String(64),
        ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    ip: str = Column(String(64))
    hostname: str = Column(Text)
    ports: list[Any] = Column(JSON, default=list)
    discovered_at: datetime.datetime = Column(DateTime(timezone=True))

    engagement: PentestEngagement = relationship(
        "PentestEngagement", back_populates="targets"
    )


class PentestTimeline(Base):
    """Chronological action log entry (replaces timeline.json)."""

    __tablename__ = "pentest_timeline"

    id: str = Column(String(64), primary_key=True)
    engagement_id: str = Column(
        String(64),
        ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: str = Column(String(64))
    summary: str = Column(Text)
    extra: dict[str, Any] = Column(JSON, default=dict)
    occurred_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    engagement: PentestEngagement = relationship(
        "PentestEngagement", back_populates="timeline"
    )


class PentestCredentials(Base):
    """Fernet-encrypted credential blob (replaces credentials.enc file)."""

    __tablename__ = "pentest_credentials"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    engagement_id: str = Column(
        String(64),
        ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    data: bytes = Column(LargeBinary, nullable=False)  # Fernet-encrypted blob

    engagement: PentestEngagement = relationship(
        "PentestEngagement", back_populates="credentials"
    )


# ---------------------------------------------------------------------------
# Extraction Job Queue (replaces Redis stream owlynn:memory:extract)
# ---------------------------------------------------------------------------


class ExtractionJob(Base):
    """Background memory extraction job queue."""

    __tablename__ = "extraction_jobs"

    id: int = Column(BigInteger, primary_key=True, autoincrement=True)
    turn_id: str = Column(String(64), nullable=False, unique=True)
    mem0_uid: str = Column(String(64))
    project_id: str = Column(String(64))
    scenario_id: str = Column(String(64))
    turn_text: str = Column(Text)
    status: str = Column(String(16), default="pending", nullable=False)
    # pending → processing → done / failed
    retry_count: int = Column(Integer, default=0, nullable=False)
    error: str = Column(Text)
    enqueued_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: datetime.datetime = Column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Vector Stores (replaces Qdrant + redisvl)
# ---------------------------------------------------------------------------


class MemoryVector(Base):
    """LTM embedding (replaces Qdrant owlynn_memory_nomic collection)."""

    __tablename__ = "memory_vectors"

    id: str = Column(String(64), primary_key=True)
    content: str = Column(Text, nullable=False)
    embedding: Any = Column(VECTOR_TYPE)
    user_id: str = Column(String(128))
    project_id: str = Column(String(64))
    tier: str = Column(String(16))
    format: str = Column(String(32))
    tags: list[Any] = Column(JSON, default=list)
    meta_data: dict[str, Any] = Column(JSON, default=dict)
    confidence: float = Column(Float)
    source: str = Column(String(64))
    scenario_id: str = Column(String(64))
    created_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EngagementVector(Base):
    """Per-engagement tool output embedding (replaces Qdrant pentest_{id} collections)."""

    __tablename__ = "engagement_vectors"

    id: str = Column(String(64), primary_key=True)
    engagement_id: str = Column(String(64), nullable=False)
    tool_name: str = Column(String(64))
    target: str = Column(Text)
    output_preview: str = Column(Text)
    output_length: int = Column(Integer)
    embedding: Any = Column(VECTOR_TYPE)
    created_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SemanticCacheEntry(Base):
    """Semantic response cache (replaces Redis redisvl owlynn_semantic_cache)."""

    __tablename__ = "semantic_cache"

    id: int = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id: str = Column(String(64))
    prompt_scoped: str = Column(Text)
    response: str = Column(Text, nullable=False)
    embedding: Any = Column(VECTOR_TYPE)
    created_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Thought Graph / Mindmap
# ---------------------------------------------------------------------------


class ThoughtNode(Base):
    """A node in the unified thought graph (replaces flat chat sessions)."""

    __tablename__ = "thought_nodes"

    id: str = Column(String(128), primary_key=True)  # LangGraph thread_id
    title: str = Column(String(256), nullable=False, default="New Thought")
    summary: str = Column(Text, default="")
    mode: str = Column(String(32), default="normal", nullable=False)
    scenario_id: str | None = Column(String(64), nullable=True)
    engagement_id: str | None = Column(String(64), nullable=True)
    course_id: str | None = Column(String(64), nullable=True)
    status: str = Column(String(32), default="active", nullable=False)
    tags: list[Any] = Column(JSON, default=list)
    canvas_x: float | None = Column(Float, nullable=True)
    canvas_y: float | None = Column(Float, nullable=True)
    pinned: bool = Column(Boolean, default=False)
    embedding: Any = Column(VECTOR_TYPE, nullable=True)
    created_at: float = Column(Float, nullable=False)
    last_active_at: float = Column(Float, nullable=False)
    topic_cluster_id: str | None = Column(String(128), nullable=True)
    topic_label: str | None = Column(String(256), nullable=True)
    dormancy_score: float | None = Column(Float, nullable=True)
    importance_score: float | None = Column(Float, nullable=True)


class ThoughtEdge(Base):
    """A directed semantic edge connecting two thought nodes."""

    __tablename__ = "thought_edges"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    source_id: str = Column(
        String(128), ForeignKey("thought_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_id: str = Column(
        String(128), ForeignKey("thought_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation: str = Column(String(64), default="relates_to", nullable=False)
    weight: float = Column(Float, default=1.0, nullable=False)
    auto_generated: bool = Column(Boolean, default=True, nullable=False)
    created_at: datetime.datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
