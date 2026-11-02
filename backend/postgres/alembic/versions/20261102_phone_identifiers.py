"""Phone identifiers (docs/cellebrite/02 sections 8.2 and 8.3).

- ``cases.phone_default_region``: ISO 3166-1 alpha-2 region for numbers written without ``+`` (8.3 step 2).
- ``phone_participations.region_basis``: how the region of a number without ``+`` was chosen (``decided``,
  ``case_setting``, ``assumed_default``; ``explicit_plus`` when written with ``+``), and
  ``identity_kind``, ``identity_subkind`` from ``identifiers.classify``.
"""
from alembic import op

revision = "20261102_phone_identifiers"
down_revision = "20261102_phone_meaning"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE cases ADD COLUMN phone_default_region varchar(2) "
               "CHECK (phone_default_region IS NULL OR phone_default_region ~ '^[A-Z]{2}$')")
    op.execute("ALTER TABLE phone_participations ADD COLUMN region_basis varchar(24), "
               "ADD COLUMN identity_kind varchar(16), ADD COLUMN identity_subkind varchar(32)")


def downgrade():
    op.execute("ALTER TABLE phone_participations DROP COLUMN identity_subkind, DROP COLUMN identity_kind, "
               "DROP COLUMN region_basis")
    op.execute("ALTER TABLE cases DROP COLUMN phone_default_region")
