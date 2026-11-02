"""Index phone_record_summaries.root_record_uid for the record panel (03 section 3.6).

The record panel reads a record's descendants by ``root_record_uid``; without an index every panel open scans the
whole table (measured on the live box 2 November: a sequential scan of 101,990 rows, 73.8 ms).
"""
from alembic import op

revision = "20261103_phone_summary_root_idx"
down_revision = "20261102_pol_key_dates"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE INDEX IF NOT EXISTS ix_phone_record_summaries_root ON phone_record_summaries (root_record_uid)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_phone_record_summaries_root")
