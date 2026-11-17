"""Dates read from document text, one row per reading, with the words and page they came from (lx-docdates B).

Revision ID: 20261119_document_date_readings
Revises: 20261118_answer_ratings_chat
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261119_document_date_readings"
down_revision = "20261118_answer_ratings_chat"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_date_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("date_from", sa.Date, nullable=False),
        sa.Column("date_to", sa.Date, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("rule", sa.String(80), nullable=False, server_default=""),
        sa.Column("words", sa.Text, nullable=False, server_default=""),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("corrects_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_date_readings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_by_name", sa.String(300), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('written', 'signed', 'period', 'received')", name="ck_document_date_readings_kind"),
        sa.CheckConstraint("source IN ('rule', 'model', 'person')", name="ck_document_date_readings_source"),
    )
    op.create_index("uq_document_date_readings_value", "document_date_readings",
                    ["evidence_file_id", "kind", "source", "rule", "date_from", "date_to"], unique=True)
    op.create_index("ix_document_date_readings_case", "document_date_readings", ["case_id", "date_from"])


def downgrade():
    op.drop_index("ix_document_date_readings_case", table_name="document_date_readings")
    op.drop_index("uq_document_date_readings_value", table_name="document_date_readings")
    op.drop_table("document_date_readings")
