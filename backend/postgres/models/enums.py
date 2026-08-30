from enum import Enum

class GlobalRole(str, Enum):
    super_admin = "super_admin"
    admin = "admin"
    user = "user"
    guest = "guest"

class CaseMembershipRole(str, Enum):
    owner = "owner"
    collaborator = "collaborator"


class CaseStatus(str, Enum):
    active = "active"
    on_hold = "on_hold"
    closed = "closed"


class ProofClass(str, Enum):
    """How a financial fact was obtained, which fixes what may be done with it.

    Assigned mechanically at ingestion from the source format and the outcome
    of the arithmetic.  It is never user-settable: a class that a person could
    raise would be an opinion, and the whole point of the taxonomy is that it
    is not one.  The processor boundary falls between p3 and p4.
    """

    # Structured file carrying mandatory control totals (camt.053, BAI2, NACHA).
    p0 = "p0"
    # Structured file without control totals (OFX/QFX, bank CSV).
    p1 = "p1"
    # Statement document whose arithmetic closes against its printed balances.
    p2 = "p2"
    # Statement document whose arithmetic does not close, or cannot be tried.
    p3 = "p3"
    # A financial assertion made in unstructured material.  Never admitted to
    # the ledger and never counted in a total; corroboration only.
    p4 = "p4"


class LedgerStatus(str, Enum):
    """Whether a row counts toward totals and may be traced."""

    admitted = "admitted"
    quarantined = "quarantined"
    superseded = "superseded"
    rejected = "rejected"


class TransactionDirection(str, Enum):
    """Sign discipline: magnitude lives in the amount, sign lives here."""

    credit = "credit"
    debit = "debit"


class ReconciliationStatus(str, Enum):
    """Outcome of the balance identity for one statement period."""

    not_attempted = "not_attempted"
    balanced = "balanced"
    unbalanced = "unbalanced"
    # Attempted, but the statement did not print the balances it needs.
    unavailable = "unavailable"


class DocumentStatus(str, Enum):
    admitted = "admitted"
    quarantined = "quarantined"
    superseded = "superseded"
    rejected = "rejected"


class AdjudicationSubject(str, Enum):
    transaction = "transaction"
    statement_period = "statement_period"
    source_document = "source_document"
    account = "account"


class IngestionRunStatus(str, Enum):
    """Lifecycle of one execution of the financial ingestion pipeline.

    ``aborted`` is distinct from ``failed``: a run stopped deliberately is not
    the same event as a run that broke, and conflating them would hide the
    difference from anyone later asking why a case's ledger is incomplete.
    """

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"


class BalanceSource(str, Enum):
    """Where a statement period's opening or closing balance came from.

    A balance carried forward from the neighbouring period is weaker evidence
    than one printed on the page, and a balance that was never available at all
    is not zero.  Recording which of the three applies is what stops an absent
    balance being silently treated as a real one.
    """

    printed = "printed"
    carried_forward = "carried_forward"
    absent = "absent"


class PeriodBoundsSource(str, Enum):
    """Where a statement period's start or end date came from.

    The distinction matters because of what the dates are later used for.  A
    gap between one period's end and the next period's start is the only
    evidence that a whole statement is missing, and that argument holds only
    where both dates were printed on their statements.  A bound derived from
    the first or last transaction on the page is a restatement of the rows
    already held: it shrinks to fit whatever was extracted, so it invents a gap
    where a quiet fortnight ended the month and closes a real one where the
    final rows were dropped.  Start and end are recorded separately because
    statements exist that print only a closing date.
    """

    printed = "printed"
    derived = "derived"
    absent = "absent"


class DateSource(str, Enum):
    """Which of a transaction's dates was chosen for ordering.

    Statements carry up to four dates for one movement.  The sequencing date is
    a choice, and this records which choice was made so it can be reviewed
    rather than inferred.
    """

    transaction = "transaction"
    posted = "posted"
    value = "value"
    effective = "effective"


class ExtractionLayer(int, Enum):
    """How a value was read, by decreasing determinism.

    The layer is recorded on every document and every row because it bounds
    what may be claimed about the result.  Layer 3 is a marked fallback, not a
    normal path, and a ledger built mostly from it is a ledger to be explained.
    """

    native = 0            # Structured parse of a format that defines the field.
    template = 1          # Version-controlled template match on a known layout.
    structural = 2        # Structural OCR plus model interpretation.
    grounded_model = 3    # Model with retrieval grounding.  Fallback only.
