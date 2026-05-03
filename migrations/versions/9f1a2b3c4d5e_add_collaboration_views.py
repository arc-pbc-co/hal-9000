"""add collaboration views

Revision ID: 9f1a2b3c4d5e
Revises: 8e0f1a2b3c4d
Create Date: 2026-05-03 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f1a2b3c4d5e"
down_revision: str | None = "8e0f1a2b3c4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create collections, saved searches, views, notifications, and audit events."""
    op.create_table(
        "research_collections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("slug", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_email", sa.String(length=320), nullable=True),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug", name="uq_research_collections_project_slug"),
    )
    op.create_index(
        "ix_research_collections_project",
        "research_collections",
        ["project_id", "status"],
    )
    op.create_table(
        "research_collection_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=512), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_by", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["research_collections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "target_type",
            "target_id",
            name="uq_research_collection_items_target",
        ),
    )
    op.create_index(
        "ix_research_collection_items_target",
        "research_collection_items",
        ["target_type", "target_id"],
    )
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("target", sa.String(length=50), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=True),
        sa.Column("owner_email", sa.String(length=320), nullable=True),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_saved_searches_project_name"),
    )
    op.create_index("ix_saved_searches_project", "saved_searches", ["project_id", "status"])
    op.create_table(
        "shared_project_views",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("slug", sa.String(length=256), nullable=False),
        sa.Column("view_type", sa.String(length=50), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=True),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "slug",
            name="uq_shared_project_views_project_slug",
        ),
    )
    op.create_index(
        "ix_shared_project_views_project",
        "shared_project_views",
        ["project_id", "status"],
    )
    op.create_table(
        "research_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("notification_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_notifications_recipient_status",
        "research_notifications",
        ["recipient_email", "status"],
    )
    op.create_index(
        "ix_research_notifications_project_run",
        "research_notifications",
        ["project_id", "run_id"],
    )
    op.create_table(
        "research_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=512), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_audit_events_project_run",
        "research_audit_events",
        ["project_id", "run_id"],
    )
    op.create_index(
        "ix_research_audit_events_target",
        "research_audit_events",
        ["target_type", "target_id"],
    )
    op.create_index("ix_research_audit_events_action", "research_audit_events", ["action"])


def downgrade() -> None:
    """Drop collaboration views."""
    op.drop_index("ix_research_audit_events_action", table_name="research_audit_events")
    op.drop_index("ix_research_audit_events_target", table_name="research_audit_events")
    op.drop_index("ix_research_audit_events_project_run", table_name="research_audit_events")
    op.drop_table("research_audit_events")
    op.drop_index("ix_research_notifications_project_run", table_name="research_notifications")
    op.drop_index(
        "ix_research_notifications_recipient_status",
        table_name="research_notifications",
    )
    op.drop_table("research_notifications")
    op.drop_index("ix_shared_project_views_project", table_name="shared_project_views")
    op.drop_table("shared_project_views")
    op.drop_index("ix_saved_searches_project", table_name="saved_searches")
    op.drop_table("saved_searches")
    op.drop_index("ix_research_collection_items_target", table_name="research_collection_items")
    op.drop_table("research_collection_items")
    op.drop_index("ix_research_collections_project", table_name="research_collections")
    op.drop_table("research_collections")
