"""Join the financial ledger and Workspace development migration histories.

Both parent histories must run before the combined preview starts. This merge
revision adds no schema or data changes of its own.
"""
revision = "20260909_preview_merge"
down_revision = ("20260907_candidate_finalizations", "20260902_workspace_ai")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
