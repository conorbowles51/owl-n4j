"""The disconfirm sweep (agent-disconfirm A, B): two more Workspace AI kinds.

* ``disconfirm_sweep``: one sweep of a theory across the whole case: its expectations, what was searched, what is
  absent, the state of each model read. A run record, never a proposal.
* ``counter_argument``: one contradicting finding, pending a person. Accepting links its sources to the theory as
  ``contradicts``.

Existing rows are unchanged: the check only widens.
"""
from alembic import op

revision = "20261105_agent_disconfirm"
down_revision = "20261105_link_choice_interview"
branch_labels = None
depends_on = None

BASE = ("'statement_summary', 'statement_comparison', 'theory_analysis', 'statement_claims', 'entry_draft', "
        "'lead_card', 'timeline_addition', 'link_proposal', 'alternative_explanation', 'control_claim', "
        "'payment_purpose', 'statement_claim', 'entity_proposal', 'glossary_term'")
ADDED = "'counter_argument', 'disconfirm_sweep'"
NAME = "ck_workspace_ai_outputs_output_type"


def upgrade():
    op.drop_constraint(NAME, "workspace_ai_outputs", type_="check")
    op.create_check_constraint(NAME, "workspace_ai_outputs", "output_type IN (%s, %s)" % (BASE, ADDED))


def downgrade():
    op.drop_constraint(NAME, "workspace_ai_outputs", type_="check")
    op.execute("DELETE FROM workspace_ai_outputs WHERE output_type IN (%s)" % ADDED)
    op.create_check_constraint(NAME, "workspace_ai_outputs", "output_type IN (%s)" % BASE)
