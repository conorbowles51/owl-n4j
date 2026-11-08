"""A page view's own start: first paint and the first data request, on the existing speed row.

Three nullable columns on request_speed_pages, so a real person's opening separates app start
(first paint, when the page first asked for data, and which route that was) from the data time
already recorded. No new table: the row holds it.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261108_page_start_marks"
down_revision = "20261105_two_step"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('request_speed_pages', sa.Column('first_paint_ms', sa.Float(), nullable=True))
    op.add_column('request_speed_pages', sa.Column('first_api_ms', sa.Float(), nullable=True))
    op.add_column('request_speed_pages', sa.Column('first_api_route', sa.String(160), nullable=True))


def downgrade():
    op.drop_column('request_speed_pages', 'first_api_route')
    op.drop_column('request_speed_pages', 'first_api_ms')
    op.drop_column('request_speed_pages', 'first_paint_ms')
