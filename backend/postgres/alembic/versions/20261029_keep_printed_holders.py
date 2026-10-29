"""A decision that an account printed under different holder names keeps, per statement, the name printed on it."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_keep_printed_holders'
down_revision = '20261028_request_speed'
branch_labels = None
depends_on = None
OLD = "'supersede_duplicate', 'restore_document', 'purge_duplicate', 'quarantine_row', 'release_row', 'explain_balance_failure', 'reclassify_document', 'admit_financial_document', 'correct_transaction', 'set_account_party', 'set_counterparty_party', 'set_account_identity'"


def upgrade():
    op.drop_constraint('ck_adjudications_decision', 'adjudications', type_='check')
    op.create_check_constraint('ck_adjudications_decision', 'adjudications', f"decision IN ({OLD}, 'keep_printed_holders')")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM adjudications WHERE decision='keep_printed_holders'")).scalar_one():
        raise RuntimeError('Cannot remove retained printed-holder decisions.')
    op.drop_constraint('ck_adjudications_decision', 'adjudications', type_='check')
    op.create_check_constraint('ck_adjudications_decision', 'adjudications', f"decision IN ({OLD})")
