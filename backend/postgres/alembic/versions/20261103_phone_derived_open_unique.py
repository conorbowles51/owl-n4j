"""One open reading per phone file and kind (03 section 8.3, M-3).

Two requests for the same file and kind could both see no open reading and both insert one (a double click, two
people). A unique partial index on the open states makes the second insert a no-op; the request then returns the
reading already open. Any duplicate open readings left by the race are closed first, keeping the oldest, with
the reason stated on the row (live had none when this was written).
"""
from alembic import op

revision = "20261103_phone_derived_open_unique"
down_revision = "20261103_phone_derived_texts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE phone_derived_texts d SET state = 'failed', finished_at = now(), "
        "error = 'A second request for the same reading; the first one is kept.' "
        "WHERE d.state IN ('queued', 'running') AND EXISTS (SELECT 1 FROM phone_derived_texts o WHERE "
        "o.case_id = d.case_id AND o.file_uid = d.file_uid AND o.kind = d.kind AND o.state IN ('queued', 'running') "
        "AND (o.created_at, o.id) < (d.created_at, d.id))")
    op.execute(
        "CREATE UNIQUE INDEX uq_phone_derived_texts_open ON phone_derived_texts (case_id, file_uid, kind) "
        "WHERE state IN ('queued', 'running')")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_phone_derived_texts_open")
