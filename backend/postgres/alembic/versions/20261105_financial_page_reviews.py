"""Saved reviews of original PDF pages (coverage disposition): an additive table; nothing reads it for totals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261105_financial_page_reviews"
down_revision = "20261105_evidence_passage_links"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "financial_page_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=True),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("saved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("saved_by_name", sa.String(255), nullable=True),
        sa.Column("saved_by_email", sa.String(255), nullable=True),
        sa.Column("origin", postgresql.JSONB(), nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("undone_by_name", sa.String(255), nullable=True),
        sa.CheckConstraint("page_number >= 1", name="ck_financial_page_reviews_page"),
        sa.CheckConstraint("disposition IN ('supporting_correspondence', 'continuation', 'blank', 'other')",
                           name="ck_financial_page_reviews_disposition"),
    )
    op.create_index("ix_financial_page_reviews_file_page", "financial_page_reviews", ["evidence_file_id", "page_number"])
    op.create_index("ix_financial_page_reviews_case", "financial_page_reviews", ["case_id"])


def downgrade():
    op.drop_table("financial_page_reviews")
