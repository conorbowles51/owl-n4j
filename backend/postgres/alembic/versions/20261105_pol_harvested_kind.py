"""A place observation can be ``harvested``: a network or tower the phone heard, never presence (04 decision 53)."""
from alembic import op

revision = "20261105_pol_harvested_kind"
down_revision = "20261105_link_choice_interview"
branch_labels = None
depends_on = None

KINDS = ("presence", "searched", "planned", "declared", "media", "transaction")


def _check(kinds):
    op.drop_constraint("pol_place_observation_kind_check", "pol_place_observation", type_="check")
    op.create_check_constraint("pol_place_observation_kind_check", "pol_place_observation",
                               "kind IN (%s)" % ", ".join("'%s'" % k for k in kinds))


def upgrade():
    _check(KINDS + ("harvested",))


def downgrade():
    op.execute("DELETE FROM pol_place_observation WHERE kind = 'harvested'")
    _check(KINDS)
