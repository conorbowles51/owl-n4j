"""``pv_identity`` holds the identities a current reading saw, or that a person linked.

``phone_identities`` keeps every key any reading produced, and ``sighting_count`` drops to 0 when no current reading
holds it (a region decision that was changed or undone, a phone deleted or superseded). The row stays, so its id and
the older generations' sightings stay valid; the view stops offering it to search, the agent and the analyses. An
identity linked to a person stays in the view with its count of 0, because the person's page names it.

No table changes. The view keeps its columns, so nothing that reads it needs rebuilding.
"""
from alembic import op

revision = "20261105_pv_identity_seen"
down_revision = "20261104_phone_original_bundles"
branch_labels = None
depends_on = None

BODY = """CREATE OR REPLACE VIEW pv_identity AS
SELECT i.id AS identity_id, i.identity_key, i.case_id, i.kind, i.subkind, i.value_normalised, i.value_display,
       i.sighting_count, i.phone_count, i.first_instant, i.last_instant, l.dossier_id AS person_id
  FROM phone_identities i LEFT JOIN phone_identity_links l ON l.identity_id = i.id"""


def upgrade():
    op.execute(BODY + "\n WHERE i.sighting_count > 0 OR l.identity_id IS NOT NULL;")


def downgrade():
    op.execute(BODY + ";")
