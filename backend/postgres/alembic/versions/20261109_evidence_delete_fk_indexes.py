"""Indexes on the columns that point at evidence_files without one, so deleting a file stops reading whole tables.

Every deleted evidence file makes PostgreSQL look for rows that point at it, to clear or remove them. Four such
columns had no index, so each look-up read the whole table. Measured live 9 Nov 2026 (EXPLAIN ANALYZE, read-only):
evidence_upload_sessions.evidence_id 82.7 ms (about 300,000 rows), evidence_files.duplicate_of_id 23.9 ms,
ingestion_logs.evidence_file_id 3.4 ms, financial_import_batch_items.file_id 1.3 ms (its unique index does not
lead with file_id): about 111 ms per deleted file. Purging a 5,000-file folder from Deleted items in the
Verification case took 807.5 s in one transaction (04:12-04:25 UTC), and the whole time it held the case's audit
lock, so a merge in that case waited 12 min 36 s and the browser gave up. Five smaller tables with the same gap
are indexed too, so every column that points at evidence_files has an index.

Each index is built the way 20261102_batches_status_index builds its own: only when no other session holds a lock
on the table, waiting at most 1 s per try, for up to 5 minutes; if that never happens the release still succeeds and
prints why (deletes stay as slow as before; no row is touched either way). Not CONCURRENTLY: a lock timeout there
leaves an invalid index behind.

Revision ID: 20261109_evidence_delete_fk_indexes
Revises: 20261109_significant_relationships
Create Date: 2026-11-09
"""
import time

from alembic import op
import sqlalchemy as sa

revision = "20261109_evidence_delete_fk_indexes"
down_revision = "20261109_significant_relationships"
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
    holders = sa.text("SELECT count(DISTINCT pid) FROM pg_locks WHERE relation = CAST(:t AS regclass) "
                      "AND pid <> pg_backend_pid()")
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
    for table, column in INDEXES:
        op.execute("DROP INDEX IF EXISTS %s" % _name(table, column))
