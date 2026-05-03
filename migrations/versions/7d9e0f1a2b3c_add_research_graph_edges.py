"""add research graph edges

Revision ID: 7d9e0f1a2b3c
Revises: 6c8d9e0f1a2b
Create Date: 2026-05-03 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d9e0f1a2b3c"
down_revision: str | None = "6c8d9e0f1a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create polymorphic research graph edge records."""
    op.create_table(
        "research_graph_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=512), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=512), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_graph_edges_source",
        "research_graph_edges",
        ["source_type", "source_id"],
    )
    op.create_index(
        "ix_research_graph_edges_target",
        "research_graph_edges",
        ["target_type", "target_id"],
    )
    op.create_index(
        "ix_research_graph_edges_relationship",
        "research_graph_edges",
        ["relationship_type"],
    )
    op.create_index(
        "ix_research_graph_edges_project_run",
        "research_graph_edges",
        ["project_id", "run_id"],
    )


def downgrade() -> None:
    """Drop research graph edges."""
    op.drop_index("ix_research_graph_edges_project_run", table_name="research_graph_edges")
    op.drop_index("ix_research_graph_edges_relationship", table_name="research_graph_edges")
    op.drop_index("ix_research_graph_edges_target", table_name="research_graph_edges")
    op.drop_index("ix_research_graph_edges_source", table_name="research_graph_edges")
    op.drop_table("research_graph_edges")
