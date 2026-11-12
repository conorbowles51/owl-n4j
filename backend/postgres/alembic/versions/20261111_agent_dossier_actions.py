"""Allow reviewed dossier changes, without altering existing proposals."""
from alembic import op
import sqlalchemy as sa

revision = '20261111_agent_dossier_actions'
down_revision = '20261110_deadline_completion'
branch_labels = None
depends_on = None

BASE = ("'statement_summary', 'statement_comparison', 'theory_analysis', 'statement_claims', 'entry_draft', "
        "'lead_card', 'timeline_addition', 'link_proposal', 'alternative_explanation', 'control_claim', "
        "'payment_purpose', 'statement_claim', 'entity_proposal', 'glossary_term', 'counter_argument', 'disconfirm_sweep'")
NAME = 'ck_workspace_ai_outputs_output_type'


def upgrade():
    op.drop_constraint(NAME, 'workspace_ai_outputs', type_='check')
    op.create_check_constraint(NAME, 'workspace_ai_outputs', f"output_type IN ({BASE}, 'dossier_change')")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM workspace_ai_outputs WHERE output_type = 'dossier_change'")):
        raise RuntimeError('Dossier proposals exist. Preserve their history before downgrading.')
    op.drop_constraint(NAME, 'workspace_ai_outputs', type_='check')
    op.create_check_constraint(NAME, 'workspace_ai_outputs', f'output_type IN ({BASE})')
