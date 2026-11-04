"""Deleted items: a deleted case or evidence file is kept for 30 days and can be restored (lx-casebin).

``deleted_at`` / ``deleted_by_user_id`` on ``cases`` and ``evidence_files``: set while the item sits in Deleted items;
every database read hides it (postgres/soft_delete.py) until it is restored (both cleared) or purged (row removed by
the delete code used before). ``deleted_state`` on ``evidence_files`` keeps what the delete moved aside (the graph
recycle-bin keys of its Document node and exclusive entities, the chunk states it changed) so a restore puts back
exactly that. Partial indexes: the hide filter looks up deleted rows only, and there are few.
"""
from alembic import op

revision = "20261104_casebin"
down_revision = "20261103_phone_search_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE cases
            ADD COLUMN deleted_at timestamptz NULL,
            ADD COLUMN deleted_by_user_id uuid NULL REFERENCES users(id) ON DELETE SET NULL;
        CREATE INDEX ix_cases_deleted ON cases (id) WHERE deleted_at IS NOT NULL;
        ALTER TABLE evidence_files
            ADD COLUMN deleted_at timestamptz NULL,
            ADD COLUMN deleted_by_user_id uuid NULL REFERENCES users(id) ON DELETE SET NULL,
            ADD COLUMN deleted_state jsonb NULL;
        CREATE INDEX ix_evidence_files_deleted ON evidence_files (id) WHERE deleted_at IS NOT NULL;
    """)


def downgrade():
    op.execute("""
        DROP INDEX IF EXISTS ix_evidence_files_deleted;
        ALTER TABLE evidence_files DROP COLUMN deleted_state, DROP COLUMN deleted_by_user_id, DROP COLUMN deleted_at;
        DROP INDEX IF EXISTS ix_cases_deleted;
        ALTER TABLE cases DROP COLUMN deleted_by_user_id, DROP COLUMN deleted_at;
    """)
