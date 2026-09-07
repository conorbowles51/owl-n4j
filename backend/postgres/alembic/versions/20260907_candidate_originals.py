"""Persist pending extraction originals separately from integer ledger rows."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "20260907_candidate_originals"
down_revision = "20260906_correction_decision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("financial_candidate_mappings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", pg.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_file_id", pg.UUID(as_uuid=True), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mapping_revision", sa.String(64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot", pg.JSONB(), nullable=False),
        sa.Column("actor", pg.JSONB(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_id", "evidence_file_id", "mapping_revision", name="uq_candidate_mapping_revision"),
        sa.CheckConstraint("length(mapping_revision) = 64 AND length(snapshot_sha256) = 64", name="ck_candidate_mapping_digests"),
        sa.CheckConstraint("candidate_count > 0 AND candidate_count <= 1000", name="ck_candidate_mapping_count"))
    op.create_index("ix_financial_candidate_mappings_case_id", "financial_candidate_mappings", ["case_id"])
    op.create_table("financial_extraction_candidates",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("mapping_id", pg.UUID(as_uuid=True), sa.ForeignKey("financial_candidate_mappings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_key", sa.String(64), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot", pg.JSONB(), nullable=False),
        sa.UniqueConstraint("mapping_id", "row_index", name="uq_candidate_mapping_row"),
        sa.UniqueConstraint("candidate_key", name="uq_extraction_candidate_key"),
        sa.CheckConstraint("row_index >= 0", name="ck_extraction_candidate_row"),
        sa.CheckConstraint("length(candidate_key) = 64 AND length(snapshot_sha256) = 64", name="ck_extraction_candidate_digests"))
    op.execute("""CREATE FUNCTION refuse_candidate_original_update() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Extraction originals are immutable; record a separate review or mapping revision';
        END $$""")
    for table in ("financial_candidate_mappings", "financial_extraction_candidates"):
        op.execute(f"CREATE TRIGGER immutable_original BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION refuse_candidate_original_update()")


def downgrade():
    for table in ("financial_extraction_candidates", "financial_candidate_mappings"):
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one():
            raise RuntimeError("Cannot downgrade while saved extraction originals exist.")
    op.drop_table("financial_extraction_candidates")
    op.drop_table("financial_candidate_mappings")
    op.execute("DROP FUNCTION refuse_candidate_original_update()")
