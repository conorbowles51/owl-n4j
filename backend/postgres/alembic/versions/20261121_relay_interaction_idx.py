"""A covering index for the contacts a phone had with a known counterpart (who overlaps with whom, relay chains).

The relay read and its count select interactions with a counterpart and a time for the chosen phones. Through
``ix_pol_activity_event_interaction`` they fetched every matching row from the 1.5 GB table: on Phone reference 1, two
phones touched 22.7k pages and took 14.7 s when the pages were not cached (18 Nov, load 20). This partial index holds
the 125k such rows with the columns those reads use, so they are answered from the index.
"""
from alembic import op

revision = "20261121_relay_interaction_idx"
down_revision = "20261120_leads"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE INDEX IF NOT EXISTS ix_pol_activity_event_relay ON pol_activity_event "
               "(extraction_id, instant_utc) INCLUDE (counterpart_identity_id, record_uid, case_id) "
               "WHERE activity_class = 'interaction' AND counterpart_identity_id IS NOT NULL AND instant_utc IS NOT NULL")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_pol_activity_event_relay")
