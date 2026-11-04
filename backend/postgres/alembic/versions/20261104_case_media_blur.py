"""The case default for blurring phone media thumbnails (03 8.3, 07 4.11 and section 6 Case settings).

``case_phone_settings``: per case, ``media_blur_default`` true or false when a person has set it; no row (or NULL)
means the default follows the case: on in a criminal case (the case context template ``criminal_defense``), off
otherwise (07 UXD-26). Each person can still turn blur off for themselves.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261104_case_media_blur"
down_revision = "20261104_pol_place_names"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "case_phone_settings",
        sa.Column("case_id", uuid, sa.ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("media_blur_default", sa.Boolean(), nullable=True),
        sa.Column("updated_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("case_phone_settings")
