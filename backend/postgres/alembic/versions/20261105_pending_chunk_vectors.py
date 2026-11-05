"""Document chunks waiting for their vector while the embedding service refuses (evidence-engine pending_chunks)."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261105_pending_chunk_vectors"
down_revision = "20261105_financial_page_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pending_chunk_vectors",
        sa.Column("chunk_id", sa.Text(), primary_key=True),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("evidence_file_id", UUID(as_uuid=True),
                  sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("revision_id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_metadata", JSONB(), nullable=False),
        sa.Column("publication_state", sa.String(16), server_default="draft", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pending_chunk_vectors_document", "pending_chunk_vectors", ["document_id", "revision_id"])
    op.create_index("ix_pending_chunk_vectors_file", "pending_chunk_vectors", ["evidence_file_id"])
    op.create_index("ix_pending_chunk_vectors_state", "pending_chunk_vectors", ["publication_state", "created_at"])


def downgrade():
    op.drop_table("pending_chunk_vectors")
