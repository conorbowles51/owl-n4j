"""Immutable candidate materialization receipts and source claims."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "20260907_candidate_finalizations"
down_revision = "20260907_investigator_reading"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("financial_candidate_finalizations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", pg.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_file_id", pg.UUID(as_uuid=True), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", pg.UUID(as_uuid=True), sa.ForeignKey("financial_source_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ingestion_run_id", pg.UUID(as_uuid=True), sa.ForeignKey("financial_ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot", pg.JSONB(), nullable=False),
        sa.Column("actor", pg.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("transaction_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_id", "evidence_file_id", name="uq_candidate_finalization_file"),
        sa.UniqueConstraint("source_document_id", name="uq_candidate_finalization_document"),
        sa.CheckConstraint("length(source_sha256) = 64 AND length(snapshot_sha256) = 64", name="ck_candidate_finalization_digests"),
        sa.CheckConstraint("transaction_count > 0 AND transaction_count <= 1000", name="ck_candidate_finalization_count"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_candidate_finalization_reason"))
    op.create_table("financial_candidate_transactions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("finalization_id", pg.UUID(as_uuid=True), sa.ForeignKey("financial_candidate_finalizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", pg.UUID(as_uuid=True), sa.ForeignKey("financial_extraction_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_id", pg.UUID(as_uuid=True), sa.ForeignKey("financial_candidate_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_id", pg.UUID(as_uuid=True), sa.ForeignKey("financial_transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_claim_sha256", sa.String(64), nullable=False),
        sa.Column("review_revision", sa.String(64), nullable=False),
        sa.Column("original_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("candidate_id", name="uq_candidate_transaction_candidate"),
        sa.UniqueConstraint("transaction_id", name="uq_candidate_transaction_row"),
        sa.UniqueConstraint("finalization_id", "source_claim_sha256", name="uq_candidate_transaction_source"),
        sa.CheckConstraint("length(source_claim_sha256) = 64 AND length(review_revision) = 64 AND length(original_sha256) = 64", name="ck_candidate_transaction_digests"))
    for table in ("financial_candidate_finalizations", "financial_candidate_transactions"):
        op.execute(f"CREATE TRIGGER immutable_original BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION refuse_candidate_original_update()")
    op.execute("""
    CREATE FUNCTION validate_candidate_finalization() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM id FROM evidence_files WHERE id = NEW.evidence_file_id AND case_id = NEW.case_id FOR UPDATE;
      IF NOT FOUND OR NOT EXISTS (
        SELECT 1 FROM financial_source_documents d
        JOIN financial_ingestion_runs r ON r.id = d.ingestion_run_id
        JOIN evidence_files f ON f.id = d.evidence_file_id
        WHERE d.id = NEW.source_document_id AND d.case_id = NEW.case_id
          AND d.evidence_file_id = NEW.evidence_file_id AND r.id = NEW.ingestion_run_id
          AND r.case_id = NEW.case_id AND d.sha256_at_ingestion = NEW.source_sha256
          AND f.sha256 = NEW.source_sha256 AND d.extraction_layer = 4
          AND d.metadata->>'source_shape' = 'selected_document_rows'
      ) THEN RAISE EXCEPTION 'Candidate finalization source scope is inconsistent'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER scoped_finalization BEFORE INSERT ON financial_candidate_finalizations
      FOR EACH ROW EXECUTE FUNCTION validate_candidate_finalization();
    """)
    op.execute("""
    CREATE FUNCTION validate_candidate_transaction() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM financial_candidate_finalizations f
        JOIN financial_transactions t ON t.source_document_id = f.source_document_id AND t.case_id = f.case_id
        JOIN financial_candidate_mappings m ON m.case_id = f.case_id AND m.evidence_file_id = f.evidence_file_id
        JOIN financial_extraction_candidates c ON c.mapping_id = m.id
        JOIN financial_candidate_reviews r ON r.candidate_id = c.id
        WHERE f.id = NEW.finalization_id AND t.id = NEW.transaction_id AND c.id = NEW.candidate_id
          AND r.id = NEW.review_id AND r.status = 'resolved' AND t.extraction_layer = 4
          AND c.snapshot_sha256 = NEW.original_sha256 AND r.original_sha256 = NEW.original_sha256
          AND NOT EXISTS (SELECT 1 FROM financial_candidate_reviews later
                          WHERE later.candidate_id = c.id AND later.sequence > r.sequence)
      ) THEN RAISE EXCEPTION 'Candidate transaction source or review scope is inconsistent'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER scoped_candidate_transaction BEFORE INSERT ON financial_candidate_transactions
      FOR EACH ROW EXECUTE FUNCTION validate_candidate_transaction();
    """)
    op.execute("""
    CREATE FUNCTION refuse_finalized_candidate_changes() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE source_id uuid; source_case uuid;
    BEGIN
      IF TG_TABLE_NAME = 'financial_candidate_mappings' THEN
        source_id := NEW.evidence_file_id; source_case := NEW.case_id;
      ELSIF TG_TABLE_NAME = 'financial_extraction_candidates' THEN
        SELECT evidence_file_id, case_id INTO source_id, source_case
        FROM financial_candidate_mappings WHERE id = NEW.mapping_id;
      ELSE
        SELECT m.evidence_file_id, m.case_id INTO source_id, source_case
        FROM financial_candidate_mappings m JOIN financial_extraction_candidates c ON c.mapping_id = m.id
        WHERE c.id = NEW.candidate_id;
      END IF;
      PERFORM id FROM evidence_files WHERE id = source_id AND case_id = source_case FOR UPDATE;
      IF EXISTS (SELECT 1 FROM financial_candidate_finalizations
                 WHERE evidence_file_id = source_id AND case_id = source_case) THEN
        RAISE EXCEPTION 'PDF reading is finalized; use ledger correction history';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER sealed_candidate_mapping BEFORE INSERT ON financial_candidate_mappings
      FOR EACH ROW EXECUTE FUNCTION refuse_finalized_candidate_changes();
    CREATE TRIGGER sealed_extraction_candidate BEFORE INSERT ON financial_extraction_candidates
      FOR EACH ROW EXECUTE FUNCTION refuse_finalized_candidate_changes();
    CREATE TRIGGER sealed_candidate_review BEFORE INSERT ON financial_candidate_reviews
      FOR EACH ROW EXECUTE FUNCTION refuse_finalized_candidate_changes();
    """)


def downgrade():
    for table in ("financial_candidate_finalizations", "financial_candidate_transactions"):
        if op.get_bind().execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar_one():
            raise RuntimeError("Cannot downgrade while candidate finalization history exists.")
    op.execute("DROP TRIGGER sealed_candidate_mapping ON financial_candidate_mappings")
    op.execute("DROP TRIGGER sealed_extraction_candidate ON financial_extraction_candidates")
    op.execute("DROP TRIGGER sealed_candidate_review ON financial_candidate_reviews")
    op.drop_table("financial_candidate_transactions")
    op.drop_table("financial_candidate_finalizations")
    for function in ("refuse_finalized_candidate_changes", "validate_candidate_transaction", "validate_candidate_finalization"):
        op.execute(f"DROP FUNCTION {function}()")
