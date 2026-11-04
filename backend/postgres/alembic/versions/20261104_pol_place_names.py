"""Named places of the Patterns screen (04 sections 7.7 and 8.3, cb-places-rest item D).

- ``pol_place_cluster``: a place a person has named. Clusters are computed on read (DBSCAN over stays), so a name is
  kept with the place's centre and radius when it was named; a recomputed place takes the name of the nearest named
  place of the case whose centre is within the clustering distance (150 m) of its own. The row is the place's stable
  identity across recomputes; ``label_decision_id`` is the case decision that set the current name.
- The case decision ledger gains the subject ``place_cluster`` and the decision ``label_place`` (its reversal is
  another ``label_place``, to a new name or to none).

The constraint lists are read from the database and extended, so values another migration added are kept.
"""
import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261104_pol_place_names"
down_revision = "20261104_upload_registrations"
branch_labels = None
depends_on = None

NEW = {"ck_adjudications_subject_type": ("subject_type", ["place_cluster"]),
       "ck_adjudications_decision": ("decision", ["label_place"])}


def _values(conn, name):
    d = conn.execute(sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n AND "
                             "conrelid = 'adjudications'::regclass"), {"n": name}).scalar()
    return re.findall(r"'([^']+)'::", d or "")


def _replace(conn, name, column, values):
    quoted = ", ".join("'%s'" % v for v in values)
    op.execute("ALTER TABLE adjudications DROP CONSTRAINT IF EXISTS %s" % name)
    op.execute("ALTER TABLE adjudications ADD CONSTRAINT %s CHECK (%s IN (%s))" % (name, column, quoted))


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "pol_place_cluster",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("case_id", uuid, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_key", sa.String(80), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("radius_m", sa.Float(), nullable=False),
        sa.Column("stay_count", sa.Integer(), nullable=False),
        sa.Column("day_count", sa.Integer(), nullable=False),
        sa.Column("profile", postgresql.JSONB(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("label_decision_id", uuid, nullable=True),
        sa.Column("label_by_name", sa.Text(), nullable=True),
        sa.Column("computed_with", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("label IS NULL OR length(btrim(label)) BETWEEN 1 AND 200", name="ck_pol_place_cluster_label"),
    )
    op.create_index("ix_pol_place_cluster_case", "pol_place_cluster", ["case_id"])
    conn = op.get_bind()
    for name, (column, add) in NEW.items():
        have = _values(conn, name)
        if not have:
            raise RuntimeError("constraint %s not found on adjudications" % name)
        _replace(conn, name, column, have + [v for v in add if v not in have])


def downgrade():
    conn = op.get_bind()
    for name, (column, add) in NEW.items():
        _replace(conn, name, column, [v for v in _values(conn, name) if v not in add])
    op.drop_table("pol_place_cluster")
