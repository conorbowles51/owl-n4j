"""Reviewed account identifiers and referenced accounts in the existing audit chain."""
from alembic import op
import sqlalchemy as sa

revision = '20260923_account_identity'
down_revision = '20260923_upload_groups'
branch_labels = None
depends_on = None
OLD = "'supersede_duplicate', 'restore_document', 'purge_duplicate', 'quarantine_row', 'release_row', 'explain_balance_failure', 'reclassify_document', 'admit_financial_document', 'correct_transaction', 'set_account_party', 'set_counterparty_party'"


def upgrade():
    op.drop_constraint('ck_adjudications_decision', 'adjudications', type_='check')
    op.create_check_constraint('ck_adjudications_decision', 'adjudications', f"decision IN ({OLD}, 'set_account_identity')")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM adjudications WHERE decision='set_account_identity'")).scalar_one():
        raise RuntimeError('Cannot remove retained account identity decisions.')
    op.drop_constraint('ck_adjudications_decision', 'adjudications', type_='check')
    op.create_check_constraint('ck_adjudications_decision', 'adjudications', f"decision IN ({OLD})")
