"""Workspace AI output type ``statement_claims`` (docs/cellebrite/04 section 9.2, unit U12)."""
from alembic import op

revision = "20261102_pol_claim_drafts"
down_revision = "20261102_pol_claims"
branch_labels = None
depends_on = None

OLD = "'statement_summary', 'statement_comparison', 'theory_analysis'"


def upgrade():
    op.drop_constraint("ck_workspace_ai_outputs_output_type", "workspace_ai_outputs", type_="check")
    op.create_check_constraint("ck_workspace_ai_outputs_output_type", "workspace_ai_outputs",
                               "output_type IN (%s, 'statement_claims')" % OLD)


def downgrade():
    import sqlalchemy as sa
    if op.get_bind().execute(sa.text("SELECT count(*) FROM workspace_ai_outputs WHERE output_type = "
                                     "'statement_claims'")).scalar_one():
        raise RuntimeError("Drafted claims are stored; removing the output type would orphan them.")
    op.drop_constraint("ck_workspace_ai_outputs_output_type", "workspace_ai_outputs", type_="check")
    op.create_check_constraint("ck_workspace_ai_outputs_output_type", "workspace_ai_outputs", "output_type IN (%s)" % OLD)
