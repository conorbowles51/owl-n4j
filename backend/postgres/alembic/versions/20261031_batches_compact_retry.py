"""financial_import_batches compacted (VACUUM FULL), second try: waits for a moment no other session holds the table.

The first try (20261031_batches_compact, release 02:39 on 31 Oct) was skipped: two background processes each kept
one transaction on the table for minutes, longer than its 20 tries of 2 s. Measured 31 Oct 09:50 (pg_locks on the
table, one sample a second for 90 s): the table was free in 70 of 90 samples and no holder's transaction was older
than 3 s. Table at 09:46: 89 rows in 22,183,936 bytes (2,708 pages), which every status poll reads in full.

This try looks at pg_locks every half second, for up to 5 minutes, for a moment when no other session holds a
lock on the table, and only then asks for the exclusive lock, waiting at most 1 s for it, so a person's request
that reads the table is held for at most 1 s per try. If the 5 minutes pass without a compaction it prints why
and the migration still succeeds.

Every row is checksummed just before and just after the compaction and the result printed: rows, checksum, and
any row whose checksum differs, with its updated_at. VACUUM FULL rewrites the file, never a row; the live app
keeps writing to the table outside the exclusive lock (status, lease), so a row a writer changed in the
milliseconds between the two reads is listed with its updated_at rather than failing the release, and so is a
row added or removed by a writer in that gap.
"""
import time

from alembic import op
import sqlalchemy as sa

revision = "20261031_batches_compact_retry"
down_revision = "20261031_batches_compact"
branch_labels = None
depends_on = None

TABLE = 'financial_import_batches'
WINDOW_SECONDS = 300
POLL_SECONDS = 0.5
LOCK_WAIT = '1s'

HOLDERS = sa.text("SELECT count(DISTINCT pid) FROM pg_locks WHERE relation = 'financial_import_batches'::regclass "
                  "AND pid <> pg_backend_pid()")
ROWS = sa.text("SELECT b.id::text, md5(b::text), b.updated_at::text FROM financial_import_batches b")
SIZE = sa.text("SELECT pg_relation_size('financial_import_batches')")


def _is_lock_timeout(error):
    return 'lock timeout' in str(error)


def _rows(bind):
    """{id: (md5 of the whole row, updated_at)} for every row."""
    return {key: (digest, updated) for key, digest, updated in bind.execute(ROWS).all()}


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    with op.get_context().autocommit_block():
        before_size = bind.execute(SIZE).scalar()
        deadline = time.monotonic() + WINDOW_SECONDS
        tries = busy = 0
        while True:
            if bind.execute(HOLDERS).scalar():
                busy += 1
            else:
                tries += 1
                before_rows = _rows(bind)
                try:
                    bind.execute(sa.text("SET lock_timeout = '%s'" % LOCK_WAIT))
                    bind.execute(sa.text('VACUUM (FULL, ANALYZE) %s' % TABLE))
                    break
                except sa.exc.OperationalError as error:
                    if not _is_lock_timeout(error):
                        raise
                finally:
                    bind.execute(sa.text('RESET lock_timeout'))
            if time.monotonic() >= deadline:
                print('%s not compacted in %d s: %d polls found the table held, %d tries for the lock (%s each) '
                      'timed out; rows unchanged' % (TABLE, WINDOW_SECONDS, busy, tries, LOCK_WAIT))
                return
            time.sleep(POLL_SECONDS)
        after_rows = _rows(bind)
        after_size = bind.execute(SIZE).scalar()
        both = set(before_rows) & set(after_rows)
        changed = sorted((key, after_rows[key][1]) for key in both if before_rows[key][0] != after_rows[key][0])
        added = sorted((key, after_rows[key][1]) for key in set(after_rows) - both)
        removed = sorted(set(before_rows) - both)
        print('%s compacted: %d -> %d bytes; %d rows before, %d after, %d identical; changed by a writer: %s; '
              'added: %s; removed: %s (try %d, %d polls busy)'
              % (TABLE, before_size, after_size, len(before_rows), len(after_rows), len(both) - len(changed),
                 changed or 'none', added or 'none', removed or 'none', tries, busy))


def downgrade():
    pass
