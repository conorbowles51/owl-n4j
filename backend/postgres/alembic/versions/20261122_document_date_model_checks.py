"""Files the document dates model read and found no date in, by the text it read, so a second run does not ask again.

Revision ID: 20261122_document_date_model_checks
Revises: 20261122_lead_finder_beat
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261122_document_date_model_checks"
down_revision = "20261122_lead_finder_beat"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_date_model_checks",
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("rule", sa.String(80), nullable=False, server_default=""),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("document_date_model_checks")
