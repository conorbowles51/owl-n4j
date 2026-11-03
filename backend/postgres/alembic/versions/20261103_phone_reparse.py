"""Independent re-parse runs and the rows the tool read (05 section 17.3).

``phone_reparse_runs``: one run of a pinned ALEAPP or iLEAPP over one phone's verified files, with the tool, version,
git commit, licence, command line, the rebuilt tree's counts, exit code, run time, peak memory and output hashes.
``phone_reparse_rows``: the rows of the tool's own output for the artefacts the reviewed mapping reads, kept as the
tool wrote them, with the mapped kind and the natural key the comparison uses. Never merged into captured rows and
never read as the report's records: a comparison (approach ``reparse_comparison``) reads both side by side.

Revision ID: 20261103_phone_reparse
Revises: 20261103_merge_audio_review
"""
from alembic import op

revision = "20261103_phone_reparse"
down_revision = "20261103_merge_audio_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE phone_reparse_runs (
  id               uuid PRIMARY KEY,
  case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id    uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  tool             varchar(16) NOT NULL CHECK (tool IN ('aleapp', 'ileapp')),
  tool_version     varchar(32) NOT NULL,
  tool_commit      char(40) NOT NULL,
  tool_licence     varchar(16) NOT NULL,
  status           varchar(16) NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
  command_line     jsonb,
  tree             jsonb,
  exit_code        integer,
  stopped          text,
  seconds          double precision,
  peak_rss_mb      double precision,
  output_manifest_sha256 char(64),
  outputs          jsonb,
  artefact_counts  jsonb,
  mapping_version  varchar(32),
  error            text,
  requested_by     varchar(320) NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  started_at       timestamptz,
  finished_at      timestamptz,
  CHECK (status <> 'failed' OR error IS NOT NULL)
);
CREATE INDEX ix_phone_reparse_runs_case ON phone_reparse_runs(case_id, extraction_id, created_at DESC);

CREATE TABLE phone_reparse_rows (
  run_id           uuid NOT NULL REFERENCES phone_reparse_runs(id) ON DELETE CASCADE,
  artefact         varchar(128) NOT NULL,
  row_index        integer NOT NULL,
  kind             varchar(32) NOT NULL,
  natural_key      text,
  instant          timestamptz,
  instant_text     text,
  source_path      text,
  values           jsonb NOT NULL,
  PRIMARY KEY (run_id, artefact, row_index)
);
CREATE INDEX ix_phone_reparse_rows_key ON phone_reparse_rows(run_id, kind, natural_key);
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS phone_reparse_rows; DROP TABLE IF EXISTS phone_reparse_runs;")
