"""Represent investigator-reviewed readings without inventing automation."""
from alembic import op
import sqlalchemy as sa

revision = "20260907_investigator_reading"
down_revision = "20260907_candidate_reviews"
branch_labels = None
depends_on = None

TABLES = ("financial_source_documents", "financial_transactions")


def _bounds(maximum):
    for table in TABLES:
        name = f"ck_{table}_extraction_layer"
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"extraction_layer BETWEEN 0 AND {maximum}")


def upgrade():
    _bounds(4)


def downgrade():
    # Do not relabel human readings as automated ones or discard provenance.
    for table in TABLES:
        if op.get_bind().execute(sa.text(
            f"SELECT EXISTS (SELECT 1 FROM {table} WHERE extraction_layer = 4)"
        )).scalar_one():
            raise RuntimeError("Cannot downgrade while investigator-reviewed readings exist.")
    _bounds(3)
