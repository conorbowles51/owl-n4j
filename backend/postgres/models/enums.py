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
    """What a decision was about.

    ``evidence_file`` is the one member naming no financial table, and it is
    why the ledger dropped its ``financial_`` prefix in
    ``20260901_rename_adjudications``.  The decision to send a file for
    document processing is taken on the evidence list, *before* any financial
    row exists to be the subject of it — which is exactly what makes it worth
    recording, since nothing downstream would otherwise show that anyone
    chose.  Nothing structural had to change to hold it: ``subject_id`` never
    carried a foreign key, so the only thing that ever stopped it was one
    ``CHECK`` constraint.
    """

    transaction = "transaction"
    statement_period = "statement_period"
    source_document = "source_document"
    account = "account"
    evidence_file = "evidence_file"


class AdjudicationDecision(str, Enum):
    """What was decided.  Closed for the reason the quarantine reasons are.

    ``subject_type`` was constrained from the start and ``decision`` was left
    as free text, which is the wrong way round: the subject is a table name
    that only this codebase writes, while the decision is the answer to "what
    did you do to this evidence, and how many times did you do it" — a
    question put in a deposition and answered by a GROUP BY.  Free text
    cannot answer it, because 'release', 'released' and 'release_row' are
    three answers to one question and the count is wrong three ways.

    The pairs matter more than the members.  Every disposition here has its
    reversal in the same vocabulary, because the ledger appends: undoing a
    supersession or a quarantine writes the *undo*, it does not retract the
    original.  The row-level columns cannot carry that history — a released
    row must have a null ``quarantine_reason`` to satisfy
    ``ck_financial_transactions_quarantine_coherent`` — so if the reversal is
    not appended here it is not recorded anywhere at all.

    ``explain_balance_failure`` is the odd one and is deliberately not a
    disposition.  It records a verdict from
    :mod:`services.financial.adjudication` about *why* an identity does not
    close.  It changes no status and never can: see that module on why a
    well-corroborated explanation of a p3 document leaves it p3.

    ``reclassify_document`` is the only member here that a machine writes, and
    the only one that changes a status without anyone deciding anything.  A
    proof class is a function of the source shape and the arithmetic outcome,
    but the outcome is not known when the document row is written — the
    arithmetic runs over transactions that do not exist yet — so every
    document whose format admits a check is stored at the class its *unchecked*
    state deserves and moved when the check reports.  Recording that move is
    not optional: ``proof_class`` is what totals filter on, so a document that
    silently changed class would change every figure computed from it with
    nothing on the record to say when or why.

    It is a member rather than free text for the reason the others are, and
    it does not spoil the deposition count, because the automatic events are
    separable by actor: they carry :data:`RECONCILIATION_ACTOR_EMAIL` from
    :mod:`services.financial.documents`, which no person can hold.  "How many
    documents did your analysts reclassify" and "how many did your software
    reclassify" are therefore both exactly answerable, which is more than
    either question could be if the move went unlogged.

    It has no reversal member because it is its own: the event carries the
    class before and the class after, so a later run that moves a document
    back writes another ``reclassify_document`` rather than an undo.  The
    disposition pairs need two names because a status flag cannot hold its own
    history; a proof class recorded as a before/after pair already does.

    ``admit_financial_document`` needs its name read carefully, because the
    name points the wrong way on its own.  It does **not** mean a document was
    admitted *into* the financial ledger.  It means a file the router held
    back — a bank statement that arrived on the evidence list, where the
    general document pipeline would index it as prose and its figures would
    become searchable text that no total could ever be traced to — was
    admitted *out* to that pipeline anyway, by a named person who was shown
    what the router found and chose to proceed.  ``financial`` in the name
    describes the *document*, not the destination.  Nothing is admitted to the
    ledger by this event and nothing can be: it is written on the evidence
    file, before any financial row exists.

    It is the only member whose subject is an ``evidence_file``, and the only
    one recording a decision to *not* use this subsystem on evidence it would
    otherwise claim.  That is precisely why it is logged.  An override that
    left no trace would make the router's judgement look like the system's
    behaviour, and a reader months later, finding a statement's figures in the
    text index and nowhere in any total, would have no way to tell a
    deliberate call from a routing failure.

    It takes no reversal member, and for the same reason
    ``explain_balance_failure`` does not: it changes no stored column.  It
    authorises one send, and a send cannot be un-sent.  Reprocessing the same
    file through the financial path later is a new ingestion with its own run
    and its own records, not an undo of this.
    """

    supersede_duplicate = "supersede_duplicate"
    restore_document = "restore_document"
    purge_duplicate = "purge_duplicate"

    quarantine_row = "quarantine_row"
    release_row = "release_row"

    explain_balance_failure = "explain_balance_failure"

    reclassify_document = "reclassify_document"

    admit_financial_document = "admit_financial_document"
    correct_transaction = "correct_transaction"
    set_account_party = "set_account_party"


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
    """How a value was read; codes 0–3 order automated extraction methods.

    Investigator review is a separate method, not a fifth automation tier or
    a statement that arithmetic passed. Original extraction provenance and the
    investigator's review history must be retained separately. Layer 3 remains
    the marked model fallback.
    """

    native = 0            # Structured parse of a format that defines the field.
    template = 1          # Version-controlled template match on a known layout.
    structural = 2        # Structural OCR plus model interpretation.
    grounded_model = 3    # Model with retrieval grounding.  Fallback only.
    investigator_review = 4  # Explicit reading with retained source/review history.


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


class CoordinateSpace(str, Enum):
    """Which coordinate space a rectangle's numbers were measured in.

    This exists because two PyMuPDF calls on the *same page* return geometry in
    two different spaces, and nothing in the numbers says which.  Measured on
    1.28.2 against a synthetic page carrying one ruled table and one text run,
    at each of the four legal rotations:

    * ``page.get_text("words")`` returns the **unrotated** rectangle.  The
      numbers do not change at all as the page is rotated.
    * ``page.find_tables()`` returns the **displayed** rectangle, already
      rotated, and it does change.

    So the same rectangle, in the same file, means two different places on the
    paper depending only on which function produced it.  Applying the rotation
    matrix to the table box at 90 degrees pushes it off the page entirely
    (y1=692 against a 612-high page), and *failing* to apply it to the word box
    leaves it silently in the wrong quarter.

    A containment check cannot recover the space, which is the reason this is a
    recorded fact rather than something inferred later.  At 180 degrees both
    readings of the table box land inside the page — ``(212, 632, 532, 692)``
    as-is and ``(80, 100, 400, 160)`` rotated — and both look entirely
    reasonable.  Only one is where the ink is.

    At rotation 0 the two spaces coincide exactly, so any test that exercises
    only an unrotated page passes under either convention while proving
    nothing.  The tests for this module use rotated pages for that reason.
    """

    #: Origin top-left of the crop box, before page rotation is applied.
    #: What ``get_text`` reports.  Must be multiplied by ``rotation_matrix``
    #: before it can be drawn.
    pdf_unrotated = "pdf_unrotated"
    #: Origin top-left of the page as displayed, rotation already applied.
    #: What ``find_tables`` reports, and the only space this module stores.
    pdf_displayed = "pdf_displayed"


class LocatorKind(str, Enum):
    """How well a stored value can be pointed back at its source.

    The distinction the vocabulary exists to preserve is between *no rectangle
    because none is possible* and *no rectangle because we lost it*.  Modelling
    the box as an optional field collapses those, and then a viewer showing
    "source unavailable" cannot say whether that is an honest property of a CSV
    feed or a defect in the PDF reader — which is exactly the question asked
    when the exhibit is challenged.

    ``page_only`` is the honest description of every row extracted before this
    module existed: the corpus JSON carries ``source_page`` and no geometry, so
    those rows can be pointed at a page and no further.  Back-filling them to
    ``page_rectangle`` would claim a precision that was never captured.
    """

    #: Page and rectangle both known.  Click-through resolves to a highlight.
    page_rectangle = "page_rectangle"
    #: Page known, rectangle never captured.  Click-through opens the page.
    page_only = "page_only"
    #: The source format has no pages: a CSV row, a camt.053 entry, an API
    #: feed.  There is nothing to point at and that is not a shortcoming.
    not_positional = "not_positional"
    #: The source is paginated, capture was attempted, and it failed.  Distinct
    #: from ``page_only`` because this one is a defect and should be counted.
    unlocated = "unlocated"


class IdentifierKind(str, Enum):
    """What a stored identifier is, said by the caller rather than inferred.

    The vocabulary is deliberately not a detector.  ``021000021`` is a valid
    ABA routing number and a syntactically unremarkable US social security
    number, and ``4111111111111111`` is a card number and also sixteen digits
    of nothing in particular.  A module that guessed would be right most of the
    time and confidently wrong the rest, and the wrong answers would arrive
    dressed as verifications.  The caller read the value out of a named field
    and therefore already knows; it is asked to say so.

    Kinds with no check digit are members here rather than absent, so that a
    caller handling a BIC or an EIN gets an explicit "there is nothing to
    verify" instead of a lookup failure it might quietly treat as a pass.
    """

    #: ISO 13616 international bank account number.  ISO 7064 MOD-97-10.
    iban = "iban"
    #: US ABA routing transit number.  Nine digits, weighted mod 10.
    aba_routing = "aba_routing"
    #: A payment card primary account number.  ISO/IEC 7812-1, Luhn.
    payment_card = "payment_card"
    #: ISO 17442 legal entity identifier.  Twenty characters, MOD-97-10.
    lei = "lei"
    #: ISO 9362 business identifier code.  Structure only; no check digit
    #: exists at all, and this member makes that unmissable.
    bic = "bic"
    #: US social security number.  Randomised since June 2011; only the
    #: never-issued ranges survive as a check, and they are not a check digit.
    us_ssn = "us_ssn"
    #: US employer identification number.  Nine digits and no check digit.
    us_ein = "us_ein"


class CheckDigitOutcome(str, Enum):
    """The verdict of a field-level check, in four values rather than two.

    A boolean would collapse the two failures that call for opposite responses.
    *Malformed* says the value never had the shape the check needs — nine
    characters where eight and a letter were required — and points at the
    extractor or at the field mapping.  *Failed* says the value had exactly the
    right shape, the arithmetic ran, and the number disagrees with itself; that
    points at the document, and is a finding to be flagged
    rather than a row to be dropped.  Reporting both as ``False`` would send an
    analyst to re-read a bank statement over what was a column misalignment,
    and to re-run an extractor over what was a genuine transcription error in
    the source.

    ``no_check_digit`` is the fourth because silence is the dangerous answer.
    A BIC that comes back with no verdict at all looks, at a glance and in a
    log line, exactly like one that passed.
    """

    #: The arithmetic ran and the value agrees with itself.
    passed = "passed"
    #: The arithmetic ran and the value disagrees with itself.  A finding
    #: about the document, not about the reader.
    failed = "failed"
    #: The value is the wrong shape for the check to run at all.  A finding
    #: about the extraction, not about the document.
    malformed = "malformed"
    #: The identifier is well-formed and the standard gives it no check digit.
    #: Structure is all that was verified and the result says so.
    no_check_digit = "no_check_digit"


class LinkRelation(str, Enum):
    """What a link between two rows actually asserts.

    The two values are not degrees of the same thing.  They are opposite
    claims about whether the ledger is holding one movement or two, and
    conflating them corrupts totals in one direction or balances in the other.

    ``same_side`` says two rows are the *same* movement of money in the *same*
    account, seen from two sources -- the payer's own statement and the payer's
    own ACH file, say.  Only one of them is a movement.  Anything that adds
    them together counts the payment twice.

    ``counterparty`` says two rows are the *two sides* of one payment: a debit
    in the payer's account and a credit in the payee's.  Both are real, both
    belong in their own account's totals, and both are needed for either
    account's balance identity to hold.  Merging them, or dropping one, breaks
    :mod:`services.financial.reconcile` for two periods at once.  The link is
    what lets a tracing engine walk from one account to the other; it is not a
    licence to collapse anything.
    """

    #: One movement, observed more than once.  Redundant: count it once.
    same_side = "same_side"
    #: Two movements, being the two ends of one payment.  Not redundant.
    counterparty = "counterparty"


class JoinTier(int, Enum):
    """How strongly two rows were shown to describe one payment.

    Ordered by decreasing strength so that ``<`` means stronger, matching
    :class:`DuplicateMatchRung`.  Unlike that class the tiers are *not* nested:
    a pair joined on a shared UETR has not thereby been shown to agree on
    amount and date, because the tiers read different fields.  So a link
    records the one tier it was made at, and the components it actually
    matched on travel with it.

    The tier is not decoration.  It decides what may be done without a person:
    tiers 0 and 1 are mechanical and reproducible, and tier 2 is a proposal
    that must never merge automatically.
    """

    #: A shared identifier that is unique within a scope both rows share.
    #: Certain, and only as certain as the scope is honest -- which is why
    #: :class:`ReferenceScope` exists.
    exact_identifier = 0
    #: Amount, currency, direction and date agree, the last within a stated
    #: tolerance.  Mechanically reproducible from the ledger alone.
    deterministic_composite = 1
    #: Amount and approximate date and a fuzzy counterparty name.  A proposal
    #: for a human, never an assertion.
    probabilistic = 2


class ReferenceScope(str, Enum):
    """The universe within which an identifier is unique.

    Tier-0 joins live or die on this.  "Exact match" on a bare string is a
    trap: cheque number 1001 exists in every chequebook ever printed, and
    joining two accounts' cheque 1001 into one payment is a confident,
    mechanical, entirely wrong answer that no downstream check would catch.
    An identifier is therefore only ever compared inside a scope, and a
    reference whose scope key is unknown is not a candidate for a tier-0 join
    at all.
    """

    #: Unique everywhere by construction.  A UETR is a UUID and needs no
    #: further qualification.
    global_ = "global"
    #: Unique within the institution that issued it.  A NACHA trace number
    #: carries its own scope -- the first eight digits are the ODFI's routing
    #: prefix -- so full-string equality is already scoped equality.
    institution = "institution"
    #: Unique within one account, and reused once the book runs out.  Usable
    #: for a ``same_side`` link, where the account is shared by definition,
    #: and useless for a ``counterparty`` link, where it is not.
    account = "account"


class LinkOutcome(str, Enum):
    """Whether a match resolved to one partner, or to several.

    A payment has two ends.  When one debit answers to three candidate credits
    the honest result is not the first of the three; it is the fact that there
    are three.  Emitting the first would let a tracing engine walk money down a
    path chosen by iteration order, and the ambiguity -- the thing an analyst
    needs to see -- would be the one part not written down.
    """

    #: Exactly one partner on each side.  Asserted.
    resolved = "resolved"
    #: More than one partner.  Recorded with all of them, asserted as none.
    ambiguous = "ambiguous"
