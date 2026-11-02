"""The phone timeline entry carries its activity class from the pattern-of-life projection (03 section 4, 04 3.1).

``pv_timeline_entry.activity_class`` was the constant ``'unknown'`` until 04-U2 existed; it now reads the class of the
time value's activity event (an interval's end takes its start's event), and stays ``'unknown'`` for a time value with
no activity event (3.3's scheduled and expiry times, or a phone whose projection is not built yet). Same columns, same
order. Downgrade restores the constant.
"""
import os
from importlib.util import module_from_spec, spec_from_file_location

from alembic import op

revision = "20261102_pol_timeline_class"
down_revision = "20261102_pol_availability"
branch_labels = None
depends_on = None

CLASS = """COALESCE((SELECT a.activity_class FROM pol_activity_event a WHERE a.extraction_id = t.extraction_id
                  AND a.record_uid = t.record_uid AND (a.time_field = t.field_name OR a.end_field = t.field_name)
                  ORDER BY (a.time_field = t.field_name) DESC LIMIT 1), 'unknown')::text AS activity_class"""


def _sql(cls):
    path = os.path.join(os.path.dirname(__file__), "20261102_phone_meaning.py")
    spec = spec_from_file_location("phone_meaning_migration", path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    sql = mod.TIMELINE % {"current": mod.CURRENT, "extra": mod.EXTRA}
    assert "'unknown'::text AS activity_class" in sql
    return sql.replace("CREATE VIEW", "CREATE OR REPLACE VIEW").replace("'unknown'::text AS activity_class", cls)


def upgrade():
    op.execute(_sql(CLASS))


def downgrade():
    op.execute(_sql("'unknown'::text AS activity_class"))
