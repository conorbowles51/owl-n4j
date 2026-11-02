"""Fill the copy groups of every active phone's current reading (03 section 3.4, rule v1 with D-34 and D-37).

New readings get their groups in ``comms.build``; this applies the same function, ``services.phone.copies.assign``,
to the readings already stored. Measured on the live box 2 November (read-only dry run): 57 groups of 115 records
on the real cases, so 58 rows collapse into "Found N times"; 0 on the synthetic phones-only case. Downgrade clears
the groups, as before this release.
"""
from alembic import op
from sqlalchemy import text

revision = "20261103_phone_copies_backfill"
down_revision = "20261103_phone_summary_root_idx"
branch_labels = None
depends_on = None


def upgrade():
    from services.phone import copies
    conn = op.get_bind()
    rows = conn.execute(text(
        "SELECT st.extraction_id, st.generation FROM phone_interpretation_state st JOIN phone_extractions e ON "
        "e.id = st.extraction_id WHERE e.standing = 'active' AND st.generation IS NOT NULL")).fetchall()
    groups = records = 0
    for ext, gen in rows:
        got = copies.assign(conn, ext, gen)
        groups, records = groups + got["groups"], records + got["records"]
    print("phone copy groups: %d phones, %d groups, %d records" % (len(rows), groups, records))


def downgrade():
    op.execute("UPDATE phone_comm_events SET dup_group_uid = NULL, dup_rule_version = NULL")
