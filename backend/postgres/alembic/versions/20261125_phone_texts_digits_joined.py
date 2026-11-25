"""Indexes phone texts by their digits joined across spaces, so a number typed one way finds it stored another.

Folding turns ``(717) 555-0221`` into ``717 555 0221``; searching ``7175550221`` did not find it, and searching
``717-555-0221`` did not find ``+17175550221``. Measured on live 25 Nov: 10,424 contact numbers, 888 call and message
party numbers and 646 message bodies hold a number written with separators. The search now also matches the digits
with the spaces between them removed (services/search/number_words.py). This partial trigram index holds that joined
text for the texts of up to 1,000 characters that have digits split by a space (564,776 of 6,632,554 on live, 25 Nov);
without it the match reads every such text (an optional-space pattern took 68 s on the largest case). Built on a copy
of those live texts: 52 s and 95 MB; with the 22,382 longer texts (700 MB of email and log bodies) 4.5 minutes.

It also indexes phone files by file name for the phone search's "Files and documents" kind: a name search read all
1,656,482 files of the largest case in 14 to 18 s.

Built like 20261109_evidence_delete_fk_indexes_2: only writers and schema changes delay it, 1 s lock tries for up to
5 minutes; if it never gets the lock the release still succeeds and prints why (search stays correct, only slower
for number queries).

Revision ID: 20261125_phone_texts_digits_joined
Revises: 20261122_document_date_model_checks
Create Date: 2026-11-25
"""
import time

from alembic import op
import sqlalchemy as sa

revision = "20261125_phone_texts_digits_joined"
down_revision = "20261122_document_date_model_checks"
branch_labels = None
depends_on = None

# each expression must stay character for character what the search writes, or the planner cannot use the index:
# services/search/number_words.py (JOINED_SQL, SPLIT_SQL) and services/search/phone_search.py (FILE_NAME_SQL)
INDEXES = (
    ("ix_phone_texts_digits_joined", "phone_texts",
     "CREATE INDEX IF NOT EXISTS ix_phone_texts_digits_joined ON phone_texts USING gin ((regexp_replace(value_folded, "
     "'([0-9]) (?=[0-9])', '\\1', 'g')) gin_trgm_ops) WHERE value_folded ~ '[0-9] [0-9]' AND length(value_folded) "
     "<= 1000"),
    # a phone file by its name (not its folder path): 14 to 18 s on the largest case without it (1,656,482 files)
    ("ix_phone_files_name", "phone_files",
     "CREATE INDEX IF NOT EXISTS ix_phone_files_name ON phone_files USING gin ((lower(regexp_replace(local_path, "
     "'^.*[/\\\\]', ''))) gin_trgm_ops)"),
)
WINDOW_SECONDS = 300
POLL_SECONDS = 0.5
LOCK_WAIT = "1s"


def _build(bind, index, table, ddl):
    if bind.execute(sa.text("SELECT count(*) FROM pg_indexes WHERE indexname = :i"), dict(i=index)).scalar():
        return
    # Only locks that conflict with the build's SHARE lock: readers (AccessShare, RowShare) never delay it.
    holders = sa.text("SELECT count(DISTINCT pid) FROM pg_locks WHERE relation = CAST(:t AS regclass) "
                      "AND pid <> pg_backend_pid() AND mode NOT IN ('AccessShareLock', 'RowShareLock', 'ShareLock')")
    deadline = time.monotonic() + WINDOW_SECONDS
    tries = busy = 0
    started = time.monotonic()
    while True:
        if bind.execute(holders, dict(t=table)).scalar():
            busy += 1
        else:
            tries += 1
            try:
                bind.execute(sa.text("SET lock_timeout = '%s'" % LOCK_WAIT))
                bind.execute(sa.text("SET maintenance_work_mem = '256MB'"))
                started = time.monotonic()
                bind.execute(sa.text(ddl))
                break
            except sa.exc.OperationalError as error:
                if "lock timeout" not in str(error):
                    raise
            finally:
                bind.execute(sa.text("RESET lock_timeout"))
                bind.execute(sa.text("RESET maintenance_work_mem"))
        if time.monotonic() >= deadline:
            print("%s not created in %d s: %d polls found %s held, %d tries for the lock (%s each) timed out; rows "
                  "unchanged, the search it serves reads the table instead" % (index, WINDOW_SECONDS, busy, table,
                                                                                 tries, LOCK_WAIT))
            return
        time.sleep(POLL_SECONDS)
    print("%s created in %.0f s (try %d, %d polls busy)" % (index, time.monotonic() - started, tries, busy))


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for index, table, ddl in INDEXES:
            _build(bind, index, table, ddl)


def downgrade():
    for index, _, _ in INDEXES:
        op.execute("DROP INDEX IF EXISTS %s" % index)
