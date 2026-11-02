"""Phone decisions in the case decision ledger (docs/cellebrite/02 section 8.8, 6.8, 6.10).

- ``adjudications.reason_kind``: ``typed`` (the person's words; every earlier row) or ``standard`` (a reason the
  system built from what was shown, for routine confirmations and identity links; displayed as "Standard reason").
- Subjects ``phone_identity`` and ``phone_record``; the decisions of 8.8, and 05's ``confirm_phone_result`` and
  ``reject_phone_result`` (their subject, ``phone_analysis_result``, lands with 05's results table).
- ``phone_record_subjects`` (1.2): a row per record a decision is about, created with the first decision.
- ``phone_identity_links``: the current link of each identity to a dossier, rebuilt from the ledger and never its
  source (8.8); ``phone_identity_rejections`` likewise for rejected pairs.
- ``phone_identity_suggestions`` (8.7).
- ``phone_mapping_proposals.case_id`` so a case correction (6.8 step 5) names its case.
- ``phone_interpretation_progress``: records read so far in a running pass, written outside the pass's
  transaction so a correction's re-reading can show true progress (07 J-8 step 4).
"""
from alembic import op
import sqlalchemy as sa

revision = "20261102_phone_decisions"
down_revision = "20261102_phone_identities"
branch_labels = None
depends_on = None

SUBJECTS = "'transaction', 'statement_period', 'source_document', 'account', 'evidence_file', 'phone_extraction'"
DECISIONS = ("'supersede_duplicate', 'restore_document', 'purge_duplicate', 'quarantine_row', 'release_row', "
             "'explain_balance_failure', 'reclassify_document', 'admit_financial_document', 'correct_transaction', "
             "'set_account_party', 'set_counterparty_party', 'set_account_identity', 'keep_printed_holders', "
             "'supersede_phone_extraction'")
NEW_SUBJECTS = "'phone_identity', 'phone_record'"
NEW_DECISIONS = ("'link_phone_identity', 'unlink_phone_identity', 'reject_phone_identity_link', "
                 "'restore_phone_identity_link', 'set_phone_owner', 'set_phone_device_zone', 'set_phone_default_region', "
                 "'set_phone_clock_offset', 'correct_phone_value', 'set_phone_identity_label', "
                 "'apply_phone_zone_to_offsetless', 'allow_phone_external_processing', "
                 "'accept_phone_reconciliation_difference', 'set_phone_label', 'confirm_phone_result', "
                 "'reject_phone_result', 'confirm_phone_reading', 'correct_phone_reading', 'mark_not_duplicate'")

TABLES = """
CREATE TABLE phone_record_subjects (
  id             uuid PRIMARY KEY,
  case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id  uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  document_index smallint NOT NULL,
  ordinal        integer NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_phone_record_subjects_ext ON phone_record_subjects (case_id, extraction_id);

CREATE TABLE phone_identity_links (
  case_id      uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  identity_id  uuid NOT NULL REFERENCES phone_identities(id),
  dossier_id   uuid NOT NULL,
  decision_id  uuid NOT NULL,
  PRIMARY KEY (identity_id)
);
CREATE INDEX ix_phone_identity_links_dossier ON phone_identity_links (case_id, dossier_id);

CREATE TABLE phone_identity_rejections (
  case_id      uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  identity_id  uuid NOT NULL REFERENCES phone_identities(id),
  target       text NOT NULL,
  decision_id  uuid NOT NULL,
  PRIMARY KEY (identity_id, target)
);

CREATE TABLE phone_identity_suggestions (
  id                  uuid PRIMARY KEY,
  case_id             uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  identity_ids        uuid[] NOT NULL,
  dossier_id          uuid,
  reasons             jsonb NOT NULL,
  score               numeric(3,2) NOT NULL,
  state               varchar(16) NOT NULL DEFAULT 'open' CHECK (state IN ('open','accepted','rejected','superseded')),
  computed_generation integer NOT NULL DEFAULT 0,
  computed_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_phone_identity_suggestions_case ON phone_identity_suggestions (case_id, state, score DESC);

ALTER TABLE phone_mapping_proposals ADD COLUMN case_id uuid REFERENCES cases(id) ON DELETE CASCADE;

CREATE TABLE phone_interpretation_progress (
  extraction_id  uuid PRIMARY KEY REFERENCES phone_extractions(id) ON DELETE CASCADE,
  records_total  bigint NOT NULL DEFAULT 0,
  records_done   bigint NOT NULL DEFAULT 0,
  started_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz
);
"""


def _constraints(subjects, decisions):
    op.drop_constraint("ck_adjudications_subject_type", "adjudications", type_="check")
    op.create_check_constraint("ck_adjudications_subject_type", "adjudications", f"subject_type IN ({subjects})")
    op.drop_constraint("ck_adjudications_decision", "adjudications", type_="check")
    op.create_check_constraint("ck_adjudications_decision", "adjudications", f"decision IN ({decisions})")


def upgrade():
    op.add_column("adjudications", sa.Column("reason_kind", sa.String(16), nullable=False, server_default="typed"))
    op.create_check_constraint("ck_adjudications_reason_kind", "adjudications", "reason_kind IN ('typed', 'standard')")
    _constraints(f"{SUBJECTS}, {NEW_SUBJECTS}", f"{DECISIONS}, {NEW_DECISIONS}")
    op.execute(TABLES)


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT count(*) FROM adjudications WHERE subject_type IN ({NEW_SUBJECTS}) OR "
                            f"decision IN ({NEW_DECISIONS})")).scalar_one():
        raise RuntimeError("Cannot remove retained phone decisions.")
    op.execute("DROP TABLE phone_interpretation_progress; ALTER TABLE phone_mapping_proposals DROP COLUMN case_id; DROP TABLE phone_identity_suggestions; "
               "DROP TABLE phone_identity_rejections; DROP TABLE phone_identity_links; DROP TABLE phone_record_subjects;")
    _constraints(SUBJECTS, DECISIONS)
    op.drop_constraint("ck_adjudications_reason_kind", "adjudications", type_="check")
    op.drop_column("adjudications", "reason_kind")
