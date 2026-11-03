"""A statement check can end ``no_record`` (agent-phones; report "Statement check with the money lane").

``pol_claim_evaluation.outcome`` gains ``no_record``: the phone holds no record of the kind the statement needs for
its time, with the reason in ``outcome_basis`` and ``summary.no_record_reason``. Existing checks are unchanged; the
constraint only widens.
"""
from alembic import op

revision = "20261103_pol_check_no_record"
down_revision = "20261103_assessment_agent_message"
branch_labels = None
depends_on = None

OLD = "('contradicted','contradicted_weakly','consistent','supported','mixed','insufficient_data')"
NEW = "('contradicted','contradicted_weakly','consistent','supported','mixed','insufficient_data','no_record')"


def _set(values):
    op.execute("ALTER TABLE pol_claim_evaluation DROP CONSTRAINT IF EXISTS pol_claim_evaluation_outcome_check")
    op.execute("ALTER TABLE pol_claim_evaluation ADD CONSTRAINT pol_claim_evaluation_outcome_check CHECK (outcome IN %s)"
               % values)


def upgrade():
    _set(NEW)


def downgrade():
    _set(OLD)
