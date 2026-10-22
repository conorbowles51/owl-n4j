"""Allow findings to remain unrated without changing existing assessments."""
from alembic import op
import sqlalchemy as sa
revision = "20261019_workspace_setup"
down_revision = "20261019_dossier_workflows"
branch_labels = None
depends_on = None
CONSTRAINT = "ck_workspace_entries_type_specific_fields"
RULE = """(entry_type = 'note' AND lifecycle_state IS NULL AND significance IS NULL AND confidence IS NULL) OR
(entry_type = 'finding' AND lifecycle_state IN ('draft', 'active', 'superseded', 'withdrawn') AND confidence IS NULL) OR
(entry_type = 'theory' AND lifecycle_state IN ('proposed', 'investigating', 'substantiated', 'weakened', 'rejected', 'converted') AND significance IS NULL)"""
def upgrade():
    op.drop_constraint(CONSTRAINT, "workspace_entries", type_="check")
    op.create_check_constraint(CONSTRAINT, "workspace_entries", RULE)
def downgrade():
    connection = op.get_bind()
    count = connection.scalar(sa.text("SELECT count(*) FROM workspace_entries WHERE entry_type = 'finding' AND significance IS NULL AND needs_migration_review = false"))
    if count:
        raise RuntimeError("Unrated findings exist. Review them before restoring the old required-rating constraint.")
    op.drop_constraint(CONSTRAINT, "workspace_entries", type_="check")
    op.create_check_constraint(CONSTRAINT, "workspace_entries", RULE.replace("AND confidence IS NULL) OR\n(entry_type = 'theory'", "AND confidence IS NULL AND (significance IS NOT NULL OR needs_migration_review = true)) OR\n(entry_type = 'theory'"))
