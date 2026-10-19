"""close the quarantine reason vocabulary and tie it to the status

Revision ID: 20260830_quarantine_reasons
Revises: 20260830_document_duplicates
Create Date: 2026-08-30

The ledger migration gave documents and transactions a ``quarantine_reason``
column and left it as free text that nothing wrote.  This one closes the
vocabulary and requires the reason and the status to agree.

*The vocabulary is closed because the question it answers is asked under
oath.*  "How many rows did you exclude, and on what basis" is a question
opposing counsel is entitled to put, and a free-text column cannot answer it:
'balance break', 'balance_break', 'bal. break' and 'broke the chain' are four
answers to a question that has one.  Five values are admitted, and adding a
sixth is a migration, which is the point — the set of grounds on which
evidence may be set aside should not be extensible by whoever is typing.

*The reason and the status are held to agree because either half alone is
worthless.*  A row marked quarantined with no reason has been removed from
every total on grounds nobody recorded, which is precisely the failure the
vocabulary exists to prevent.  A row carrying a reason while admitted
describes a decision that was reversed, and a reader cannot tell that from a
decision that was taken.  The constraint is written as an equality between two
booleans rather than as a pair of implications so that neither direction can
be relaxed later without the other becoming visible.

Note what is *not* constrained.  ``superseded`` and ``rejected`` rows carry no
quarantine reason, because they were not quarantined; if those dispositions
come to need their own recorded grounds they need their own column, not a
borrowed one.  A statement that printed no control total is likewise not
quarantined at all — its reconciliation status is ``unavailable``, which is a
fact about the document rather than a fault in it.

This migration does not require an empty table.  Adding these columns' rules
is not a backfill: no row is being asked to assert anything new, only to be
consistent about what it already claims.  But a violating row would make the
upgrade fail with a message naming a constraint and nothing else, so the two
checks below run first and report what is actually wrong.  Nothing writes
``quarantine_reason`` at the time of writing, so any violation would be a row
quarantined without grounds — which is worth stopping for and worth naming.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260830_quarantine_reasons"
down_revision: Union[str, None] = "20260830_document_duplicates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REASONS = (
    "('balance_break', 'unreadable_row', 'currency_mismatch', "
    "'unexplained_delta', 'adjudicated')"
)

# (table, status column, constraint name stem)
TARGETS = (
    ("financial_source_documents", "status"),
    ("financial_transactions", "ledger_status"),
)


def _coherence(status_column: str) -> str:
    return f"(quarantine_reason IS NOT NULL) = ({status_column} = 'quarantined')"


def _refuse_incoherent_rows() -> None:
    """Name the rows that would break, instead of letting Postgres name a constraint."""
    bind = op.get_bind()
    complaints = []
    for table, status_column in TARGETS:
        unknown = bind.execute(
            sa.text(  # noqa: S608 - identifiers are fixed literals above
                f"SELECT count(*) FROM {table} WHERE quarantine_reason IS NOT NULL "
                f"AND quarantine_reason NOT IN {REASONS}"
            )
        ).scalar_one()
        if unknown:
            complaints.append(
                f"{table}: {unknown} row(s) carry a quarantine_reason outside "
                f"the closed vocabulary {REASONS}"
            )
        incoherent = bind.execute(
            sa.text(  # noqa: S608 - identifiers are fixed literals above
                f"SELECT count(*) FROM {table} "
                f"WHERE NOT ({_coherence(status_column)})"
            )
        ).scalar_one()
        if incoherent:
            complaints.append(
                f"{table}: {incoherent} row(s) have a quarantine_reason that "
                f"disagrees with {status_column} — either set aside with no "
                "recorded grounds, or carrying grounds while still counted"
            )
    if complaints:
        raise RuntimeError(
            "quarantine reasons cannot be constrained while these rows stand:\n  "
            + "\n  ".join(complaints)
            + "\nRecord a reason for each quarantined row, or clear the reason "
            "from rows that are no longer quarantined, then run again."
        )


def upgrade() -> None:
    _refuse_incoherent_rows()

    for table, status_column in TARGETS:
        op.create_check_constraint(
            f"ck_{table}_quarantine_reason",
            table,
            f"quarantine_reason IS NULL OR quarantine_reason IN {REASONS}",
        )
        op.create_check_constraint(
            f"ck_{table}_quarantine_coherent",
            table,
            _coherence(status_column),
        )


def downgrade() -> None:
    for table, _ in reversed(TARGETS):
        op.drop_constraint(f"ck_{table}_quarantine_coherent", table, type_="check")
        op.drop_constraint(f"ck_{table}_quarantine_reason", table, type_="check")
