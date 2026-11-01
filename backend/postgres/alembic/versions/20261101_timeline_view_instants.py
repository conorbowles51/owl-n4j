"""Saved-view events gain sort_instant and sort_zone, backfilled from sort_date and sort_time (07 6.4 item 8).

The old columns stay and saved views keep ordering by sort_date, sort_time and position, so every existing view
renders exactly as before (07 CO-21). Backfill: a valid written date and time becomes the instant with zone
"wall_clock" (no zone was recorded); a date-only event (time "99:99") gets zone "wall_clock" and no instant, since
inventing a time would claim precision the event does not have. The upgrade counts rows and checks every view's
order before and after, and refuses to finish if either moved.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261101_timeline_view_instants'
down_revision = '20261101_interview_evidence_targets'
branch_labels = None
depends_on = None

ORDER = "SELECT view_id, event_key FROM timeline_view_events ORDER BY view_id, sort_date, sort_time, position"
BACKFILL = """
UPDATE timeline_view_events SET
  sort_zone = CASE WHEN sort_date IS NULL THEN NULL ELSE 'wall_clock' END,
  sort_instant = CASE
    WHEN sort_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND sort_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
    THEN (sort_date || ' ' || sort_time)::timestamp AT TIME ZONE 'UTC'
    ELSE NULL END
"""


def upgrade():
    bind = op.get_bind()
    before = bind.execute(sa.text(ORDER)).all()
    op.add_column('timeline_view_events', sa.Column('sort_instant', sa.DateTime(timezone=True), nullable=True))
    op.add_column('timeline_view_events', sa.Column('sort_zone', sa.String(64), nullable=True))
    bind.execute(sa.text(BACKFILL))
    after = bind.execute(sa.text(ORDER)).all()
    counts = bind.execute(sa.text(
        "SELECT count(*), count(sort_instant), count(*) FILTER (WHERE sort_zone = 'wall_clock') FROM timeline_view_events"
    )).one()
    print(f"timeline_view_events rows: before {len(before)}, after {counts[0]}; with an instant {counts[1]}; "
          f"wall_clock {counts[2]}")
    if counts[0] != len(before) or after != before:
        raise RuntimeError("timeline_view_events changed: row count or a saved view's order moved")


def downgrade():
    op.drop_column('timeline_view_events', 'sort_zone')
    op.drop_column('timeline_view_events', 'sort_instant')
