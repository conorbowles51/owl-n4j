"""Builds the evidence-delete indexes 20261109_evidence_delete_fk_indexes could not, waiting only for writers.

That migration waited for a moment when no session held any lock on the table. On live (9 Nov 06:30-06:48 UTC)
evidence_upload_sessions and evidence_files were held in all 599 polls of each 5-minute window, by readers, which
never conflict with building an index: "ix_evidence_upload_sessions_evidence_id not created in 300 s" and the same
for evidence_files.duplicate_of_id; the other seven were built. Deleting a file still read the whole upload sessions
table (68.7 ms per deleted file, measured after). This migration counts only the locks that conflict with the
build's SHARE lock (writers and schema changes), tries with a 1 s lock limit, for up to 5 minutes per index; if it
never gets one the release still succeeds and prints why. An index that exists is left alone.

Revision ID: 20261109_evidence_delete_fk_indexes_2
Revises: 20261109_evidence_delete_fk_indexes
Create Date: 2026-11-09
"""
import time

from alembic import op
import sqlalchemy as sa

revision = "20261109_evidence_delete_fk_indexes_2"
down_revision = "20261109_evidence_delete_fk_indexes"
branch_labels = None
depends_on = None

INDEXES = (
    ("evidence_upload_sessions", "evidence_id"),
    ("evidence_files", "duplicate_of_id"),
    ("ingestion_logs", "evidence_file_id"),
    ("financial_import_batch_items", "file_id"),
    # Small today (0 to 1,883 rows on 9 Nov), indexed so every column pointing at evidence_files has one
    # (tests/test_postgres_evidence_delete_fk_indexes.py).
    ("financial_recovery_items", "file_id"),
    ("phone_extraction_containers", "evidence_file_id"),
    ("financial_candidate_mappings", "evidence_file_id"),
    ("financial_candidate_finalizations", "evidence_file_id"),
    ("financial_pdf_nominations", "evidence_file_id"),
)
WINDOW_SECONDS = 300
POLL_SECONDS = 0.5
LOCK_WAIT = "1s"


def _name(table: str, column: str) -> str:
    return "ix_%s_%s" % (table, column)


def _build(bind, table: str, column: str) -> None:
    index = _name(table, column)
    if bind.execute(sa.text("SELECT count(*) FROM pg_indexes WHERE tablename = :t AND indexname = :i"),
                    dict(t=table, i=index)).scalar():
        return
    # Only locks that conflict with the build's SHARE lock: readers (AccessShare, RowShare) never delay it.
    holders = sa.text("SELECT count(DISTINCT pid) FROM pg_locks WHERE relation = CAST(:t AS regclass) "
                      "AND pid <> pg_backend_pid() AND mode NOT IN ('AccessShareLock', 'RowShareLock', 'ShareLock')")
    deadline = time.monotonic() + WINDOW_SECONDS
    tries = busy = 0
    while True:
        if bind.execute(holders, dict(t=table)).scalar():
            busy += 1
        else:
            tries += 1
            try:
                bind.execute(sa.text("SET lock_timeout = '%s'" % LOCK_WAIT))
                bind.execute(sa.text("CREATE INDEX IF NOT EXISTS %s ON %s (%s)" % (index, table, column)))
                break
            except sa.exc.OperationalError as error:
                if "lock timeout" not in str(error):
                    raise
            finally:
                bind.execute(sa.text("RESET lock_timeout"))
        if time.monotonic() >= deadline:
            print("%s not created in %d s: %d polls found the table held, %d tries for the lock (%s each) timed "
                  "out; rows unchanged, deleting an evidence file still reads the whole of %s"
                  % (index, WINDOW_SECONDS, busy, tries, LOCK_WAIT, table))
            return
        time.sleep(POLL_SECONDS)
    print("%s created (try %d, %d polls busy)" % (index, tries, busy))


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        for table, column in INDEXES:
            op.create_index(_name(table, column), table, [column], if_not_exists=True)
        return
    with op.get_context().autocommit_block():
        for table, column in INDEXES:
            _build(bind, table, column)


def downgrade():
    pass  # the indexes belong to 20261109_evidence_delete_fk_indexes; its downgrade drops them
