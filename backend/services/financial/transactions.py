"""The ledger row writer: the last boundary before money becomes a total.

Why this writer takes a document and not a row
----------------------------------------------

``FinancialTransaction.content_hash`` fingerprints the normalised reading so
that re-reading one document twice produces the same rows rather than a second
set, and ``uq_financial_transactions_document_content`` makes that a guarantee.
Two genuinely distinct rows can carry the same reading -- two identical cash
withdrawals on one day, two identical card fees -- and they are told apart by
an occurrence index that :func:`references.document_content_hashes` assigns by
counting repeats across the whole document.

A row-at-a-time writer cannot count repeats it has not seen.  It would take the
default occurrence of zero, the second identical row would collide with the
first, and the unique constraint would reject a row that belongs in the ledger.
So the unit here is the document's rows together.  ``references`` says the same
thing in its own words: passing occurrences by hand row by row is how two rows
end up sharing one.

Sign is declared, never inferred
--------------------------------

``amount_minor`` is a magnitude and ``direction`` carries the sign, enforced by
``ck_financial_transactions_amount_non_negative`` and again by
:class:`~services.financial.references.RowReading`.  The native parsers each
derive direction from what their format defines -- ``CdtDbtInd`` in camt.053, a
type code in BAI2, ``C``/``D``/``RC``/``RD`` in MT940 -- and hand this writer a
reading that is already normalised.

Everything else arrives signed: a CSV export with one amount column, an OFX
``TRNAMT``, a PDF whose debits are printed in parentheses.  There are two
opposite conventions in the wild and no way to tell them apart from one row.  A
column of negatives is a customer-view statement under one convention and an
accounting extract under the other, and picking whichever makes the statement
balance is exactly what :mod:`services.financial.bai2` refuses to do:

    No convention is retried until one balances. ... Trying conventions until
    one passes is how a file with a genuine error gets silently repaired.

So :func:`normalise_sign` requires the caller to *name* the convention, and a
named convention that contradicts a direction the source also stated is an
error rather than a preference.  Zero has no sign under either convention, so a
zero amount must arrive with its direction stated.

The class a row carries has to move when its document moves
-----------------------------------------------------------

A row's ``proof_class`` is its document's.  It is copied onto the row because
totals filter on it, and a filter that joins to the document on every aggregate
is a filter that gets forgotten.

The copy has to be maintained, and the reason is not hypothetical.  A statement
is admitted at p3.  Its rows cannot be written before it exists, and the
arithmetic cannot run before its rows exist, so the rows are necessarily
written at p3 as well.  Reconciliation then closes and the document is promoted
to p2.  ``DEFAULT_TOTAL_CLASSES`` is ``{p0, p1, p2}``, so if the rows stay at
p3 every row of a statement that *balanced* silently leaves every total.  The
arithmetic passed and the money disappeared from the report.

:func:`services.financial.documents.reclassify_after_reconciliation` therefore
moves the document's rows with it, and records how many it moved.

What the writer derives, and the caller may not supply
------------------------------------------------------

``proof_class``, ``ref_id``, ``content_hash``, ``case_id`` and
``ingestion_run_id`` are all derived.  The first for the reason the document
writer gives -- a class a caller chooses is an opinion, and it decides which
rows enter a total.  The reference and the hash because they are functions of
the reading and the document digest, and a caller-supplied reference is a
reference that stops reproducing when the file is ingested again.

``provenance["locator"]`` is likewise written here and only here, serialised
from the draft's own ``locator`` field.  A caller-supplied one is refused at
the draft: the locator is a typed value whose coherence rules live in
:mod:`services.financial.locators`, and a hand-built dict that bypassed them
would be indistinguishable from one that did not once stored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence

from postgres.models.enums import (
    DateSource,
    ExtractionLayer,
    ProofClass,
    TransactionDirection,
)
from postgres.models.financial import (
    FinancialAccount,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from services.financial.locators import Locator
from services.financial.money import get_currency
from services.financial.proof_class import may_produce_ledger_rows
from services.financial.references import (
    RowReading,
    document_content_hashes,
    ref_id as build_ref_id,
)
from services.financial.runs import RunScopeError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

    from services.financial.runs import IngestionRunHandle


#: The provenance key a row's locator is stored under.  The same key
#: :mod:`services.financial.table_geometry` writes cell locators under, so one
#: reader can open a row's place in its source whatever produced the row.
LOCATOR_PROVENANCE_KEY = "locator"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TransactionWriteError(Exception):
    """Base class for every refusal in this module.

    Named for the write rather than for the row, because
    :mod:`services.financial.references` already owns ``RowReferenceError`` for
    what is wrong with a reading in itself.  A reading can be perfectly well
    formed and still have no business being stored against this document.
    """


class TransactionFieldError(TransactionWriteError):
    """A draft field is missing, malformed, or longer than its column."""


class SignConventionError(TransactionWriteError):
    """A signed amount cannot be resolved to a magnitude and a direction."""


class NonLedgerClassError(TransactionWriteError):
    """The document's proof class may not produce ledger rows at all.

    Not :class:`services.financial.correlation.LedgerClassError`, which is the
    same refusal seen from the other end: that one rejects a p4 entry offered
    as corroboration of an assertion, this one rejects a p4 document asked to
    yield rows in the first place.
    """


class OrderingDateError(TransactionWriteError):
    """No date is available to order a row by, or the one given is not one."""


# ---------------------------------------------------------------------------
# Sign
# ---------------------------------------------------------------------------


class SignConvention(str, Enum):
    """How a source expresses which way the money went.

    Three values rather than two, because "the amount is signed" is not one
    convention.  A bank statement written from the customer's point of view
    signs money leaving the account negative; a ledger extract written from the
    bookkeeper's signs a debit positive.  The same column of numbers means
    opposite things under the two, and nothing inside a single row says which.

    A different axis from
    :class:`~postgres.models.enums.TotalsConvention`, and deliberately not
    merged with it.  That one describes how a document signs the *control
    totals it prints for itself* -- whether the header identity subtracts
    outflows or adds them.  This one describes how the *transaction rows* carry
    their amounts.  A statement may perfectly well print magnitude header
    totals above a signed amount column, so one value cannot answer both
    questions, and a shared enum would invite a caller to read one off the
    other.

    Not persisted, which is why it lives here rather than in the model enums:
    ``TotalsConvention`` is a property of the document that has to survive on
    the row, whereas this is a declaration the caller makes at the moment of
    writing, and what survives is its already-normalised result -- a magnitude
    in ``amount_minor`` and a direction beside it.
    """

    #: The source states direction separately; the amount is already a
    #: magnitude.  Every native parser produces this.
    direction_indicator = "direction_indicator"
    #: One signed column, customer view: negative is money out, so a debit.
    debit_negative = "debit_negative"
    #: One signed column, bookkeeping view: positive is a debit.
    debit_positive = "debit_positive"


def normalise_sign(
    amount_minor: int,
    convention: SignConvention,
    *,
    stated: Optional[TransactionDirection] = None,
) -> tuple[int, TransactionDirection]:
    """Resolve an amount as written into a magnitude and a direction.

    ``stated`` is the direction the source declared, where it declared one.
    Under :attr:`SignConvention.direction_indicator` it is required, because
    that convention is the claim that the source said so.  Under a signed
    convention it is optional, and where it is present it must agree with the
    sign: a source that says "credit" beside a negative number under a
    customer-view convention has said two contradictory things about one
    movement, and the writer is not entitled to pick the one it prefers.

    Zero is refused under both signed conventions.  It is a real amount -- a
    reversed fee, a notional entry -- but it has no sign, so its direction has
    to be stated rather than read off.
    """
    if not isinstance(convention, SignConvention):
        raise SignConventionError(
            f"convention {convention!r} is not a SignConvention; the "
            "convention is the caller's declaration and cannot be a string "
            "that happens to match"
        )
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise SignConventionError(
            f"amount_minor is {type(amount_minor).__name__}; amounts are "
            "exact integers of minor units and cannot go through a float"
        )
    if stated is not None and not isinstance(stated, TransactionDirection):
        raise SignConventionError(
            f"stated direction {stated!r} is not a TransactionDirection"
        )

    if convention is SignConvention.direction_indicator:
        if stated is None:
            raise SignConventionError(
                "convention is direction_indicator but no direction was "
                "stated; that convention is precisely the claim that the "
                "source said which way the money went"
            )
        if amount_minor < 0:
            raise SignConventionError(
                f"amount {amount_minor} is negative under direction_indicator, "
                "where the amount is a magnitude and the direction carries the "
                "sign; a negative here means the source signed its amounts and "
                "the convention was named wrongly"
            )
        return amount_minor, stated

    if amount_minor == 0:
        raise SignConventionError(
            f"amount is zero under {convention.value}, which reads direction "
            "off the sign, and zero has none; state the direction for this row"
        )

    if convention is SignConvention.debit_negative:
        implied = (
            TransactionDirection.debit
            if amount_minor < 0
            else TransactionDirection.credit
        )
    else:
        implied = (
            TransactionDirection.debit
            if amount_minor > 0
            else TransactionDirection.credit
        )

    if stated is not None and stated is not implied:
        raise SignConventionError(
            f"the source states {stated.value} but under {convention.value} an "
            f"amount of {amount_minor} is a {implied.value}; one of the two "
            "readings of this row is wrong and choosing between them here "
            "would bury the disagreement in a total"
        )
    return abs(amount_minor), implied


# ---------------------------------------------------------------------------
# Ordering date
# ---------------------------------------------------------------------------

#: The order in which a date is chosen for sequencing, most authoritative
#: first.  Posted leads because the running balance on a statement advances in
#: posting order, so it is the choice that reproduces the printed sequence and
#: the period totals computed from it.  :mod:`services.financial.native` makes
#: the same choice for camt.053, preferring the booking date over the value
#: date, and this is that rule written down for the sources that arrive with no
#: choice already made.
ORDERING_PRECEDENCE: tuple[tuple[DateSource, str], ...] = (
    (DateSource.posted, "posted_date"),
    (DateSource.transaction, "transaction_date"),
    (DateSource.value, "value_date"),
    (DateSource.effective, "effective_date"),
)


def choose_ordering_date(reading: RowReading) -> tuple[date, DateSource]:
    """Pick the date a row is sequenced by, and say which one it was.

    For readings that arrive with no choice already made.  Rows from
    :mod:`services.financial.native` carry their own ``ordering_date`` and
    ``ordering_date_source`` because each format defines which of its dates
    governs, and a general precedence must not overrule a format that says.

    Raises rather than inventing a date.  A row with no date at all cannot be
    ordered, cannot sit inside a period, and would fail
    ``ck_financial_transactions_has_a_date`` on the way in; refusing here says
    why instead of letting the database say that something was null.
    """
    for source, attribute in ORDERING_PRECEDENCE:
        value = getattr(reading, attribute)
        if value is None:
            continue
        if isinstance(value, datetime) or not isinstance(value, date):
            raise OrderingDateError(
                f"{attribute} is {type(value).__name__}; the column is a DATE "
                "and a timestamp would be silently truncated"
            )
        return value, source
    raise OrderingDateError(
        "the reading states none of the four dates, so there is nothing to "
        "order it by; a row without a date is not a ledger row"
    )


# ---------------------------------------------------------------------------
# The draft
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransactionDraft:
    """One row of one document, as read, before it is stored.

    Carries no ``proof_class``, ``ref_id`` or ``content_hash``, for the reason
    :class:`~services.financial.documents.SourceDocumentDraft` carries no proof
    class: each is derived, and a caller-supplied value is either an opinion or
    a reference that stops reproducing.

    ``ordering_date`` and ``ordering_date_source`` are optional *together*.
    Supplied, they are the format's own choice -- camt.053 defines that booking
    governs, and a general precedence must not overrule a format that says.
    Omitted, :func:`choose_ordering_date` picks by
    :data:`ORDERING_PRECEDENCE`.  One without the other is refused: a date with
    no named source cannot be audited, and a source with no date is a claim
    about a value that was never chosen.

    ``extraction_layer`` defaults to the document's.  Where a row states its
    own it may be *less* deterministic than the document's but never more: a
    single figure recovered by a model from an otherwise natively parsed file
    is layer 3 sitting in a layer 0 document, which is true and worth
    recording, whereas a row claiming a native read inside a model-read
    document claims a guarantee the file never offered.

    ``locator`` is required and has no default, for the reason
    :func:`services.financial.locators.capture` gives its ``space`` argument
    none: a default would be wrong exactly when a call site forgot to thread
    position data through, and silently.  A row with nothing to say about
    where it was read says so out loud with
    :attr:`~postgres.models.enums.LocatorKind.unlocated`, which keeps the
    count of unlocated rows a measure of reader failure rather than of
    forgotten parameters.  For the same reason ``provenance`` may not carry a
    ``"locator"`` key of its own: the writer serialises the field, and two
    statements of where a row came from is one more than can be true.
    """

    reading: RowReading
    row_index: int
    account_id: uuid.UUID
    locator: Locator
    statement_period_id: Optional[uuid.UUID] = None
    ordering_date: Optional[date] = None
    ordering_date_source: Optional[DateSource] = None
    extraction_layer: Optional[ExtractionLayer] = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.reading, RowReading):
            raise TransactionFieldError(
                f"reading must be a RowReading, got {type(self.reading).__name__}; "
                "the reading is what gets hashed, and a loose mapping would "
                "hash whatever keys it happened to have"
            )
        if isinstance(self.row_index, bool) or not isinstance(self.row_index, int):
            raise TransactionFieldError(
                f"row_index is {type(self.row_index).__name__}; it is the "
                "position in the document and orders rows that share a date"
            )
        if self.row_index < 0:
            raise TransactionFieldError(
                f"row_index is {self.row_index}; positions within a document "
                "start at zero"
            )
        if not isinstance(self.account_id, uuid.UUID):
            raise TransactionFieldError(
                f"account_id is {type(self.account_id).__name__}, not a UUID"
            )
        if not isinstance(self.locator, Locator):
            raise TransactionFieldError(
                f"locator must be a Locator, got {type(self.locator).__name__}; "
                "a row with nothing to say about where it was read says so "
                "with LocatorKind.unlocated rather than by leaving the field "
                "loose"
            )
        if self.statement_period_id is not None and not isinstance(
            self.statement_period_id, uuid.UUID
        ):
            raise TransactionFieldError(
                f"statement_period_id is {type(self.statement_period_id).__name__}, "
                "not a UUID or None"
            )

        stated_date = self.ordering_date is not None
        stated_source = self.ordering_date_source is not None
        if stated_date != stated_source:
            raise OrderingDateError(
                "ordering_date and ordering_date_source are supplied together "
                "or not at all; a date with no named source cannot be audited, "
                "and a source with no date names a choice nobody made"
            )
        if stated_date:
            if isinstance(self.ordering_date, datetime) or not isinstance(
                self.ordering_date, date
            ):
                raise OrderingDateError(
                    f"ordering_date is {type(self.ordering_date).__name__}; the "
                    "column is a DATE and a timestamp would be silently "
                    "truncated"
                )
            if not isinstance(self.ordering_date_source, DateSource):
                raise OrderingDateError(
                    "ordering_date_source must be a DateSource, got "
                    f"{type(self.ordering_date_source).__name__}"
                )
            # The named source must be a date the reading actually states, and
            # must be *that* date.  Otherwise a row can be ordered by a value
            # that appears nowhere in it while claiming a provenance for it,
            # and the column that exists to make the choice visible would
            # instead conceal it.
            attribute = dict(
                (source, name) for source, name in ORDERING_PRECEDENCE
            )[self.ordering_date_source]
            available = getattr(self.reading, attribute)
            if available is None:
                raise OrderingDateError(
                    f"ordering_date_source is {self.ordering_date_source.value} "
                    f"but the reading states no {attribute}; the source names "
                    "which of the four dates was chosen and cannot name an "
                    "absent one"
                )
            if available != self.ordering_date:
                raise OrderingDateError(
                    f"ordering_date is {self.ordering_date.isoformat()} but the "
                    f"reading's {attribute} is {available.isoformat()}; the "
                    "ordering date is one of the four dates, not a fifth"
                )

        if self.extraction_layer is not None and not isinstance(
            self.extraction_layer, ExtractionLayer
        ):
            raise TransactionFieldError(
                "extraction_layer must be an ExtractionLayer or None, got "
                f"{type(self.extraction_layer).__name__}; the column takes an "
                "integer, so a wrong integer is indistinguishable from a right "
                "one once stored"
            )

        for label, value in (
            ("provenance", self.provenance),
            ("metadata", self.metadata),
        ):
            if not isinstance(value, Mapping):
                raise TransactionFieldError(
                    f"{label} must be a mapping, got {type(value).__name__}"
                )
        if LOCATOR_PROVENANCE_KEY in self.provenance:
            raise TransactionFieldError(
                f"provenance already carries {LOCATOR_PROVENANCE_KEY!r}; the "
                "locator is the draft's own field and the writer serialises "
                "it, so a second copy here could only agree by luck or "
                "disagree in silence"
            )
        object.__setattr__(self, "provenance", dict(self.provenance))
        object.__setattr__(self, "metadata", dict(self.metadata))


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


def record_transactions(
    session: "Session",
    run: "IngestionRunHandle",
    document: FinancialSourceDocument,
    drafts: Sequence[TransactionDraft],
) -> list[FinancialTransaction]:
    """Write one document's ledger rows, attributed to ``run``.

    The whole document at once, because occurrence indices are counted across
    it: see the module docstring.  Passing a document's rows in two calls
    produces two rows that collide on
    ``uq_financial_transactions_document_content``, so the batch is the unit
    and a partial batch is a bug rather than an optimisation.

    An empty sequence writes nothing and returns an empty list.  A statement
    period with no movements in it is a real thing, and refusing it here would
    make the writer disagree with the arithmetic, which is content to reconcile
    an empty period against an unchanged balance.

    Rows are admitted, never quarantined, for the reason documents are:
    quarantine is a decision about a row that has been read, so it needs the
    row to exist, and :mod:`services.financial.quarantine` records who took it.

    Run counters are deliberately not incremented here.  The sibling writer
    does not touch them either, and a writer that counts plus a driver that
    counts is a run reporting twice what it ingested.  Counting belongs to
    whoever walks the documents.

    :raises RunScopeError: if the document, an account, or a period belongs to
        another case, or a period belongs to another document.
    :raises NonLedgerClassError: if the document's class may not yield rows.
    :raises TransactionFieldError: if two drafts claim one position.
    """
    if not isinstance(document, FinancialSourceDocument):
        raise TransactionFieldError(
            "document must be a FinancialSourceDocument, got "
            f"{type(document).__name__}"
        )
    if document.case_id != run.case_id:
        raise RunScopeError(
            f"source document {document.id} belongs to case "
            f"{document.case_id}, but this run is ingesting case {run.case_id}"
        )

    try:
        document_class = ProofClass(document.proof_class)
    except ValueError:
        raise NonLedgerClassError(
            f"source document {document.id} records proof class "
            f"{document.proof_class!r}, which is not a ProofClass member, so "
            "what its rows may claim cannot be determined"
        ) from None
    if not may_produce_ledger_rows(document_class):
        # p4 is corroboration: a document that supports a reading without
        # stating one.  ck_financial_transactions_no_p4 refuses these too, but
        # saying so here names the document rather than the column.
        raise NonLedgerClassError(
            f"source document {document.id} is {document_class.value}, which "
            "may not produce ledger rows at all; a corroborating document "
            "supports readings taken from elsewhere and states none of its own"
        )

    document_layer = ExtractionLayer(document.extraction_layer)

    if isinstance(drafts, (str, bytes)) or not isinstance(drafts, Sequence):
        raise TransactionFieldError(
            f"drafts must be a sequence, got {type(drafts).__name__}; the unit "
            "of this writer is the document's rows together"
        )
    if not drafts:
        return []

    positions: dict[int, int] = {}
    for offset, draft in enumerate(drafts):
        if not isinstance(draft, TransactionDraft):
            raise TransactionFieldError(
                f"drafts[{offset}] is {type(draft).__name__}, not a "
                "TransactionDraft"
            )
        first = positions.get(draft.row_index)
        if first is not None:
            # Two rows at one position order arbitrarily against each other,
            # and row_index exists precisely to break the tie between rows
            # sharing a date.
            raise TransactionFieldError(
                f"drafts[{offset}] and drafts[{first}] both claim row_index "
                f"{draft.row_index}; the position is what orders rows that "
                "share a date, and two rows cannot hold one position"
            )
        positions[draft.row_index] = offset

    accounts: dict[uuid.UUID, FinancialAccount] = {}
    periods: dict[uuid.UUID, FinancialStatementPeriod] = {}

    for offset, draft in enumerate(drafts):
        if draft.account_id not in accounts:
            account = session.get(FinancialAccount, draft.account_id)
            if account is None:
                raise RunScopeError(
                    f"drafts[{offset}] names account {draft.account_id}, which "
                    "does not exist; a ledger row cannot hang off an account "
                    "that was never recorded"
                )
            if account.case_id != run.case_id:
                raise RunScopeError(
                    f"drafts[{offset}] names account {draft.account_id}, which "
                    f"belongs to case {account.case_id}, but this run is "
                    f"ingesting case {run.case_id}"
                )
            accounts[draft.account_id] = account

        if draft.statement_period_id is None:
            continue
        if draft.statement_period_id not in periods:
            period = session.get(
                FinancialStatementPeriod, draft.statement_period_id
            )
            if period is None:
                raise RunScopeError(
                    f"drafts[{offset}] names statement period "
                    f"{draft.statement_period_id}, which does not exist"
                )
            if period.source_document_id != document.id:
                # The period is what a balance identity is checked over.  A row
                # filed under a period belonging to a different document would
                # be counted into that document's opening-to-closing
                # arithmetic, and the identity would fail on a page nobody
                # printed it on.
                raise RunScopeError(
                    f"drafts[{offset}] names statement period "
                    f"{draft.statement_period_id}, which belongs to source "
                    f"document {period.source_document_id} and not to "
                    f"{document.id}"
                )
            periods[draft.statement_period_id] = period
        period = periods[draft.statement_period_id]
        if period.account_id != draft.account_id:
            raise RunScopeError(
                f"drafts[{offset}] files a row for account {draft.account_id} "
                f"under a period covering account {period.account_id}; a row "
                "belongs to the period that reconciles the account it moved"
            )

    hashes = document_content_hashes([draft.reading for draft in drafts])

    rows: list[FinancialTransaction] = []
    for draft, content in zip(drafts, hashes):
        reading = draft.reading
        if draft.ordering_date is None:
            ordering_date, ordering_source = choose_ordering_date(reading)
        else:
            ordering_date = draft.ordering_date
            ordering_source = draft.ordering_date_source

        layer = document_layer if draft.extraction_layer is None else (
            draft.extraction_layer
        )
        if layer.value < document_layer.value:
            raise TransactionFieldError(
                f"row {draft.row_index} claims extraction layer {layer.value} "
                f"({layer.name}) inside a document read at layer "
                f"{document_layer.value} ({document_layer.name}); a row cannot "
                "have been read more natively than the file it came from"
            )

        row = FinancialTransaction(
            account_id=draft.account_id,
            source_document_id=document.id,
            statement_period_id=draft.statement_period_id,
            # Derived, never accepted. See the module docstring.
            ref_id=build_ref_id(document.sha256_at_ingestion, content),
            content_hash=content,
            row_index=draft.row_index,
            amount_minor=reading.amount_minor,
            # Validated rather than passed through: RowReading checks the shape
            # of the code, not that it is a currency anyone issues, and an
            # unrecognised code has no exponent to place a decimal point by.
            currency=get_currency(reading.currency).code,
            direction=reading.direction.value,
            running_balance_minor=reading.running_balance_minor,
            transaction_date=reading.transaction_date,
            posted_date=reading.posted_date,
            value_date=reading.value_date,
            effective_date=reading.effective_date,
            ordering_date=ordering_date,
            ordering_date_source=ordering_source.value,
            description=reading.description,
            counterparty_raw=reading.counterparty_raw,
            transaction_type=reading.transaction_type,
            bank_reference=reading.bank_reference,
            # The document's class, copied. See the module docstring for why
            # the copy exists and why it has to be maintained.
            proof_class=document_class.value,
            extraction_layer=layer.value,
            ledger_status="admitted",
            quarantine_reason=None,
            # The draft guarantees the key is free, so this cannot clobber.
            provenance={
                **draft.provenance,
                LOCATOR_PROVENANCE_KEY: draft.locator.to_json(),
            },
            metadata_=dict(draft.metadata),
        )
        run.stamp(row)
        rows.append(row)

    session.add_all(rows)
    # Flushed so that a constraint violation is raised here, where the drafts
    # that caused it are still in hand, rather than at some later commit.
    session.flush()
    return rows
