"""add review annotations

Revision ID: 5b7c8d9e0f1a
Revises: 4a6b7c8d9e0f
Create Date: 2026-05-03 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b7c8d9e0f1a"
down_revision: str | None = "4a6b7c8d9e0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create review comments and annotations."""
    op.create_table(
        "review_annotations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=True),
        sa.Column("author_email", sa.String(length=320), nullable=True),
        sa.Column("annotation_type", sa.String(length=50), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("resolved_by", sa.String(length=320), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_annotations_target",
        "review_annotations",
        ["target_type", "target_id"],
    )
    op.create_index(
        "ix_review_annotations_run_status",
        "review_annotations",
        ["run_id", "status"],
    )


def downgrade() -> None:
    """Drop review comments and annotations."""
    op.drop_index("ix_review_annotations_run_status", table_name="review_annotations")
    op.drop_index("ix_review_annotations_target", table_name="review_annotations")
    op.drop_table("review_annotations")
