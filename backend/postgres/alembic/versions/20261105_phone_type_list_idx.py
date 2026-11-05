"""Indexes for the list of each record type (03 section 7.5): a window in report or time order reads from the index
at its keyset position, and the exact total counts the type's rows of one generation, never the table.
"""
from alembic import op

revision = "20261105_phone_type_list_idx"
down_revision = "20261104_phone_original_bundles"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE INDEX IF NOT EXISTS ix_phone_record_summaries_list_report ON phone_record_summaries "
               "(extraction_id, generation, model_type, document_index, ordinal)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_phone_record_summaries_list_time ON phone_record_summaries "
               "(extraction_id, generation, model_type, first_instant, document_index, ordinal)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_phone_record_summaries_list_time")
    op.execute("DROP INDEX IF EXISTS ix_phone_record_summaries_list_report")
