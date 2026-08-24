"""Add thought node cluster and dormancy columns for organic map scaling.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-24 16:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | None = None
depends_on: str | None = None

_COLUMNS = (
    ("topic_cluster_id", sa.String(128)),
    ("topic_label", sa.String(256)),
    ("dormancy_score", sa.Float()),
    ("importance_score", sa.Float()),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "thought_nodes" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("thought_nodes")}
    for name, col_type in _COLUMNS:
        if name in existing:
            continue
        op.add_column("thought_nodes", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "thought_nodes" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("thought_nodes")}
    for name, _col_type in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("thought_nodes", name)
