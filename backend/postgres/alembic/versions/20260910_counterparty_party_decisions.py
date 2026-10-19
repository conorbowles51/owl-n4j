"""Retain explicit payment counterparty identity links."""
from alembic import op
import sqlalchemy as sa
revision='20260910_counterparty_parties'
down_revision='20260910_account_parties'
branch_labels=None
depends_on=None
OLD="'supersede_duplicate', 'restore_document', 'purge_duplicate', 'quarantine_row', 'release_row', 'explain_balance_failure', 'reclassify_document', 'admit_financial_document', 'correct_transaction', 'set_account_party'"
def upgrade():
    op.drop_constraint('ck_adjudications_decision','adjudications',type_='check')
    op.create_check_constraint('ck_adjudications_decision','adjudications',f"decision IN ({OLD}, 'set_counterparty_party')")
def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM adjudications WHERE decision='set_counterparty_party'")).scalar_one():
        raise RuntimeError('Cannot downgrade while counterparty identity history exists.')
    op.drop_constraint('ck_adjudications_decision','adjudications',type_='check')
    op.create_check_constraint('ck_adjudications_decision','adjudications',f"decision IN ({OLD})")
