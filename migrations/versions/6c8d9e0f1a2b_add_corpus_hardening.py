"""add corpus hardening metadata

Revision ID: 6c8d9e0f1a2b
Revises: 5b7c8d9e0f1a
Create Date: 2026-05-03 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c8d9e0f1a2b"
down_revision: str | None = "5b7c8d9e0f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add document versioning, source quality, and dedupe reports."""
    op.add_column("documents", sa.Column("source_identifier", sa.String(length=512), nullable=True))
    op.add_column("documents", sa.Column("source_version", sa.String(length=100), nullable=True))
    op.add_column("documents", sa.Column("version_group_key", sa.String(length=512), nullable=True))
    op.add_column(
        "documents",
        sa.Column("is_current_version", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "documents",
        sa.Column("supersedes_document_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("refresh_policy", sa.String(length=50), nullable=False, server_default="manual"),
    )
    op.add_column("documents", sa.Column("refresh_interval_days", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("last_refreshed_at", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("next_refresh_at", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("normalized_doi", sa.String(length=256), nullable=True))
    op.add_column("documents", sa.Column("citation_key", sa.String(length=256), nullable=True))
    op.add_column("documents", sa.Column("normalized_citation", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("source_quality_score", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("source_quality_label", sa.String(length=50), nullable=True))
    op.add_column("documents", sa.Column("source_quality_json", sa.Text(), nullable=True))
    op.create_index("ix_documents_source_identifier", "documents", ["source_identifier"])
    op.create_index("ix_documents_version_group_key", "documents", ["version_group_key"])
    op.create_index("ix_documents_normalized_doi", "documents", ["normalized_doi"])

    op.create_table(
        "corpus_dedupe_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_type", sa.String(length=100), nullable=False),
        sa.Column("scope", sa.String(length=256), nullable=False),
        sa.Column("duplicate_group_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_document_count", sa.Integer(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Remove corpus hardening metadata."""
    op.drop_table("corpus_dedupe_reports")
    op.drop_index("ix_documents_normalized_doi", table_name="documents")
    op.drop_index("ix_documents_version_group_key", table_name="documents")
    op.drop_index("ix_documents_source_identifier", table_name="documents")
    op.drop_column("documents", "source_quality_json")
    op.drop_column("documents", "source_quality_label")
    op.drop_column("documents", "source_quality_score")
    op.drop_column("documents", "normalized_citation")
    op.drop_column("documents", "citation_key")
    op.drop_column("documents", "normalized_doi")
    op.drop_column("documents", "next_refresh_at")
    op.drop_column("documents", "last_refreshed_at")
    op.drop_column("documents", "refresh_interval_days")
    op.drop_column("documents", "refresh_policy")
    op.drop_column("documents", "supersedes_document_id")
    op.drop_column("documents", "is_current_version")
    op.drop_column("documents", "version_group_key")
    op.drop_column("documents", "source_version")
    op.drop_column("documents", "source_identifier")
