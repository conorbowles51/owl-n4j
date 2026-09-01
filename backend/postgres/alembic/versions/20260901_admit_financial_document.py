"""admit an eighth decision, and the first subject that is not a financial row

Revision ID: 20260901_admit_financial_document
Revises: 20260901_rename_adjudications
Create Date: 2026-09-01

``20260901_rename_adjudications`` dropped the ``financial_`` prefix from this
table on the grounds that the structure was never financial — ``subject_id``
has never carried a foreign key — and that what actually confined it was one
``CHECK`` constraint.  This migration widens that constraint, and a second one,
and is the whole reason the rename was worth doing first.

What is being recorded
----------------------

Route detection runs before the general document pipeline and holds back files
that look like bank statements, because indexing a statement as prose turns its
figures into searchable text that no total can ever be traced to.  An
investigator who is shown what the router found may disagree, and should be
able to proceed.  ``admit_financial_document`` is the record that they did.

The name points the wrong way if read quickly, so it is worth saying plainly:
this does **not** mean a document was admitted *into* the financial ledger.  It
means a financial document was admitted *out* to the general document pipeline,
by a named person, against the router's judgement.  ``financial`` describes the
document; it does not describe the destination.  Nothing is admitted to the
ledger by this event and nothing could be — it is written on the evidence file,
before any financial row exists.

Why it is logged rather than simply allowed
-------------------------------------------

An override that left no trace would make one person's judgement look like the
system's behaviour.  A reader months later, finding a statement's figures in
the text index and in no total anywhere, would have no way to distinguish a
deliberate call with reasons behind it from a routing failure nobody noticed.
The event carries the actor and a mandatory reason, so the two are never
confused.

It is also, deliberately, the only member of the vocabulary that records a
decision *not* to use this subsystem on evidence it would otherwise claim.
That is not a gap in the log.  It is the entry the log most needs.

Why the subject has to be the evidence file
-------------------------------------------

There is nothing else it could be.  The decision is taken on the evidence list,
before ingestion, so no ``financial_source_document`` row exists yet and none
may be invented to hold the record — a document row that named no ingestion run
and carried no proof class would be a placeholder, and the account writer's
placeholder guard exists because placeholders in this ledger are read later as
facts.

``evidence_file`` is therefore the first subject that is not a financial table.
Admitting it costs one ``IN`` list, which is the point the rename was making.

Why there is no reversal member
-------------------------------

For the reason ``explain_balance_failure`` has none: it changes no stored
column.  It authorises one send, and a send cannot be un-sent.  Putting the
same file through the financial path later is a new ingestion with its own run
and its own records, not an undo of this one.

What is deliberately not constrained
------------------------------------

The two ``IN`` lists remain independent, so nothing at the database level stops
``admit_financial_document`` being recorded against a transaction, or
``quarantine_row`` against an evidence file.  That is not an oversight
introduced here; the vocabulary has never paired decisions with subjects, and
``quarantine_row`` against an account has always been equally meaningless and
equally permitted.  The pairing is enforced where it can be enforced with the
subject in hand rather than its id — ``services.financial.decisions.record``
takes the mapped object and checks it against ``_SUBJECT_MODELS`` — and adding
a pairing constraint for one member only would suggest the others had been
checked.

On the upgrade
--------------

Widening an ``IN`` list admits values; it cannot invalidate a stored row, so
there is no preflight and none is needed.  The downgrade is the one with teeth,
and it has two independent ways to be blocked, so it counts and reports them
separately: a row may carry the new subject, or the new decision, and being
told only that "some rows" are in the way would leave the operator guessing
which narrowing to look at.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260901_admit_financial_document"
down_revision: Union[str, None] = "20260901_rename_adjudications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "adjudications"
SUBJECT_CONSTRAINT = f"ck_{TABLE}_subject_type"
DECISION_CONSTRAINT = f"ck_{TABLE}_decision"

_SUBJECTS_BEFORE = "'transaction', 'statement_period', 'source_document', 'account'"
SUBJECTS_BEFORE = f"({_SUBJECTS_BEFORE})"
SUBJECTS_AFTER = f"({_SUBJECTS_BEFORE}, 'evidence_file')"

_DECISIONS_BEFORE = (
    "'supersede_duplicate', 'restore_document', 'purge_duplicate', "
    "'quarantine_row', 'release_row', 'explain_balance_failure', "
    "'reclassify_document'"
)
DECISIONS_BEFORE = f"({_DECISIONS_BEFORE})"
DECISIONS_AFTER = f"({_DECISIONS_BEFORE}, 'admit_financial_document')"

NEW_SUBJECT = "evidence_file"
NEW_DECISION = "admit_financial_document"


def upgrade() -> None:
    op.drop_constraint(SUBJECT_CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(
        SUBJECT_CONSTRAINT, TABLE, f"subject_type IN {SUBJECTS_AFTER}"
    )
    op.drop_constraint(DECISION_CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(
        DECISION_CONSTRAINT, TABLE, f"decision IN {DECISIONS_AFTER}"
    )


def _count(bind, column: str, value: str) -> int:
    """Rows carrying one of the values this migration admitted.

    The column name is interpolated and the value is bound.  The two names are
    module constants a few lines above rather than anything reaching this from
    outside, and a bound parameter cannot stand where an identifier goes.
    """
    return bind.execute(
        sa.text(
            f"SELECT count(*) FROM {TABLE} "  # noqa: S608 - fixed literals
            f"WHERE {column} = :value"
        ),
        {"value": value},
    ).scalar_one()


def downgrade() -> None:
    # Narrowing is the direction that can contradict stored rows, so the
    # refusal names them and says which of the two lists is blocked.  Neither
    # value can be mapped onto the older vocabulary: no other subject means "a
    # file on the evidence list", and no other decision means "sent to the
    # general pipeline against the router's finding".  So the honest
    # instruction is to decide what happens to the rows, not to relabel them.
    bind = op.get_bind()
    blocked = []
    stranded_subject = _count(bind, "subject_type", NEW_SUBJECT)
    if stranded_subject:
        blocked.append(
            f"{stranded_subject} row(s) name an {NEW_SUBJECT} as their "
            "subject, and no older subject means a file on the evidence list"
        )
    stranded_decision = _count(bind, "decision", NEW_DECISION)
    if stranded_decision:
        blocked.append(
            f"{stranded_decision} row(s) record a {NEW_DECISION}, and no "
            "older decision means a financial document sent to the general "
            "pipeline against the router's finding"
        )
    if blocked:
        raise RuntimeError(
            f"cannot narrow the {TABLE} vocabulary: "
            + "; ".join(blocked)
            + ". Downgrading would drop the only record that anyone chose to "
            "route this evidence away from financial processing, which is the "
            "record most likely to be asked about. Decide what happens to "
            "those rows, and do it explicitly, before narrowing."
        )

    op.drop_constraint(DECISION_CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(
        DECISION_CONSTRAINT, TABLE, f"decision IN {DECISIONS_BEFORE}"
    )
    op.drop_constraint(SUBJECT_CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(
        SUBJECT_CONSTRAINT, TABLE, f"subject_type IN {SUBJECTS_BEFORE}"
    )
