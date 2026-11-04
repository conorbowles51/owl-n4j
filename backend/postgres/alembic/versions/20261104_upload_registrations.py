"""Folder registration runs in the background (lx-uploadfollow C).

``evidence_upload_registrations``: one row per selection being registered, so every server process can tell the
page how far registration has come ("Registering n of N") and whether it is still running. A registration that
stops (a server restart) leaves its heartbeat behind and no evidence rows: they commit together with the receipt.
No foreign key to the selection, on purpose: the registration holds the selection's row FOR UPDATE until it
commits, and a key check from the progress write would wait on that lock, so no progress could be written while
registration runs. Discarding a selection removes its row. New table; no existing row changes.
"""
from alembic import op

revision = "20261104_upload_registrations"
down_revision = "20261104_phone_perceptual_hash"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE evidence_upload_registrations (
            group_id uuid PRIMARY KEY,
            phase varchar(20) NOT NULL,
            done integer NOT NULL DEFAULT 0,
            total integer NOT NULL DEFAULT 0,
            error jsonb NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            heartbeat_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz NULL
        )
    """)


def downgrade():
    op.execute("DROP TABLE evidence_upload_registrations")
