"""Retain investigator account-party assignment and removal decisions."""
from alembic import op
import sqlalchemy as sa

revision = '20260910_account_parties'
down_revision = '20260910_statement_editor'
branch_labels = None
depends_on = None
OLD = "'supersede_duplicate', 'restore_document', 'purge_duplicate', 'quarantine_row', 'release_row', 'explain_balance_failure', 'reclassify_document', 'admit_financial_document', 'correct_transaction'"


def upgrade():
    op.drop_constraint('ck_adjudications_decision', 'adjudications', type_='check')
    op.create_check_constraint('ck_adjudications_decision', 'adjudications', f"decision IN ({OLD}, 'set_account_party')")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM adjudications WHERE decision = 'set_account_party'")).scalar_one():
        raise RuntimeError('Cannot downgrade while account party decisions exist.')
    op.drop_constraint('ck_adjudications_decision', 'adjudications', type_='check')
    op.create_check_constraint('ck_adjudications_decision', 'adjudications', f'decision IN ({OLD})')
