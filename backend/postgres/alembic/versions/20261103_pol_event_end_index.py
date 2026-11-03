"""Statement check at corpus scale (docs/cellebrite/04 section 11 and decision 37).

1. Activity events by end time. A check reads the events overlapping its window: those starting inside it come from
   the (extraction, instant) index; those starting earlier and still running need their end time indexed, or every
   earlier event of the phone is read (5.4 s for a 24-hour window on a 542,091-event phone; 42 ms with this index).
   Only events with an end time are indexed (50,173 of the 542,091).
2. A check item may be an ``event_group``: the context events of one phone, hour and reason, with their count.
3. Each phone's per-family event counts are kept on its projection state (``families``), written by the build; the
   phones already built get them here through the same function (``activity.families``). The aggregate read every
   event of every phone on each request about a person (4 to 6 s with one 542,091-event phone in the case).
4. An event's activity mapping version is read through the projection state: the state records the version of each
   activity mapping it applied (``activity_versions``, keyed by the mapping's ``<kind>/<name>/`` row prefix), and the
   view takes the version for the event's mapping row from it, falling back to the version stored on the event. A new
   mapping version then rewrites only the events whose class, actor or flags move: rewriting every event of a
   542,091-event phone takes 60 to 81 s on its own, over the 60 s target for re-applying a mapping.
"""
import importlib.util
import os

from alembic import op

revision = "20261103_pol_event_end_index"
down_revision = "20261103_phone_selections"
branch_labels = None
depends_on = None

OLD_KINDS = "'activity_event','place_observation','band','colocation','transaction','comm_event','window_piece'"


def _activity_migration():
    """The view's own migration, for its exact text and attribution groups."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "20261102_pol_activity.py")
    spec = importlib.util.spec_from_file_location("pol_activity_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _versioned_view(conn):
    import sqlalchemy as sa
    cols = [r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND "
        "table_name = 'pol_activity_event' ORDER BY ordinal_position"))]
    prefix = "split_part(ev.activity_mapping_row, '/', 1) || '/' || split_part(ev.activity_mapping_row, '/', 2) || '/'"
    inner = ", ".join("coalesce(CAST(ps.activity_versions ->> (%s) AS uuid), ev.activity_mapping_version) AS "
                      "activity_mapping_version" % prefix if c == "activity_mapping_version" else "ev.%s" % c
                      for c in cols)
    view = _activity_migration().VIEW
    old_select, old_from = "  SELECT ev.*,\n", "  FROM pol_activity_event ev\n) x;"
    assert view.count(old_select) == 1 and view.count(old_from) == 1
    return view.replace(old_select, "  SELECT %s,\n" % inner).replace(
        old_from, "  FROM pol_activity_event ev LEFT JOIN pol_projection_state ps ON ps.extraction_id = ev.extraction_id\n) x;")


def upgrade():
    op.execute("CREATE INDEX IF NOT EXISTS ix_pol_activity_event_ext_end ON pol_activity_event (extraction_id, end_utc) "
               "WHERE end_utc IS NOT NULL")
    op.execute("ALTER TABLE pol_claim_evaluation_item DROP CONSTRAINT IF EXISTS pol_claim_evaluation_item_ref_kind_check")
    op.execute("ALTER TABLE pol_claim_evaluation_item ADD CONSTRAINT pol_claim_evaluation_item_ref_kind_check CHECK "
               "(ref_kind IN (%s,'event_group'))" % OLD_KINDS)
    op.execute("ALTER TABLE pol_projection_state ADD COLUMN IF NOT EXISTS families jsonb")
    import json

    import sqlalchemy as sa

    from services.pattern_of_life import activity
    conn = op.get_bind()
    done = 0
    for (e,) in conn.execute(sa.text("SELECT extraction_id FROM pol_projection_state WHERE status = 'ready'")).fetchall():
        conn.execute(sa.text("UPDATE pol_projection_state SET families = CAST(:f AS jsonb) WHERE extraction_id = :e"),
                     {"e": e, "f": json.dumps(activity.families(conn, e))})
        done += 1
    print("pattern projections given their family counts: %d" % done)
    op.execute("ALTER TABLE pol_projection_state ADD COLUMN IF NOT EXISTS activity_versions jsonb")
    op.execute("DROP VIEW pol_activity_event_v")
    op.execute(_versioned_view(conn))


def downgrade():
    import sqlalchemy as sa
    n = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM pol_claim_evaluation_item WHERE ref_kind = 'event_group'")).scalar_one()
    if n:
        raise RuntimeError("%d statement-check items are groups of events; the earlier schema cannot hold them." % n)
    op.execute("ALTER TABLE pol_claim_evaluation_item DROP CONSTRAINT pol_claim_evaluation_item_ref_kind_check")
    op.execute("ALTER TABLE pol_claim_evaluation_item ADD CONSTRAINT pol_claim_evaluation_item_ref_kind_check CHECK "
               "(ref_kind IN (%s))" % OLD_KINDS)
    op.execute("DROP VIEW pol_activity_event_v")
    op.execute(_activity_migration().VIEW)
    op.execute("ALTER TABLE pol_projection_state DROP COLUMN IF EXISTS activity_versions")
    op.execute("ALTER TABLE pol_projection_state DROP COLUMN IF EXISTS families")
    op.execute("DROP INDEX IF EXISTS ix_pol_activity_event_ext_end")
