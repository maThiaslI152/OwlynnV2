"""Unified state management migration — adds all new tables and pgvector extension.

Revision ID: a1b2c3d4e5f6
Revises: 1060de570602
Create Date: 2026-07-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "1060de570602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # ------------------------------------------------------------------
    # Enable pgvector extension
    # ------------------------------------------------------------------
    if not is_sqlite:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # STM
    # ------------------------------------------------------------------
    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fact", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # Personal context
    # ------------------------------------------------------------------
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("occurrences", sa.Integer(), default=1, nullable=False),
        sa.Column("first_mentioned", sa.DateTime(timezone=True)),
        sa.Column("last_mentioned", sa.DateTime(timezone=True)),
        sa.Column("strength", sa.Float(), default=1.0, nullable=False),
        sa.UniqueConstraint("category", "name", name="uq_topic_cat_name"),
    )

    op.create_table(
        "interests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("count", sa.Integer(), default=1, nullable=False),
        sa.Column("first_observed", sa.DateTime(timezone=True)),
        sa.Column("last_observed", sa.DateTime(timezone=True)),
        sa.Column("strength", sa.Float(), default=1.0, nullable=False),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64)),
        sa.Column("message_count", sa.Integer(), default=0),
        sa.Column("user_messages", sa.Integer(), default=0),
        sa.Column("topics", JSONB, default={}),
        sa.Column("interests", JSONB, default={}),
        sa.Column("key_questions", JSONB, default=[]),
        sa.Column("summary_text", sa.Text()),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # User config
    # ------------------------------------------------------------------
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), primary_key=True, default=1),
        sa.Column("data", JSONB, nullable=False, default={}),
    )

    op.create_table(
        "personas",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("data", JSONB, nullable=False, default={}),
        sa.Column("is_active", sa.Boolean(), default=False, nullable=False),
    )

    # ------------------------------------------------------------------
    # Study
    # ------------------------------------------------------------------
    op.create_table(
        "courses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("data", JSONB, nullable=False, default={}),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "quiz_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("course_id", sa.String(64)),
        sa.Column("status", sa.String(32)),
        sa.Column("score", sa.Float()),
        sa.Column("questions", JSONB, default=[]),
        sa.Column("answers", JSONB, default=[]),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    # ------------------------------------------------------------------
    # Pentest engagement tables
    # ------------------------------------------------------------------
    op.create_table(
        "pentest_engagements",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.Text()),
        sa.Column("client", sa.Text()),
        sa.Column("phase", sa.String(32)),
        sa.Column("status", sa.String(32)),
        sa.Column("description", sa.Text()),
        sa.Column("assessor", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("engagement_data", JSONB, default={}),
        sa.Column("task_graph", JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "pentest_scope",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "engagement_id",
            sa.String(64),
            sa.ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("targets", JSONB, default=[]),
        sa.Column("exclusions", JSONB, default=[]),
        sa.Column("rules_of_engagement", sa.Text()),
    )

    op.create_table(
        "pentest_findings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "engagement_id",
            sa.String(64),
            sa.ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text()),
        sa.Column("severity", sa.String(16)),
        sa.Column("cvss", sa.Float()),
        sa.Column("cwe", sa.String(32)),
        sa.Column("cve", sa.String(32)),
        sa.Column("owasp_category", sa.Text()),
        sa.Column("target", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("remediation", sa.Text()),
        sa.Column("phase", sa.String(32)),
        sa.Column("status", sa.String(32)),
        sa.Column("tags", JSONB, default=[]),
        sa.Column("evidence_refs", JSONB, default=[]),
        sa.Column("discovered_at", sa.DateTime(timezone=True)),
        sa.Column("retested_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "pentest_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "engagement_id",
            sa.String(64),
            sa.ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ip", sa.String(64)),
        sa.Column("hostname", sa.Text()),
        sa.Column("ports", JSONB, default=[]),
        sa.Column("discovered_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "pentest_timeline",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "engagement_id",
            sa.String(64),
            sa.ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64)),
        sa.Column("summary", sa.Text()),
        sa.Column("extra", JSONB, default={}),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "pentest_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "engagement_id",
            sa.String(64),
            sa.ForeignKey("pentest_engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )

    # ------------------------------------------------------------------
    # Extraction job queue (replaces Redis stream)
    # ------------------------------------------------------------------
    op.create_table(
        "extraction_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("turn_id", sa.String(64), nullable=False, unique=True),
        sa.Column("mem0_uid", sa.String(64)),
        sa.Column("project_id", sa.String(64)),
        sa.Column("scenario_id", sa.String(64)),
        sa.Column("turn_text", sa.Text()),
        sa.Column("status", sa.String(16), default="pending", nullable=False),
        sa.Column("retry_count", sa.Integer(), default=0, nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_extraction_jobs_pending",
        "extraction_jobs",
        ["status", "enqueued_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ------------------------------------------------------------------
    # Vector stores (replaces Qdrant + redisvl)
    # ------------------------------------------------------------------
    op.create_table(
        "memory_vectors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text()),   # overridden by pgvector below
        sa.Column("user_id", sa.String(128)),
        sa.Column("project_id", sa.String(64)),
        sa.Column("tier", sa.String(16)),
        sa.Column("format", sa.String(32)),
        sa.Column("tags", JSONB, default=[]),
        sa.Column("meta_data", JSONB, default={}),
        sa.Column("confidence", sa.Float()),
        sa.Column("source", sa.String(64)),
        sa.Column("scenario_id", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Drop placeholder column and add proper vector column + index
    if not is_sqlite:
        op.drop_column("memory_vectors", "embedding")
        op.execute("ALTER TABLE memory_vectors ADD COLUMN embedding vector(768)")
        op.execute(
            "CREATE INDEX memory_vectors_embedding_idx ON memory_vectors "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
    op.create_index("ix_memory_vectors_user_project", "memory_vectors", ["user_id", "project_id"])

    op.create_table(
        "engagement_vectors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("engagement_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(64)),
        sa.Column("target", sa.Text()),
        sa.Column("output_preview", sa.Text()),
        sa.Column("output_length", sa.Integer()),
        sa.Column("embedding", sa.Text()),  # overridden below
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    if not is_sqlite:
        op.drop_column("engagement_vectors", "embedding")
        op.execute("ALTER TABLE engagement_vectors ADD COLUMN embedding vector(768)")
        op.execute(
            "CREATE INDEX engagement_vectors_embedding_idx ON engagement_vectors "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
        )
    op.create_index("ix_engagement_vectors_engagement_id", "engagement_vectors", ["engagement_id"])

    op.create_table(
        "semantic_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(64)),
        sa.Column("prompt_scoped", sa.Text()),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text()),  # overridden below
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    if not is_sqlite:
        op.drop_column("semantic_cache", "embedding")
        op.execute("ALTER TABLE semantic_cache ADD COLUMN embedding vector(768)")
        op.execute(
            "CREATE INDEX semantic_cache_embedding_idx ON semantic_cache "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.drop_table("semantic_cache")
    op.drop_table("engagement_vectors")
    op.drop_table("memory_vectors")
    op.drop_table("extraction_jobs")
    op.drop_table("pentest_credentials")
    op.drop_table("pentest_timeline")
    op.drop_table("pentest_targets")
    op.drop_table("pentest_findings")
    op.drop_table("pentest_scope")
    op.drop_table("pentest_engagements")
    op.drop_table("quiz_sessions")
    op.drop_table("courses")
    op.drop_table("personas")
    op.drop_table("user_profile")
    op.drop_table("conversations")
    op.drop_table("interests")
    op.drop_table("topics")
    op.drop_table("memories")
    if not is_sqlite:
        op.execute("DROP EXTENSION IF EXISTS vector")
