"""Attach evidence files (photos first) to Timeline events.

Revision ID: 20261112_timeline_event_files
Revises: 20261111_agent_dossier_actions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261112_timeline_event_files"
down_revision = "20261111_agent_dossier_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("timeline_event_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(200), nullable=False),
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("added_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("case_id", "event_key", "evidence_file_id", name="uq_timeline_event_file"))
    op.create_index("ix_timeline_event_files_case_id", "timeline_event_files", ["case_id"])
    op.create_index("ix_timeline_event_files_evidence_file_id", "timeline_event_files", ["evidence_file_id"])


def downgrade():
    op.drop_table("timeline_event_files")
