"""Address lookup mode per case (Neil 2026-11-04).

``cases.address_lookup_mode``: 'auto' (addresses found in evidence are sent to the outside address service on their
own, one a second, by services.address_lookup) or 'flag' (they wait in the map's Needs review panel until a person
clicks Look up). Empty means the system default (ADDRESS_LOOKUP_DEFAULT, 'auto' unless set).
"""
from alembic import op

revision = "20261104_address_lookup_mode"
down_revision = "20261104_removed_records"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS address_lookup_mode VARCHAR(8)")
    op.execute(
        "ALTER TABLE cases ADD CONSTRAINT ck_cases_address_lookup_mode "
        "CHECK (address_lookup_mode IS NULL OR address_lookup_mode IN ('auto', 'flag'))"
    )


def downgrade():
    op.execute("ALTER TABLE cases DROP CONSTRAINT IF EXISTS ck_cases_address_lookup_mode")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS address_lookup_mode")
