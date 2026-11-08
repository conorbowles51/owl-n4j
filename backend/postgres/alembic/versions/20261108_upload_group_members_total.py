"""Paged upload manifests: the declared size of a selection registered in pages (01 D41).

D9's reversal condition is met: real productions measured 8 Nov hold 209,271 (P03), 204,426 (P08),
206,622 (P13) and 279,701 (P11) files, over the one-request manifest cap of 200,000. A selection
larger than one page declares its total at creation and sends the rest of its manifest in pages;
``members_total`` is NULL for a selection created whole, so existing rows mean what they always did.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261108_upload_group_members_total"
down_revision = "20261105_two_step"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence_upload_groups", sa.Column("members_total", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence_upload_groups", "members_total")
