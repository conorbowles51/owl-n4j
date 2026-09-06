"""Allow an audited append-only transaction correction."""
from alembic import op
import sqlalchemy as sa

revision = "20260906_correction_decision"
down_revision = "20260902_evidence_table_geometry"
branch_labels = None
depends_on = None

OLD = "'supersede_duplicate', 'restore_document', 'purge_duplicate', 'quarantine_row', 'release_row', 'explain_balance_failure', 'reclassify_document', 'admit_financial_document'"


def upgrade():
    op.drop_constraint("ck_adjudications_decision", "adjudications", type_="check")
    op.create_check_constraint("ck_adjudications_decision", "adjudications", f"decision IN ({OLD}, 'correct_transaction')")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM adjudications WHERE decision = 'correct_transaction'")).scalar_one():
        raise RuntimeError("Cannot downgrade while transaction correction audit events exist.")
    op.drop_constraint("ck_adjudications_decision", "adjudications", type_="check")
    op.create_check_constraint("ck_adjudications_decision", "adjudications", f"decision IN ({OLD})")
