"""admit a seventh decision: the reclassification a machine writes

Revision ID: 20260831_reclassify_decision
Revises: 20260830_adjudication_sequence
Create Date: 2026-08-31

``20260830_adjudication_sequence`` closed the decision vocabulary at six and
said what adding to it costs: "Adding a seventh is a migration, for the same
reason adding a sixth quarantine reason is."  This is that migration, and this
docstring is the part it asked for — what the seventh value means.

Why a seventh value is needed at all
------------------------------------

A proof class is a function of two things: the shape of the source, and the
outcome of the arithmetic.  Only the first is known when the document row is
written.  The arithmetic runs over transactions, the transactions reference the
document, and the document therefore has to exist before the check that grades
it can be attempted.  So every document whose format admits a check is stored
at the class its *unchecked* state deserves — p3 for a statement, and p3 even
for a camt.053, whose mandatory control totals are a guarantee that has not yet
been collected — and moved when the check reports.

``proof_class`` is the column every total filters on.  A document that changed
class with nothing on the record would change every figure computed from it,
retroactively, with no way to say when it happened or what the figure was
before.  That is the failure this table exists to prevent, so the move belongs
in this table.

Why it does not spoil the count
-------------------------------

The vocabulary is closed because "what did you do to this evidence, and how
many times" is answered by a GROUP BY, and free text answers it wrongly once
per spelling.  A machine event filed alongside human ones threatens the same
count from the other direction: an automatic promotion is not something an
analyst did, and a total that mixed the two would overstate human handling of
the evidence.

Two things keep the count exact.  The value is its own member, so
``GROUP BY decision`` separates it from every disposition.  And the rows carry
a reserved actor address that no person can hold — see
``RECONCILIATION_ACTOR_EMAIL`` in ``services.financial.documents`` — so
"how many documents did your analysts reclassify" and "how many did your
software reclassify" are both answerable, which neither would be if the move
went unlogged.

Why it has no reversal member
-----------------------------

Every disposition in this vocabulary has its undo in the same vocabulary,
because a status flag cannot hold its own history: a released row must carry a
null ``quarantine_reason``, so the release is recorded here or nowhere.  A
reclassification is not in that position.  The event carries ``before`` and
``after``, both naming a class, so a later run that moves a document back
writes another ``reclassify_document`` and the pair reads correctly in
sequence.  Adding ``unreclassify_document`` would be a second name for the
same event and would split one count into two.

On the upgrade
--------------

Widening an ``IN`` list admits values; it cannot invalidate a stored row, so
there is no preflight here and none is needed.  The downgrade is the one with
teeth: narrowing the list back to six will fail on any row already written at
the seventh value, so it refuses in advance and names the rows, rather than
letting Postgres report a constraint violation with no indication of which
evidence is affected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260831_reclassify_decision"
down_revision: Union[str, None] = "20260830_adjudication_sequence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "financial_adjudications"
CONSTRAINT = f"ck_{TABLE}_decision"

_SIX = (
    "'supersede_duplicate', 'restore_document', 'purge_duplicate', "
    "'quarantine_row', 'release_row', 'explain_balance_failure'"
)
DECISIONS_BEFORE = f"({_SIX})"
DECISIONS_AFTER = f"({_SIX}, 'reclassify_document')"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(
        CONSTRAINT, TABLE, f"decision IN {DECISIONS_AFTER}"
    )


def downgrade() -> None:
    # Narrowing the list is the direction that can contradict stored rows, so
    # the refusal names them.  A reclassification cannot be mapped onto one of
    # the six -- none of them means "the arithmetic reported and the class
    # moved" -- so the honest instruction is to decide what happens to the
    # rows, not to relabel them.
    bind = op.get_bind()
    stranded = bind.execute(
        sa.text(
            f"SELECT count(*) FROM {TABLE} "  # noqa: S608 - fixed literals
            "WHERE decision = 'reclassify_document'"
        )
    ).scalar_one()
    if stranded:
        raise RuntimeError(
            f"{stranded} row(s) in {TABLE} record a reclassification, and no "
            "value in the six-member vocabulary means what they mean. "
            "Downgrading would either drop the only record of why those "
            "documents hold the proof class they hold, or relabel a machine "
            "event as a human decision. Decide which, and do it explicitly, "
            "before narrowing the constraint."
        )

    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(
        CONSTRAINT, TABLE, f"decision IN {DECISIONS_BEFORE}"
    )
