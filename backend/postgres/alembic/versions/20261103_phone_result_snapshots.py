"""A kept phone analysis result (05 section 3.4, J-14b; 02 decision 50).

An approach result is kept the way a pattern view is: frozen into ``pol_analysis_snapshot`` (kind, subject, window,
parameters, mapping versions, record ids, summary counts) and linked as ``phone_analysis``, resolved by the one
``phone_analysis`` resolver. The kind ``analysis_result`` is added to the table's closed list.
"""
from alembic import op

revision = "20261103_phone_result_snapshots"
down_revision = "20261103_assessment_agent_message"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE pol_analysis_snapshot DROP CONSTRAINT pol_analysis_snapshot_kind_check")
    op.execute("ALTER TABLE pol_analysis_snapshot ADD CONSTRAINT pol_analysis_snapshot_kind_check CHECK (kind IN "
               "('day', 'window', 'grid', 'places', 'analysis_result'))")


def downgrade():
    op.execute("DELETE FROM pol_analysis_snapshot WHERE kind = 'analysis_result'")
    op.execute("ALTER TABLE pol_analysis_snapshot DROP CONSTRAINT pol_analysis_snapshot_kind_check")
    op.execute("ALTER TABLE pol_analysis_snapshot ADD CONSTRAINT pol_analysis_snapshot_kind_check CHECK (kind IN "
               "('day', 'window', 'grid', 'places'))")
