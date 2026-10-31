"""financial_import_batches compacted once (VACUUM FULL): same rows, the file shrinks to its rows' size.

Measured 31 Oct 02:30: 89 rows (about 1 MB) in 2,708 pages (22 MB heap); every status poll reads all 2,708
pages (EXPLAIN ANALYZE: shared hit=2708, 2.7 ms), about 1,850 polls in 45 minutes (pg_stat_statements). Plain
autovacuum frees the space for reuse but never shrinks the file.

VACUUM FULL holds an exclusive lock on the table for the rewrite (under a second for 1 MB). It waits at most
2 s per try for that lock, 5 tries; if another session holds the table all that time the compaction is skipped
with a printed line and the migration still succeeds (no row is touched either way).
"""
import time

from alembic import op
import sqlalchemy as sa

revision = "20261031_batches_compact"
down_revision = "20261031_pg_stat_statements"
branch_labels = None
depends_on = None

TRIES = 5
LOCK_WAIT = '2s'


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    with op.get_context().autocommit_block():
        before = bind.execute(sa.text("SELECT pg_relation_size('financial_import_batches')")).scalar()
        for attempt in range(1, TRIES + 1):
            try:
                bind.execute(sa.text("SET lock_timeout = '%s'" % LOCK_WAIT))
                bind.execute(sa.text('VACUUM (FULL, ANALYZE) financial_import_batches'))
                break
            except sa.exc.OperationalError as error:
                if 'lock timeout' not in str(error) and 'canceling statement due to lock timeout' not in str(error):
                    raise
                if attempt == TRIES:
                    print('financial_import_batches not compacted: the table stayed locked by another session '
                          '(%d tries of %s); rows unchanged' % (TRIES, LOCK_WAIT))
                    return
                time.sleep(1)
            finally:
                bind.execute(sa.text('RESET lock_timeout'))
        after = bind.execute(sa.text("SELECT pg_relation_size('financial_import_batches')")).scalar()
        print('financial_import_batches compacted: %d -> %d bytes' % (before, after))


def downgrade():
    pass
