"""Engine job states for phone capture (01 section 10.3, unit 2.1): verifying_source, capturing, reconciling.

Without them the job card would show a phone reading as "Extracting Text" or a raw status string (decision D19).
PostgreSQL cannot drop an enum value, so downgrade leaves them; no row uses them until a phone job runs.
"""
from alembic import op

revision = "20261101_phone_job_states"
down_revision = "20261101_phone_capture"
branch_labels = None
depends_on = None


def upgrade():
    for value in ("verifying_source", "capturing", "reconciling"):
        op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS '%s'" % value)


def downgrade():
    pass
