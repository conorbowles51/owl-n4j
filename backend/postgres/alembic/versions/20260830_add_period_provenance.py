"""record where each statement period bound and balance came from

Revision ID: 20260830_period_provenance
Revises: 20260830_financial_ledger
Create Date: 2026-08-30

The ledger migration gave statement periods their dates and balances.  This
one gives four of those values a source, and closes two holes in the table it
inherits.

*Period bounds get a source, separately for start and end.*  A period end
printed on the statement and one derived from the last transaction on the page
support entirely different arguments.  Only the printed one can establish that
a neighbouring statement is missing; a derived bound shrinks to fit the rows
that happened to be extracted, so it manufactures a gap after a quiet fortnight
and conceals one when the final rows were dropped.  Start and end are separate
columns because statements exist that print only a closing date.

*A carried-forward balance names where it was carried from.*  Otherwise
'carried_forward' is an unfalsifiable claim, and a reader cannot see that the
balance identity for this period is partly a restatement of the period next
door rather than an independent check of these rows.

*A value and its source must agree that the value exists.*  The inherited
table permits a row saying a balance is absent while carrying one, and a row
saying a balance was printed while carrying none.  Either makes the source
column evidence of nothing.  The check compares two booleans rather than
testing truthiness, so a zero balance is admitted as the real balance it is.

*One document covers one account once.*  The inherited unique constraint spans
(source_document_id, account_id, period_start, period_end), and both Postgres
and SQLite treat nulls in a unique constraint as distinct.  A statement whose
dates could not be read therefore admits unlimited duplicate periods — on
exactly the document that is hardest to check by eye.  A partial unique index
covers the undated case.

This migration refuses to run against a populated table rather than guessing.
Backfilling a source column would mean asserting that existing dates were
printed and existing balances observed, which is the assertion these columns
exist to stop anyone making without evidence.  The table is empty by
construction: the revision that created it is the one immediately below, and
the financial feature is not in service.  If it is not empty, the right
outcome is a stop with a legible reason.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260830_period_provenance"
down_revision: Union[str, None] = "20260830_financial_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "financial_statement_periods"
PERIOD_BOUNDS_SOURCES = "('printed', 'derived', 'absent')"
UNDATED = "period_start IS NULL AND period_end IS NULL"


def _require_empty() -> None:
    """Stop with an explanation rather than backfilling a guess."""
    bind = op.get_bind()
    existing = bind.execute(
        sa.text(f"SELECT count(*) FROM {TABLE}")  # noqa: S608 - fixed identifier
    ).scalar_one()
    if existing:
        raise RuntimeError(
            f"{TABLE} holds {existing} row(s).  This migration adds source "
            "columns for the period bounds and balances, and there is no "
            "honest value to backfill them with: recording an existing date "
            "as 'printed' would assert something nobody checked.  Reconcile "
            "or clear these rows, then run the migration again."
        )


def upgrade() -> None:
    _require_empty()

    op.add_column(
        TABLE,
        sa.Column(
            "period_start_source",
            sa.String(length=16),
            nullable=False,
            server_default="absent",
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "period_end_source",
            sa.String(length=16),
            nullable=False,
            server_default="absent",
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "opening_carried_from_period_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "closing_carried_from_period_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # SET NULL rather than CASCADE or RESTRICT.  Deleting the period a balance
    # was carried from must not delete this period, and must not block the
    # case deletion that every other link here cascades from.  The cost is
    # that a surviving row can say 'carried_forward' while pointing nowhere,
    # which is why no check constraint ties the two together; the rule is
    # enforced in services.financial.periods, where it can be maintained.
    op.create_foreign_key(
        "fk_financial_statement_periods_opening_carried_from",
        TABLE,
        TABLE,
        ["opening_carried_from_period_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_financial_statement_periods_closing_carried_from",
        TABLE,
        TABLE,
        ["closing_carried_from_period_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_check_constraint(
        "ck_financial_statement_periods_start_source",
        TABLE,
        f"period_start_source IN {PERIOD_BOUNDS_SOURCES}",
    )
    op.create_check_constraint(
        "ck_financial_statement_periods_end_source",
        TABLE,
        f"period_end_source IN {PERIOD_BOUNDS_SOURCES}",
    )

    op.create_check_constraint(
        "ck_financial_statement_periods_start_coherent",
        TABLE,
        "(period_start_source = 'absent') = (period_start IS NULL)",
    )
    op.create_check_constraint(
        "ck_financial_statement_periods_end_coherent",
        TABLE,
        "(period_end_source = 'absent') = (period_end IS NULL)",
    )
    op.create_check_constraint(
        "ck_financial_statement_periods_opening_coherent",
        TABLE,
        "(opening_balance_source = 'absent') = (opening_balance_minor IS NULL)",
    )
    op.create_check_constraint(
        "ck_financial_statement_periods_closing_coherent",
        TABLE,
        "(closing_balance_source = 'absent') = (closing_balance_minor IS NULL)",
    )

    op.create_index(
        "uq_financial_statement_periods_document_account_undated",
        TABLE,
        ["source_document_id", "account_id"],
        unique=True,
        postgresql_where=sa.text(UNDATED),
        sqlite_where=sa.text(UNDATED),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_financial_statement_periods_document_account_undated", table_name=TABLE
    )

    for name in (
        "ck_financial_statement_periods_closing_coherent",
        "ck_financial_statement_periods_opening_coherent",
        "ck_financial_statement_periods_end_coherent",
        "ck_financial_statement_periods_start_coherent",
        "ck_financial_statement_periods_end_source",
        "ck_financial_statement_periods_start_source",
    ):
        op.drop_constraint(name, TABLE, type_="check")

    op.drop_constraint(
        "fk_financial_statement_periods_closing_carried_from",
        TABLE,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_financial_statement_periods_opening_carried_from",
        TABLE,
        type_="foreignkey",
    )

    op.drop_column(TABLE, "closing_carried_from_period_id")
    op.drop_column(TABLE, "opening_carried_from_period_id")
    op.drop_column(TABLE, "period_end_source")
    op.drop_column(TABLE, "period_start_source")
