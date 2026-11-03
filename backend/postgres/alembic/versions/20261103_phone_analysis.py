"""Phone analysis framework (docs/cellebrite/05 section 3.3, 3.7, 3.8; 4.3.1).

- ``phone_analysis_runs``, ``phone_analysis_results``, ``phone_analysis_result_records``,
  ``phone_analysis_measurements``: an approach's runs (idempotent per inputs and parameters), its results with both
  directions, the records and ledger rows each rests on, and the gate measurements.
- ``phone_sensitive_reveals``: append-only log of every Reveal of a sensitive value (actor, time, locator, field).
- ``phone_institution_aliases``: a person's case-level "this sender is this institution" with a reason (approach 1).
- Decision subject ``phone_analysis_result`` (its decisions ``confirm_phone_result`` and ``reject_phone_result`` are
  already in the constraint, 20261102_phone_decisions).
"""
from alembic import op

revision = "20261103_phone_analysis"
down_revision = "20261103_phone_derived_open_unique"
branch_labels = None
depends_on = None

SUBJECTS = ("'transaction', 'statement_period', 'source_document', 'account', 'evidence_file', 'phone_extraction', "
            "'phone_identity', 'phone_record'")
APPROACHES = ("'money_signals', 'message_reconciliation', 'deletion_timeline', 'awareness', 'device_users', "
              "'other_devices', 'typed_words', 'media_spread', 'intent', 'plans', 'relationships', "
              "'extraction_comparison', 'incident_window', 'common_contacts', 'contact_matrix', 'number_switching', "
              "'link_edges', 'reparse_comparison'")

UP = f"""
CREATE TABLE phone_analysis_runs (
  id                 uuid PRIMARY KEY,
  case_id            uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  approach           varchar(40) NOT NULL CHECK (approach IN ({APPROACHES})),
  approach_version   varchar(20) NOT NULL,
  parameters         jsonb NOT NULL,
  parameters_sha256  char(64) NOT NULL,
  input_manifest     jsonb NOT NULL,
  input_revision     char(64) NOT NULL,
  status             varchar(16) NOT NULL CHECK (status IN ('queued','running','completed','failed','cancelled',
                                                            'superseded')),
  requested_by       varchar(320) NOT NULL,
  counts             jsonb,
  coverage           jsonb NOT NULL DEFAULT '{{}}',
  progress           jsonb NOT NULL DEFAULT '{{}}',
  cancel_requested   boolean NOT NULL DEFAULT false,
  error              text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  started_at         timestamptz,
  finished_at        timestamptz,
  CONSTRAINT ck_phone_analysis_runs_failed_named CHECK (status <> 'failed' OR coalesce(btrim(error), '') <> '')
);
CREATE UNIQUE INDEX ux_phone_analysis_runs_inputs ON phone_analysis_runs
  (case_id, approach, approach_version, input_revision, parameters_sha256);
CREATE INDEX ix_phone_analysis_runs_case ON phone_analysis_runs (case_id, approach, created_at DESC);
CREATE INDEX ix_phone_analysis_runs_queue ON phone_analysis_runs (status, created_at) WHERE status IN ('queued','running');

CREATE TABLE phone_analysis_results (
  id            uuid PRIMARY KEY,
  run_id        uuid NOT NULL REFERENCES phone_analysis_runs(id) ON DELETE CASCADE,
  case_id       uuid NOT NULL,
  result_key    char(64) NOT NULL,
  kind          varchar(48) NOT NULL,
  strength      varchar(24) NOT NULL,
  measures      jsonb NOT NULL,
  directions    jsonb NOT NULL,
  sensitive     boolean NOT NULL DEFAULT false,
  period_start  timestamptz,
  period_end    timestamptz
);
CREATE UNIQUE INDEX ux_phone_analysis_results_key ON phone_analysis_results (run_id, result_key);
CREATE INDEX ix_phone_analysis_results_kind ON phone_analysis_results (case_id, kind);
CREATE INDEX ix_phone_analysis_results_period ON phone_analysis_results (case_id, period_start);

CREATE TABLE phone_analysis_result_records (
  id                     uuid PRIMARY KEY,
  result_id              uuid NOT NULL REFERENCES phone_analysis_results(id) ON DELETE CASCADE,
  extraction_id          uuid,
  record_uid             uuid,
  field_path             varchar(512),
  ledger_transaction_id  uuid,
  role                   varchar(40) NOT NULL
);
CREATE UNIQUE INDEX ux_phone_analysis_result_records ON phone_analysis_result_records (result_id, md5(
  coalesce(extraction_id::text, '') || '|' || coalesce(record_uid::text, '') || '|' || coalesce(field_path, '') || '|'
  || coalesce(ledger_transaction_id::text, '') || '|' || role));
CREATE INDEX ix_phone_analysis_result_records_record ON phone_analysis_result_records (record_uid);
CREATE INDEX ix_phone_analysis_result_records_ledger ON phone_analysis_result_records (ledger_transaction_id);

-- the subject of a decision on a result (3.7): one per (case, approach, result_key), so a decision carries across
-- reruns whose inputs give the same result; created with the first decision
CREATE TABLE phone_analysis_result_subjects (
  id          uuid PRIMARY KEY,
  case_id     uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  approach    varchar(40) NOT NULL,
  result_key  char(64) NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_phone_analysis_result_subjects ON phone_analysis_result_subjects (case_id, approach, result_key);

CREATE TABLE phone_analysis_measurements (
  id               uuid PRIMARY KEY,
  scope            varchar(16) NOT NULL CHECK (scope IN ('case','corpus')),
  case_id          uuid REFERENCES cases(id) ON DELETE CASCADE,
  approach         varchar(40) NOT NULL,
  measure_version  varchar(20) NOT NULL,
  result           jsonb NOT NULL,
  gate             varchar(16) NOT NULL CHECK (gate IN ('build','do_not_build','inconclusive')),
  recorded_at      timestamptz NOT NULL DEFAULT now(),
  recorded_by      varchar(320) NOT NULL
);
CREATE INDEX ix_phone_analysis_measurements ON phone_analysis_measurements (approach, recorded_at DESC);

CREATE TABLE phone_sensitive_reveals (
  id             uuid PRIMARY KEY,
  case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  record_uid     uuid NOT NULL,
  extraction_id  uuid NOT NULL,
  field_path     varchar(512) NOT NULL,
  value_index    integer NOT NULL DEFAULT 0,
  actor_user_id  uuid,
  actor_email    varchar(320) NOT NULL,
  actor_name     varchar(255) NOT NULL,
  revealed_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_phone_sensitive_reveals ON phone_sensitive_reveals (case_id, record_uid);
CREATE FUNCTION phone_sensitive_reveals_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'phone_sensitive_reveals is append-only'; END $$;
CREATE TRIGGER tr_phone_sensitive_reveals_append_only BEFORE UPDATE OR DELETE ON phone_sensitive_reveals
  FOR EACH ROW WHEN (pg_trigger_depth() = 0) EXECUTE FUNCTION phone_sensitive_reveals_append_only();

CREATE TABLE phone_institution_aliases (
  id                uuid PRIMARY KEY,
  case_id           uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  institution_id    varchar(120) NOT NULL,
  channel           varchar(24) NOT NULL CHECK (channel IN ('app_package','web_domain','sms_sender','email_domain')),
  value_normalised  varchar(320) NOT NULL,
  reason            text NOT NULL CHECK (btrim(reason) <> ''),
  actor             varchar(320) NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_phone_institution_aliases ON phone_institution_aliases (case_id, channel, value_normalised);
"""

DOWN = """
DROP TABLE IF EXISTS phone_institution_aliases;
DROP TABLE IF EXISTS phone_sensitive_reveals;
DROP FUNCTION IF EXISTS phone_sensitive_reveals_append_only();
DROP TABLE IF EXISTS phone_analysis_measurements;
DROP TABLE IF EXISTS phone_analysis_result_subjects;
DROP TABLE IF EXISTS phone_analysis_result_records;
DROP TABLE IF EXISTS phone_analysis_results;
DROP TABLE IF EXISTS phone_analysis_runs;
"""


def _subjects(subjects):
    op.drop_constraint("ck_adjudications_subject_type", "adjudications", type_="check")
    op.create_check_constraint("ck_adjudications_subject_type", "adjudications", f"subject_type IN ({subjects})")


def upgrade():
    op.execute(UP)
    _subjects(f"{SUBJECTS}, 'phone_analysis_result'")


def downgrade():
    _subjects(SUBJECTS)
    op.execute(DOWN)
