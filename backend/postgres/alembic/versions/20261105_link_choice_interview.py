"""An interview's evidence link can take a Keep or Remove choice (07 section 6.3): ``phone_link_choices.link_kind``
gains ``interview``. No rows change.
"""
from alembic import op

revision = "20261105_link_choice_interview"
down_revision = "20261105_phone_marks_collect_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE phone_link_choices DROP CONSTRAINT phone_link_choices_link_kind_check")
    op.execute("ALTER TABLE phone_link_choices ADD CONSTRAINT phone_link_choices_link_kind_check "
               "CHECK (link_kind IN ('entry', 'dossier', 'assessment', 'interview'))")


def downgrade():
    op.execute("DELETE FROM phone_link_choices WHERE link_kind = 'interview'")
    op.execute("ALTER TABLE phone_link_choices DROP CONSTRAINT phone_link_choices_link_kind_check")
    op.execute("ALTER TABLE phone_link_choices ADD CONSTRAINT phone_link_choices_link_kind_check "
               "CHECK (link_kind IN ('entry', 'dossier', 'assessment'))")
