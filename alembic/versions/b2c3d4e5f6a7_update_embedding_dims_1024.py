"""Update embedding dimensions to 1024 for mxbai embedding model.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-22 14:45:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if not is_sqlite:
        # memory_vectors
        op.execute("DROP INDEX IF EXISTS memory_vectors_embedding_idx")
        op.execute("ALTER TABLE memory_vectors DROP COLUMN IF EXISTS embedding")
        op.execute("ALTER TABLE memory_vectors ADD COLUMN embedding vector(1024)")
        op.execute(
            "CREATE INDEX memory_vectors_embedding_idx ON memory_vectors "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )

        # engagement_vectors
        op.execute("DROP INDEX IF EXISTS engagement_vectors_embedding_idx")
        op.execute("ALTER TABLE engagement_vectors DROP COLUMN IF EXISTS embedding")
        op.execute("ALTER TABLE engagement_vectors ADD COLUMN embedding vector(1024)")
        op.execute(
            "CREATE INDEX engagement_vectors_embedding_idx ON engagement_vectors "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
        )

        # semantic_cache
        op.execute("DROP INDEX IF EXISTS semantic_cache_embedding_idx")
        op.execute("ALTER TABLE semantic_cache DROP COLUMN IF EXISTS embedding")
        op.execute("ALTER TABLE semantic_cache ADD COLUMN embedding vector(1024)")
        op.execute(
            "CREATE INDEX semantic_cache_embedding_idx ON semantic_cache "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if not is_sqlite:
        # Revert back to 768 dims
        op.execute("DROP INDEX IF EXISTS memory_vectors_embedding_idx")
        op.execute("ALTER TABLE memory_vectors DROP COLUMN IF EXISTS embedding")
        op.execute("ALTER TABLE memory_vectors ADD COLUMN embedding vector(768)")
        op.execute(
            "CREATE INDEX memory_vectors_embedding_idx ON memory_vectors "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )

        op.execute("DROP INDEX IF EXISTS engagement_vectors_embedding_idx")
        op.execute("ALTER TABLE engagement_vectors DROP COLUMN IF EXISTS embedding")
        op.execute("ALTER TABLE engagement_vectors ADD COLUMN embedding vector(768)")
        op.execute(
            "CREATE INDEX engagement_vectors_embedding_idx ON engagement_vectors "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
        )

        op.execute("DROP INDEX IF EXISTS semantic_cache_embedding_idx")
        op.execute("ALTER TABLE semantic_cache DROP COLUMN IF EXISTS embedding")
        op.execute("ALTER TABLE semantic_cache ADD COLUMN embedding vector(768)")
        op.execute(
            "CREATE INDEX semantic_cache_embedding_idx ON semantic_cache "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
        )
