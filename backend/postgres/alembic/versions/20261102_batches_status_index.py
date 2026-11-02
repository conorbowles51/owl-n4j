"""financial_import_batches gets an index on status, so the batch loop's two polls stop reading the whole table.

Measured 2 Nov 02:50 (live, pg_stat_statements since 1 Nov 01:55): 29,299 polls of each kind; the one that looks
for saves waiting read 158 blocks per call, the other 75. The table had grown back to 188 pages (1.5 MB) for 90
visible rows after the 31 Oct compaction: its rows are updated about 2.7 million times (94% HOT), and every poll
scans every page. Both polls ask for status IN ('preparing', 'pausing') with the statuses as parameters.
EXPLAIN (ANALYZE, BUFFERS) with a generic plan, index created inside a rolled-back transaction on live: 188 -> 5
and 188 -> 2 shared blocks, 0 rows before and after (nothing preparing or pausing at the time).

An index on status alone: a partial index would not serve the generic plan (the statuses are parameters), and an
index on updated_at would end HOT updates on a table updated millions of times; status rarely changes.

CREATE INDEX holds a SHARE lock (writers wait, readers do not) for the build, well under a second for 1.5 MB. It is
only asked for in a moment no other session holds a lock on the table, waiting at most 1 s, for up to 5 minutes;
if that never happens the release still succeeds and prints why (the polls stay as they are; no row is touched
either way). Not CONCURRENTLY: a lock timeout there leaves an invalid index behind.
"""
import time

from alembic import op
import sqlalchemy as sa

revision = "20261102_batches_status_index"
down_revision = "20261101_users_password_changed_at"
branch_labels = None
depends_on = None

TABLE = 'financial_import_batches'
INDEX = 'ix_financial_import_batches_status'
WINDOW_SECONDS = 300
POLL_SECONDS = 0.5
LOCK_WAIT = '1s'

HOLDERS = sa.text("SELECT count(DISTINCT pid) FROM pg_locks WHERE relation = 'financial_import_batches'::regclass "
                  "AND pid <> pg_backend_pid()")
EXISTS = sa.text("SELECT count(*) FROM pg_indexes WHERE tablename = 'financial_import_batches' "
                 "AND indexname = 'ix_financial_import_batches_status'")


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        op.create_index(INDEX, TABLE, ['status'], if_not_exists=True)
        return
    with op.get_context().autocommit_block():
        if bind.execute(EXISTS).scalar():
            return
        deadline = time.monotonic() + WINDOW_SECONDS
        tries = busy = 0
        while True:
            if bind.execute(HOLDERS).scalar():
                busy += 1
            else:
                tries += 1
                try:
                    bind.execute(sa.text("SET lock_timeout = '%s'" % LOCK_WAIT))
                    bind.execute(sa.text('CREATE INDEX IF NOT EXISTS %s ON %s (status)' % (INDEX, TABLE)))
                    break
                except sa.exc.OperationalError as error:
                    if 'lock timeout' not in str(error):
                        raise
                finally:
                    bind.execute(sa.text('RESET lock_timeout'))
            if time.monotonic() >= deadline:
                print('%s not created in %d s: %d polls found the table held, %d tries for the lock (%s each) '
                      'timed out; rows unchanged, the batch polls still read the whole table'
                      % (INDEX, WINDOW_SECONDS, busy, tries, LOCK_WAIT))
                return
            time.sleep(POLL_SECONDS)
        print('%s created (try %d, %d polls busy)' % (INDEX, tries, busy))


def downgrade():
    op.execute('DROP INDEX IF EXISTS %s' % INDEX)
