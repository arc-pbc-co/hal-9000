"""add chunk embeddings

Revision ID: 2b1a9f0c8d7e
Revises: 9e5ae07c7fdc
Create Date: 2026-05-02 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b1a9f0c8d7e"
down_revision: Union[str, None] = "9e5ae07c7fdc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create portable chunk embedding records and pgvector storage on Postgres."""
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("embedding_provider", sa.String(length=100), nullable=False),
        sa.Column("embedding_model", sa.String(length=256), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=False),
        sa.Column("vector_uri", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chunk_id",
            "embedding_provider",
            "embedding_model",
            name="uq_chunk_embeddings_chunk_provider_model",
        ),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE chunk_embeddings ADD COLUMN embedding_vector vector(1536)")


def downgrade() -> None:
    """Drop chunk embedding records."""
    op.drop_table("chunk_embeddings")
