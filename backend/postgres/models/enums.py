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


class QuarantineReason(str, Enum):
    """Why a row or document was set aside.  A closed vocabulary, deliberately.

    Quarantine removes evidence from every total that follows it, so the
    grounds have to be reportable in aggregate: "how many rows did we set
    aside, and on what basis" is a question opposing counsel is entitled to
    ask, and a free-text column cannot answer it.

    The list is short because each entry has to name something the code can
    actually prove or a person can actually decide.  Two absences are
    deliberate.  A statement that printed no opening or closing balance is not
    quarantined — it is ``unavailable``, which is a fact about the document
    rather than a fault in it, and setting aside every statement that declined
    to print a control total would discard most of a typical disclosure.  And
    there is no reason meaning "a row whose amount happens to equal the
    residual", because that is a coincidence rather than a finding; see
    ``services.financial.quarantine`` for why admitting one would let the
    system manufacture a balance.
    """

    # The printed running-balance chain does not admit this row.  Proof-grade:
    # the statement's own arithmetic contradicts it.
    balance_break = "balance_break"
    # The amount, direction or date could not be read exactly, so the row
    # cannot be summed without inventing the part that was missing.
    unreadable_row = "unreadable_row"
    # Denominated differently from the period holding it.  Summing across
    # currencies produces a number that means nothing.
    currency_mismatch = "currency_mismatch"
    # Document-level: the balance identity failed and no cause was localised.
    # The rows may all be right; what is not established is that they are all
    # of them.
    unexplained_delta = "unexplained_delta"
    # A person decided, and the adjudication record carries the reasoning.
    adjudicated = "adjudicated"


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


class TotalsConvention(str, Enum):
    """How a source document signs the outflow figures it prints for itself.

    A statement's own control totals are the strongest evidence it carries,
    because they were computed by the institution rather than read by us.  But
    they arrive in two incompatible dialects.  Most statements print outflows
    as magnitudes, so the identity subtracts them::

        opening + credits - debits - checks - fees = closing

    Others print outflows already negative, so the identity adds them::

        opening + credits + debits + checks + fees = closing

    Both are correct and neither is announced.  Measured across the 326
    extraction files of the ET-Fraud corpus, 197 carry a testable identity:
    182 close only as ``magnitude``, 2 close only as ``signed``, 1 closes
    either way because every outflow it prints is zero, and 12 close neither
    way and are a separate question.  The signed pair are exact to the cent
    under their own dialect and miss by $279,555.74 and $280,288.96 under the
    other.  A check hard-coded to one dialect therefore does not merely miss
    those two, it reports the two most accurate documents in the corpus as the
    two largest discrepancies in it.

    The convention is recorded rather than inferred at the point of use.  A
    check permitted to retry dialects until one closes cannot fail, and a check
    that cannot fail is not evidence.  ``undetermined`` is the honest state for
    a document whose own figures do not distinguish the two — every outflow
    zero, for instance — and it is resolved from the institution's prevailing
    convention or by a person, not by whichever formula happens to close.
    """

    magnitude = "magnitude"
    signed = "signed"
    undetermined = "undetermined"


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


class DuplicateMatchRung(int, Enum):
    """How strongly one document was shown to duplicate another.

    The rungs are nested: identical bytes imply an identical reading, and an
    identical reading implies the same account and period.  So a match at any
    rung is also a match at every weaker rung, and recording the strongest one
    that held says everything about the claim.

    The distinction is not pedantry, because the rungs do not license the same
    action.  ``identical_bytes`` and ``identical_reading`` establish that two
    documents say the same thing, and a second copy of the same thing is not
    additional evidence of anything.  ``same_account_period`` establishes only
    that two documents cover the same account over the same dates, which is
    also true of an interim statement and the final one that replaces it, of a
    statement and its own corrected reissue, and of the first and second halves
    of a month printed separately.  Excluding on that alone would discard real
    evidence, so it is raised for a person to look at rather than acted on.
    """

    # Same sha256 over the file itself.  A re-upload of one file.
    identical_bytes = 0
    # Different bytes, identical extracted content: the same statement
    # re-scanned, re-exported, or saved by a different tool.  This is the rung
    # that matters, because it is the one byte-identity misses.
    identical_reading = 1
    # Same account over the same dates, with content that differs.  A candidate
    # and nothing more.
    same_account_period = 2
