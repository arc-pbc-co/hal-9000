"""add output versions

Revision ID: 8e0f1a2b3c4d
Revises: 7d9e0f1a2b3c
Create Date: 2026-05-03 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e0f1a2b3c4d"
down_revision: str | None = "7d9e0f1a2b3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create output version history records."""
    op.create_table(
        "research_output_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("output_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("format", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("artifact_uri", sa.String(length=1024), nullable=True),
        sa.Column("source_json", sa.Text(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["output_id"], ["research_outputs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "output_id",
            "version_number",
            name="uq_research_output_versions_output_number",
        ),
    )
    op.create_index(
        "ix_research_output_versions_output",
        "research_output_versions",
        ["output_id", "version_number"],
    )


def downgrade() -> None:
    """Drop output version history records."""
    op.drop_index("ix_research_output_versions_output", table_name="research_output_versions")
    op.drop_table("research_output_versions")
