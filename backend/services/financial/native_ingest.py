"""Walk one natively-parsed document through the writers, in the one safe order.

This is the join between reading a file and storing it.  Everything above it is
pure -- :func:`~services.financial.native.read_native` parses, and
:func:`~services.financial.native_subjects.describe_subjects` says who the
document is about -- and everything below it writes.  Keeping the seam here
means a file can be read, described and shown to a reviewer before a single row
is stored, which is what the precheck dialog is for.

The order is not an implementation detail
-----------------------------------------

Document, then accounts, then periods, then rows.  A period references both an
account and a document, and a row references an account, a document and
sometimes a period, so each stage needs the one before it to have flushed.  The
writers each check that what they reference belongs to the run's case, and those
checks are the reason this order cannot be rearranged for convenience.

The reclassification comes last, after the rows exist, because it moves the
rows' proof class with the document's and cannot move rows that are not there.

What this module refuses to guess
---------------------------------

A row carries ``account_key``, and a subject carries the same key.  That join is
the whole attribution: get it wrong and transactions are written against an
account that does not exist, or against the wrong one, and nothing downstream
can detect either.  A row whose key matches no subject is refused here rather
than written with a guessed account or silently dropped.

The period link is narrower, and honestly so.  Where a document covers an
account over one span, its rows belong to that period and are linked to it --
and a file that carries the same statement twice still covers one span, so its
rows are linked too, the duplicate being written once.  Where a document covers
one account over *two* spans -- a combined camt.053 holding January and
February for one account -- the rows of both carry the same ``account_key`` and
nothing else, so which row belongs to which period is not recoverable from the
reading.  Both periods are still recorded, because both are real and both carry
their own printed balances; the rows are left unlinked and the reason is
written into the document's metadata.  Splitting them by date would be a rule
the file never stated, applied hardest at the period boundary, which is exactly
where a reconciliation is most likely to be contested.

The one thing a document may not do is cover one account over one span twice
and disagree about it.  The database stores one period per document, account
and span, so only one of the two claims could be kept, and keeping either would
put it on the record as though the document had made it alone.  That file is
refused whole.

What travels with a row, and why
--------------------------------

``is_reversal`` has no column on ``financial_transactions``, so it is written
into the row's metadata.  It is not decoration:
:func:`services.financial.linkage.classify` uses it to tell a reversal from an
identifier conflict, because a reversal legitimately carries the same reference
as the entry it reverses, in the same account, in the opposite direction --
the one arrangement that would otherwise be reported as a contradiction.  Dropped
here, the fact is not in the database at all and cannot be recovered without
re-parsing the file.

The locator travels as the draft's own field, and the transaction writer
serialises it into provenance under the key
:mod:`services.financial.table_geometry` already uses, so that one reader can
open a row's place in its source whatever produced the row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Mapping, Optional

from postgres.models.financial import (
    FinancialAccount,
    AdjudicationEvent,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from services.financial.accounts import record_account
from services.financial.documents import (
    SourceDocumentDraft,
    reclassify_after_reconciliation,
    record_source_document,
)
from services.financial.native import CenturyWindow, NativeReading
from services.financial.native_subjects import (
    AccountSubject,
    PeriodFacts,
    describe_subjects,
)
from services.financial.periods import StatementPeriodDraft, record_statement_period
from services.financial.transactions import TransactionDraft, record_transactions

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

    from services.financial.runs import IngestionRunHandle


#: Where the reader's admissibility reservations are kept on the document.
#: They are the reasons the file said it must not auto-admit whatever its
#: arithmetic shows, and :func:`reclassify_after_reconciliation` is given them
#: directly as well -- but that call decides a class and keeps no list, so
#: without this the *reasons* would not survive the ingestion that acted on
#: them, and a reviewer asking why a perfectly balanced document sits at p3
#: would have no answer on the record.
RESERVATIONS_METADATA_KEY = "admissibility_reservations"

#: Where a row's reversal flag is kept, there being no column for it.
REVERSAL_METADATA_KEY = "is_reversal"

#: Where the reason a document's rows carry no period link is kept.
AMBIGUOUS_PERIOD_METADATA_KEY = "unlinked_period_accounts"

#: A period's dates as the document stated them.  Both may be ``None``: that is
#: a real span -- the one nobody could read -- and the database has an index of
#: its own for it, so it is compared like any other rather than skipped.
_Bounds = tuple[Optional[date], Optional[date]]

#: One account's coverage over one span, which is what a document may state
#: only once.  These are the columns
#: ``uq_financial_statement_periods_document_account_period`` is built on,
#: minus the document, which is fixed for one ingestion.
_Span = tuple[Optional[str], Optional[date], Optional[date]]


class IngestionError(Exception):
    """Base for every refusal in this module."""


class UnattributableRowError(IngestionError):
    """A row names an account the document was not described as being about."""


class ContradictoryPeriodError(IngestionError):
    """One document covers one account's one span twice, and disagrees on it."""


@dataclass(frozen=True, slots=True)
class NativeIngestion:
    """Everything one document's ingestion created, and what it could not say.

    ``unlinked_rows`` is carried rather than left to be counted off the rows,
    for the reason :class:`~services.financial.runs.RunCounts` is recorded
    rather than recomputed: it is a statement about this ingestion, and counting
    the rows later answers a different question once adjudication has moved
    them.
    """

    document: FinancialSourceDocument
    accounts: tuple[FinancialAccount, ...]
    periods: tuple[FinancialStatementPeriod, ...]
    transactions: tuple[FinancialTransaction, ...]
    adjudication: Optional[AdjudicationEvent] = None
    unlinked_rows: int = 0

    @property
    def row_count(self) -> int:
        return len(self.transactions)


def ingest_native_reading(
    session: "Session",
    run: "IngestionRunHandle",
    reading: NativeReading,
    *,
    evidence_file_id: uuid.UUID,
    sha256: str,
    window: CenturyWindow,
    document_type: Optional[str] = None,
    institution_name: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> NativeIngestion:
    """Store one natively-read document: its accounts, periods and rows.

    ``sha256`` is both the document's recorded hash and the distinguisher
    :func:`describe_subjects` needs.  Using one value for both is deliberate:
    the distinguisher has to be stable across re-reads of one file and distinct
    between two files, which is what a content hash is, and taking it from the
    same place the document records means the two cannot drift apart.

    ``document_type`` defaults to the format's own name.  A caller who knows
    better -- a bank that ships camt.053 inside something it calls a statement
    export -- may say so, and nothing here second-guesses it.

    ``institution_name`` is taken from the accounts the document names when the
    caller does not supply one and they agree on it.  Where they disagree it is
    left unset rather than resolved: a document naming two institutions has not
    told us which one issued it, and picking the first would be a guess with a
    bank's name on it.

    :raises IngestionError: if the arguments do not describe a document.
    :raises UnattributableRowError: if a row names an account no subject covers.
    :raises ContradictoryPeriodError: if the document covers one account over
        one span twice and states different figures each time.
    :raises SubjectError: if the document cannot be described at all.
    """
    if not isinstance(reading, NativeReading):
        raise IngestionError(
            f"reading must be a NativeReading, got {type(reading).__name__}; "
            "this writes what a parser read and cannot take a loose mapping"
        )
    if not isinstance(sha256, str) or not sha256.strip():
        raise IngestionError(
            "sha256 is required: it is both what the document records as its "
            "hash and what distinguishes this document's unnamed accounts from "
            "every other document's"
        )

    subjects = describe_subjects(reading, window=window, distinguisher=sha256)
    ambiguous = _ambiguous_keys(subjects)

    document = record_source_document(
        session,
        run,
        SourceDocumentDraft(
            evidence_file_id=evidence_file_id,
            sha256_at_ingestion=sha256,
            document_type=document_type or reading.format.value,
            shape=reading.source_shape,
            extraction_layer=reading.extraction_layer,
            parser_name=reading.parser_name,
            parser_version=reading.parser_version,
            institution_name=institution_name or _agreed_institution(subjects),
            currency=_agreed_currency(subjects),
            metadata=_document_metadata(reading, ambiguous, metadata),
        ),
    )
    run.document_seen()

    accounts = _record_accounts(session, run, subjects)
    periods, linkable = _record_periods(
        session, run, document, subjects, accounts, ambiguous
    )

    drafts = _transaction_drafts(reading, accounts, linkable)
    transactions = record_transactions(session, run, document, drafts)
    run.transaction_admitted(len(transactions))

    # Rows left unlinked because their account has two periods here, not rows
    # of a format that states no period at all.  NACHA's rows are every one of
    # them period-less and none of them is a loss: the file states no period,
    # so there is nothing they failed to be linked to.
    unlinked = sum(1 for row in reading.rows if row.account_key in ambiguous)

    adjudication = reclassify_after_reconciliation(
        session,
        document,
        reading.reconciliation_status,
        run=run,
        reservations=reading.admissibility_reservations,
    )

    return NativeIngestion(
        document=document,
        accounts=tuple(dict.fromkeys(accounts.values())),
        periods=tuple(periods),
        transactions=tuple(transactions),
        adjudication=adjudication,
        unlinked_rows=unlinked,
    )


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def _record_accounts(
    session: "Session",
    run: "IngestionRunHandle",
    subjects: tuple[AccountSubject, ...],
) -> dict[Optional[str], FinancialAccount]:
    """Each subject's account, keyed by the key its rows carry.

    Two subjects sharing a key reach one account, because
    :func:`~services.financial.accounts.record_account` gets or creates and the
    second statement for an account must reach the first statement's row.  The
    mapping therefore holds one entry per key, not one per subject.
    """
    accounts: dict[Optional[str], FinancialAccount] = {}
    for subject in subjects:
        account = record_account(session, run, subject.draft)
        accounts.setdefault(subject.account_key, account)
    return accounts


def _record_periods(
    session: "Session",
    run: "IngestionRunHandle",
    document: FinancialSourceDocument,
    subjects: tuple[AccountSubject, ...],
    accounts: Mapping[Optional[str], FinancialAccount],
    ambiguous: frozenset[Optional[str]],
) -> tuple[list[FinancialStatementPeriod], dict[Optional[str], uuid.UUID]]:
    """Every period the document states, and the ones rows may be linked to.

    A span stated twice is written once.  One document covers one account's one
    span once -- that is what
    ``uq_financial_statement_periods_document_account_period`` says, and its
    partner index says the same for the span nobody could read -- so a file
    carrying a statement twice must not be turned into two rows that the
    database would refuse anyway.  Collapsing them here means the refusal a
    caller sees for a genuinely contradictory file is this module's, naming the
    account and the span, rather than an integrity error naming a constraint.

    Where two statements share a span but disagree about it, nothing is
    written.  Only one of the two can be stored, and storing either would put
    one of a document's two contradictory claims on the record as though the
    document had made it alone.

    The second return value is deliberately smaller than the first.  An account
    the document covers over one span maps to that period; an account it covers
    over two maps to nothing, because the rows of both statements are
    indistinguishable and linking them all to either period would put one
    statement's movements inside the other's balances -- an error the balance
    identity would then report as a failure of the document rather than of this
    function.
    """
    periods: list[FinancialStatementPeriod] = []
    stated: dict[_Span, PeriodFacts] = {}
    written: dict[_Span, FinancialStatementPeriod] = {}

    for subject in subjects:
        facts = subject.period
        if facts is None:
            continue

        span: _Span = (subject.account_key, facts.bounds.start, facts.bounds.end)
        already = stated.get(span)
        if already is not None:
            if already != facts:
                raise ContradictoryPeriodError(
                    f"this document covers account {subject.account_key!r} over "
                    f"{_describe_span(span)} twice and states different figures "
                    "each time; only one period can be stored for a document "
                    "and an account over one span, and storing either of two "
                    "contradictory claims would record it as the document's "
                    "only claim"
                )
            continue

        stated[span] = facts
        account = accounts[subject.account_key]
        period = record_statement_period(
            session,
            run,
            StatementPeriodDraft(
                account_id=account.id,
                source_document_id=document.id,
                currency=facts.currency,
                bounds=facts.bounds,
                opening=facts.opening,
                closing=facts.closing,
            ),
        )
        periods.append(period)
        written[span] = period

    linkable: dict[Optional[str], uuid.UUID] = {}
    for (account_key, _start, _end), period in written.items():
        if account_key not in ambiguous:
            linkable[account_key] = period.id

    return periods, linkable


def _transaction_drafts(
    reading: NativeReading,
    accounts: Mapping[Optional[str], FinancialAccount],
    linkable: Mapping[Optional[str], uuid.UUID],
) -> list[TransactionDraft]:
    """The reading's rows as drafts, each attributed to its subject's account.

    ``row_index`` is the parser's, not this function's.  Renumbering would
    change every row's content hash and so its identity, which is the one thing
    a re-ingestion of an unchanged file must not do.
    """
    drafts: list[TransactionDraft] = []

    for row in reading.rows:
        account = accounts.get(row.account_key)
        if account is None:
            raise UnattributableRowError(
                f"row {row.row_index} names account key {row.account_key!r}, "
                "which no subject of this document covers; writing it would "
                "either invent an account or put these movements on another, "
                "and nothing downstream could detect either"
            )
        drafts.append(
            TransactionDraft(
                reading=row.reading,
                row_index=row.row_index,
                account_id=account.id,
                locator=row.locator,
                statement_period_id=linkable.get(row.account_key),
                ordering_date=row.ordering_date,
                ordering_date_source=row.ordering_date_source,
                metadata={REVERSAL_METADATA_KEY: row.is_reversal},
            )
        )
    return drafts


# ---------------------------------------------------------------------------
# Document metadata
# ---------------------------------------------------------------------------


def _document_metadata(
    reading: NativeReading,
    ambiguous: frozenset[Optional[str]],
    supplied: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    """The caller's metadata, plus what this ingestion learned about the file.

    The reservations are written even when empty, so that a document read by a
    parser that raises them and a document read before parsers raised them at
    all are distinguishable: an absent key means nobody asked, and an empty list
    means somebody asked and found none.

    The ambiguous keys are stringified only here.  They are compared as read
    everywhere else, because an unnamed account's key is ``None`` and the string
    ``"None"`` is a key a document could genuinely print.
    """
    metadata: dict[str, Any] = dict(supplied or {})
    metadata[RESERVATIONS_METADATA_KEY] = list(reading.admissibility_reservations)

    if ambiguous:
        metadata[AMBIGUOUS_PERIOD_METADATA_KEY] = sorted(
            "" if key is None else key for key in ambiguous
        )

    return metadata


def _ambiguous_keys(
    subjects: tuple[AccountSubject, ...],
) -> frozenset[Optional[str]]:
    """Account keys this document covers over more than one span.

    Spans, not statements.  A file carrying one statement twice states one
    period about that account and its rows all sit inside it; a file carrying
    January and February states two, and which of them a row belongs to is not
    in the reading.  Only the second is ambiguous, and counting statements
    would call both so.

    This set is what goes on the document as a reason, what decides which
    accounts' rows may be linked, and what counts the rows that went unlinked.
    Deriving all three from one place means the count, the linkage and the
    explanation cannot disagree.
    """
    spans: dict[Optional[str], set[_Bounds]] = {}
    for subject in subjects:
        if subject.period is not None:
            spans.setdefault(subject.account_key, set()).add(
                (subject.period.bounds.start, subject.period.bounds.end)
            )
    return frozenset(key for key, found in spans.items() if len(found) > 1)


def _describe_span(span: _Span) -> str:
    """A span as a person reads it, including the one nobody could read."""
    _key, start, end = span
    if start is None and end is None:
        return "a span whose dates the file did not state"
    return f"{start or 'an unstated start'}..{end or 'an unstated end'}"


def _agreed_institution(subjects: tuple[AccountSubject, ...]) -> Optional[str]:
    """The institution every named account agrees on, or ``None``."""
    return _unanimous(
        subject.draft.institution_name for subject in subjects
    )


def _agreed_currency(subjects: tuple[AccountSubject, ...]) -> Optional[str]:
    """The currency every account agrees on, or ``None``.

    A document holding two currencies has no single currency, and recording one
    of them would make a reader believe the other's totals were denominated in
    it.
    """
    return _unanimous(subject.draft.currency for subject in subjects)


def _unanimous(values: Any) -> Optional[str]:
    found = {value for value in values if value}
    return found.pop() if len(found) == 1 else None
