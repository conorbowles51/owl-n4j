"""The case decision ledger records Replace and Retire of a phone report (01 section 10.7)."""
from alembic import op
import sqlalchemy as sa

revision = '20261101_phone_supersede_decision'
down_revision = '20261101_phone_job_states'
branch_labels = None
depends_on = None
SUBJECTS = "'transaction', 'statement_period', 'source_document', 'account', 'evidence_file'"
DECISIONS = "'supersede_duplicate', 'restore_document', 'purge_duplicate', 'quarantine_row', 'release_row', 'explain_balance_failure', 'reclassify_document', 'admit_financial_document', 'correct_transaction', 'set_account_party', 'set_counterparty_party', 'set_account_identity', 'keep_printed_holders'"


def _constraints(subjects, decisions):
    op.drop_constraint('ck_adjudications_subject_type', 'adjudications', type_='check')
    op.create_check_constraint('ck_adjudications_subject_type', 'adjudications', f"subject_type IN ({subjects})")
    op.drop_constraint('ck_adjudications_decision', 'adjudications', type_='check')
    op.create_check_constraint('ck_adjudications_decision', 'adjudications', f"decision IN ({decisions})")


def upgrade():
    _constraints(f"{SUBJECTS}, 'phone_extraction'", f"{DECISIONS}, 'supersede_phone_extraction'")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM adjudications WHERE subject_type='phone_extraction'")).scalar_one():
        raise RuntimeError('Cannot remove retained phone report decisions.')
    _constraints(SUBJECTS, DECISIONS)
