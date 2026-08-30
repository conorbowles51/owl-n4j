"""give the adjudication log an order, and close its decision vocabulary

Revision ID: 20260830_adjudication_sequence
Revises: 20260830_quarantine_reasons
Create Date: 2026-08-30

Two changes to ``financial_adjudications``, both about the same thing: making
the table able to answer the questions it was built to answer.

*The log could not state a sequence.*  It has ``created_at`` and nothing else,
and ``created_at`` is not a total order.  Postgres ``now()`` returns
transaction-start time, so every row written in one transaction carries the
same value; the obvious tiebreak, ``id``, is a random uuid4, so ordering by the
pair is deterministic and arbitrary at once — which is worse than admitting
there is no order, because the result looks authoritative.  The pair that most
needs separating is a quarantine and the release that undid it, and that is
exactly the pair most likely to be written together.  ``subject_sequence``
numbers the decisions about one subject from 1, and the unique constraint on
``(subject_type, subject_id, subject_sequence)`` is what makes it worth having:
a gap or a repeat in a subject's history becomes a fact the database will show
you rather than an absence you would have to suspect in order to look for.

The counter is assigned in the service layer rather than by a sequence, because
it is per subject rather than per table, and because the tests build this
schema on SQLite.  Two writers racing on the same subject both read the same
high-water mark and the constraint refuses the second; that is the intended
outcome, since the alternative is two decisions claiming one position.

*The decision column was free text while the subject column was constrained,
which is the wrong way round.*  ``subject_type`` is a table name that only this
codebase writes.  ``decision`` is the answer to "what did you do to this
evidence, and how many times did you do it" — a question put in a deposition
and answered by a GROUP BY, which free text answers wrongly once per spelling.
The six admitted values are three disposition/reversal pairs plus
``explain_balance_failure``, which changes no status and records a verdict
about why an identity does not close.  Adding a seventh is a migration, for the
same reason adding a sixth quarantine reason is.

On the backfill.  Rows written before this column existed are numbered by
``created_at`` then ``id`` — which is precisely the arbitrary ordering the
column exists to replace.  There is nothing better available for them and this
note is the honest record of it: sequence numbers on rows predating this
migration are weaker evidence than those assigned after it.  In practice the
only writer to date was ``purge_document``, whose subject is deleted in the
same breath, so a subject with more than one historic decision should not
exist; the preflight below reports how many do, so the claim is checked rather
than assumed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260830_adjudication_sequence"
down_revision: Union[str, None] = "20260830_quarantine_reasons"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "financial_adjudications"

DECISIONS = (
    "('supersede_duplicate', 'restore_document', 'purge_duplicate', "
    "'quarantine_row', 'release_row', 'explain_balance_failure')"
)


def _refuse_unknown_decisions() -> None:
    """Name the rows that would break, instead of letting Postgres name a constraint."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"SELECT decision, count(*) FROM {TABLE} "  # noqa: S608 - fixed literals
            f"WHERE decision NOT IN {DECISIONS} GROUP BY decision ORDER BY decision"
        )
    ).all()
    if rows:
        listed = "; ".join(f"{value!r}: {count} row(s)" for value, count in rows)
        raise RuntimeError(
            "the decision vocabulary cannot be closed while these values "
            f"stand: {listed}. Each is a decision nobody can count. Map it "
            "onto one of the admitted values, or add the value here and say "
            "in this migration what it means."
        )


def _report_multi_decision_subjects() -> None:
    """The backfill's ordering is only as good as its input; say how much is at stake."""
    bind = op.get_bind()
    affected = bind.execute(
        sa.text(
            f"SELECT count(*) FROM (SELECT 1 FROM {TABLE} "  # noqa: S608
            "GROUP BY subject_type, subject_id HAVING count(*) > 1) t"
        )
    ).scalar_one()
    if affected:
        print(  # noqa: T201 - alembic reports to the operator on stdout
            f"  {TABLE}: {affected} subject(s) already carry more than one "
            "decision; their sequence is being inferred from created_at and "
            "id, which is the arbitrary ordering subject_sequence exists to "
            "replace. Sequences on these rows are weaker evidence than any "
            "assigned after this migration."
        )


def upgrade() -> None:
    _refuse_unknown_decisions()
    _report_multi_decision_subjects()

    op.add_column(TABLE, sa.Column("subject_sequence", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            f"UPDATE {TABLE} SET subject_sequence = ordered.seq "  # noqa: S608
            "FROM (SELECT id, row_number() OVER ("
            "PARTITION BY subject_type, subject_id ORDER BY created_at, id"
            f") AS seq FROM {TABLE}) AS ordered "
            f"WHERE {TABLE}.id = ordered.id"
        )
    )

    op.alter_column(TABLE, "subject_sequence", nullable=False)

    op.create_unique_constraint(
        f"uq_{TABLE}_subject_sequence",
        TABLE,
        ["subject_type", "subject_id", "subject_sequence"],
    )
    op.create_check_constraint(
        f"ck_{TABLE}_sequence_positive", TABLE, "subject_sequence >= 1"
    )
    op.create_check_constraint(
        f"ck_{TABLE}_decision", TABLE, f"decision IN {DECISIONS}"
    )


def downgrade() -> None:
    op.drop_constraint(f"ck_{TABLE}_decision", TABLE, type_="check")
    op.drop_constraint(f"ck_{TABLE}_sequence_positive", TABLE, type_="check")
    op.drop_constraint(f"uq_{TABLE}_subject_sequence", TABLE, type_="unique")
    op.drop_column(TABLE, "subject_sequence")
