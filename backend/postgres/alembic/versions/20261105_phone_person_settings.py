"""One person's own blur choice for phone pictures in one case (03 section 8.3, 07 section 4.11).

Blur is a per-person setting: the choice follows the person to any browser, and it outranks the case default in
``case_phone_settings``. New table; no existing row changes.
"""
from alembic import op

revision = "20261105_phone_person_settings"
down_revision = "20261104_case_media_blur"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE phone_person_settings (
          case_id    uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          media_blur boolean,
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (case_id, user_id)
        );
    """)


def downgrade():
    op.execute("DROP TABLE phone_person_settings")
