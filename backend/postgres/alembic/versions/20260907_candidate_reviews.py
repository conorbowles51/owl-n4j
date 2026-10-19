"""Append candidate reviews without changing extraction originals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "20260907_candidate_reviews"
down_revision = "20260907_candidate_originals"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("financial_candidate_reviews",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", pg.UUID(as_uuid=True), sa.ForeignKey("financial_extraction_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reading", pg.JSONB(none_as_null=True), nullable=True),
        sa.Column("actor", pg.JSONB(), nullable=False),
        sa.Column("original_sha256", sa.String(64), nullable=False),
        sa.Column("previous_revision", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "sequence", name="uq_candidate_review_sequence"),
        sa.CheckConstraint("sequence > 0", name="ck_candidate_review_sequence"),
        sa.CheckConstraint("status IN ('pending', 'resolved', 'rejected')", name="ck_candidate_review_status"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_candidate_review_reason"),
        sa.CheckConstraint("(status = 'resolved' AND reading IS NOT NULL) OR (status <> 'resolved' AND reading IS NULL)", name="ck_candidate_review_reading"))
    op.execute("CREATE TRIGGER immutable_original BEFORE UPDATE ON financial_candidate_reviews FOR EACH ROW EXECUTE FUNCTION refuse_candidate_original_update()")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM financial_candidate_reviews")).scalar_one():
        raise RuntimeError("Cannot downgrade while candidate review history exists.")
    op.drop_table("financial_candidate_reviews")
