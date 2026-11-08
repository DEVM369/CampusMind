"""CampusMind Basic/Hybrid RAG metadata and keyword index.

Revision ID: 20260923_0002
Revises: 20260923_0001
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_0002"
down_revision = "20260923_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(length=128), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.add_column("document_chunks", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_document_chunks_embedding_model", "document_chunks", ["embedding_model"], unique=False)
    # pg_trgm was enabled in infrastructure baseline/4. This index accelerates keyword/fuzzy retrieval for Chinese text.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_trgm "
        "ON document_chunks USING gin (content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_trgm")
    op.drop_index("ix_document_chunks_embedding_model", table_name="document_chunks")
    op.drop_column("document_chunks", "embedded_at")
    op.drop_column("document_chunks", "embedding_dimensions")
    op.drop_column("document_chunks", "embedding_model")
