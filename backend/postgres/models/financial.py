"""The financial ledger: the relational system of record for money evidence.

Six tables, in dependency order: ingestion runs, source documents, accounts,
statement periods, transactions, and adjudications.

Three rules govern the whole schema and explain most of its shape.

*Nothing here is a float.*  Every monetary value is a ``BigInteger`` count of
minor units alongside an ISO 4217 code.  The service layer is what pairs the
two back into ``services.financial.money.Money``; persistence does not import
services, so the column names carry the ``_minor`` suffix as the reminder.  A
float would make the balance identity approximate, and an approximate identity
detects nothing.

*Magnitude and sign are separate.*  ``amount_minor`` is a non-negative
magnitude and ``direction`` carries credit or debit.  A sign error is then a
wrong value in a two-valued column rather than a silently negated number, so
it fails a check constraint instead of quietly halving a total.

*Rows are corrected by supersession, not by mutation.*  A fact that turns out
to be wrong keeps its row, gains ``superseded_by_id``, and moves to the
``superseded`` status while its replacement is inserted.  The database cannot
enforce this on its own — the cascades below exist so that deleting a case
still works — so it is enforced in the service layer, and the adjudication
table is what makes a breach visible: any change to an admitted fact that has
no adjudication row explaining it is a defect.

Deletion semantics are deliberately blunt: every table cascades from the case,
and each internal parent link cascades too, because a case deletion that half
succeeds would leave orphaned money.  Immutability is a service-layer promise
recorded in adjudications; it is not a storage-layer one, and this docstring
says so rather than letting the schema imply a guarantee it does not give.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


def _jsonb_column():
    return JSONB().with_variant(JSON(), "sqlite")


# Vocabularies are enforced as check constraints rather than native Postgres
# enum types, matching evidence_files and cases.  The Python enums in
# postgres.models.enums remain the single source of truth for the values; these
# strings exist so a migration can spell the constraint out.
_PROOF_CLASSES = "('p0', 'p1', 'p2', 'p3', 'p4')"
_LEDGER_STATUSES = "('admitted', 'quarantined', 'superseded', 'rejected')"
_DOCUMENT_STATUSES = _LEDGER_STATUSES
_RUN_STATUSES = "('pending', 'running', 'completed', 'failed', 'aborted')"
_RECONCILIATION_STATUSES = (
    "('not_attempted', 'balanced', 'unbalanced', 'unavailable')"
)
_DIRECTIONS = "('credit', 'debit')"
_DATE_SOURCES = "('transaction', 'posted', 'value', 'effective')"
_BALANCE_SOURCES = "('printed', 'carried_forward', 'absent')"
_PERIOD_BOUNDS_SOURCES = "('printed', 'derived', 'absent')"
# 'evidence_file' is not a financial table, and it is here because the
# decision to route a file away from this subsystem is taken before any
# financial row exists to record it against.  The list is what makes this
# ledger polymorphic in practice; subject_id has never carried a foreign key.
_ADJUDICATION_SUBJECTS = (
    "('transaction', 'statement_period', 'source_document', 'account', "
    "'evidence_file')"
)
# Closed for the reason the quarantine reasons are closed: "how many rows did
# you set aside, and how many did you put back" is answered by a GROUP BY, and
# free text answers it wrongly as many times as there are spellings.  Every
# disposition here has its reversal in the same vocabulary, because the ledger
# appends: undoing a supersession writes the undo, it does not retract the
# original.  'reclassify_document' is the exception to both halves of that: it
# is written by the reconciliation stage rather than by a person, and it is its
# own reversal, because it carries the class before and the class after.
# 'admit_financial_document' has no reversal either, for the reason
# 'explain_balance_failure' has none: it changes no stored column, so there is
# nothing an undo could restore.  Read its name with care -- it records a
# financial document admitted *out* to general document processing, not one
# admitted into this ledger.  See postgres.models.enums.AdjudicationDecision.
_ADJUDICATION_DECISIONS = (
    "('supersede_duplicate', 'restore_document', 'purge_duplicate', "
    "'quarantine_row', 'release_row', 'explain_balance_failure', "
    "'reclassify_document', 'admit_financial_document', 'correct_transaction', 'set_account_party')"
)
_QUARANTINE_REASONS = (
    "('balance_break', 'unreadable_row', 'currency_mismatch', "
    "'unexplained_delta', 'adjudicated')"
)

# A reason must contain something that is not whitespace.
#
# ``trim()`` alone is not enough: in both Postgres and SQLite it strips spaces
# only, so a reason consisting of a tab and a newline passes a naive
# ``length(trim(reason)) > 0`` and an unexplained edit gets recorded as an
# explained one.  Postgres spells the multi-character form ``btrim(x, chars)``
# and SQLite spells it ``trim(x, chars)``, so neither is portable; nested
# ``replace()`` behaves identically in both.
#
# The literals below hold real tab, carriage return and newline characters.
# They are written as Python escapes so the source stays readable, and they
# must reach the SQL as the characters themselves: Postgres runs with
# standard_conforming_strings on, where a backslash in a string literal is a
# backslash, so an escaped form would silently check for the wrong thing.
_REASON_NOT_BLANK = (
    "length(trim(replace(replace(replace("
    "reason, '\t', ' '), '\r', ' '), '\n', ' '))) > 0"
)


class FinancialIngestionRun(Base, TimestampMixin):
    """One execution of the financial ingestion pipeline.

    Every fact in the ledger names the run that produced it, so that a later
    question — which build of the parser read this statement, under what
    configuration — has an answer that does not depend on anyone's memory.
    The recorded counts are the outcome as it stood when the run finished;
    they are not recomputed, because recomputing them against a ledger that
    has since been adjudicated would answer a different question.
    """

    __tablename__ = "financial_ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN {_RUN_STATUSES}",
            name="ck_financial_ingestion_runs_status",
        ),
        Index("ix_financial_ingestion_runs_case", "case_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )

    # Identity of the code and rules that ran.  Without these a result is not
    # reproducible, and an expert cannot say what produced it.
    code_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ruleset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config: Mapped[dict] = mapped_column(
        _jsonb_column(), nullable=False, default=dict, server_default="{}"
    )

    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Captured at the time so the trail survives the user record being removed.
    started_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    documents_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    transactions_admitted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    transactions_quarantined: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    case = relationship("Case", foreign_keys=[case_id])
    started_by = relationship("User", foreign_keys=[started_by_user_id])


class FinancialSourceDocument(Base, TimestampMixin):
    """A document admitted to the financial pipeline, and how it was read.

    This does not duplicate ``evidence_files``; it points at one and records
    what the financial reader made of it.  The exception is ``sha256_at_ingestion``,
    which is deliberately a second copy: if the evidence file's hash ever
    diverges from the hash the ledger was built on, the ledger's provenance is
    broken, and only holding both makes that detectable.
    """

    __tablename__ = "financial_source_documents"
    __table_args__ = (
        CheckConstraint(
            f"proof_class IN {_PROOF_CLASSES}",
            name="ck_financial_source_documents_proof_class",
        ),
        CheckConstraint(
            f"status IN {_DOCUMENT_STATUSES}",
            name="ck_financial_source_documents_status",
        ),
        CheckConstraint(
            f"quarantine_reason IS NULL OR quarantine_reason IN "
            f"{_QUARANTINE_REASONS}",
            name="ck_financial_source_documents_quarantine_reason",
        ),
        # A reason and a status that disagree make the column evidence of
        # nothing: a document set aside with no recorded basis cannot be
        # reviewed, and a reason left behind after a release describes a
        # decision that has been reversed.
        CheckConstraint(
            "(quarantine_reason IS NOT NULL) = (status = 'quarantined')",
            name="ck_financial_source_documents_quarantine_coherent",
        ),
        CheckConstraint(
            "extraction_layer BETWEEN 0 AND 4",
            name="ck_financial_source_documents_extraction_layer",
        ),
        UniqueConstraint(
            "ingestion_run_id",
            "evidence_file_id",
            name="uq_financial_source_documents_run_file",
        ),
        CheckConstraint(
            "duplicate_match_rung IS NULL OR duplicate_match_rung BETWEEN 0 AND 2",
            name="ck_financial_source_documents_duplicate_rung",
        ),
        # A rung is a statement about how a document matched its group, so it
        # is meaningless without one.  Allowing a rung to stand alone would
        # let a document claim it had been shown to duplicate something
        # without recording what.
        CheckConstraint(
            "duplicate_match_rung IS NULL OR duplicate_group_key IS NOT NULL",
            name="ck_financial_source_documents_rung_needs_group",
        ),
        Index("ix_financial_source_documents_case", "case_id"),
        Index("ix_financial_source_documents_evidence_file", "evidence_file_id"),
        Index(
            "ix_financial_source_documents_case_status", "case_id", "status"
        ),
        # Duplicate resolution runs within one case and only within one case,
        # so this is the index that supports it.
        Index(
            "ix_financial_source_documents_case_duplicate_group",
            "case_id",
            "duplicate_group_key",
        ),
        # The same key without the case, which is a different question with a
        # different answer: has this statement been seen in another matter?
        # That is worth being able to ask and must never drive an exclusion,
        # so it gets an index of its own rather than sharing the one above.
        Index(
            "ix_financial_source_documents_duplicate_group",
            "duplicate_group_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    sha256_at_ingestion: Mapped[str] = mapped_column(String(64), nullable=False)

    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    proof_class: Mapped[str] = mapped_column(String(2), nullable=False)

    # 0 native structured parse, 1 template match, 2 structural OCR plus model
    # interpretation, 3 model with retrieval grounding.  Decreasing determinism;
    # layer 3 is a marked fallback, not a normal path.
    extraction_layer: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)

    institution_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="admitted", server_default="admitted"
    )
    quarantine_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_source_documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Duplicate detection.  Both fingerprints are computed from what the
    # document was read to say, never from the case it happens to sit in, so
    # the same statement filed in two matters produces the same key in both.
    # That is deliberate: seeing it is useful, and acting on it is not
    # permitted.  Every query that changes a status filters on case_id;
    # nothing outside the case is ever superseded.
    #
    # content_fingerprint covers the reading — accounts, period bounds and the
    # transaction rows.  duplicate_group_key covers only the accounts and
    # bounds, so it is the coarser of the two and is what groups candidates
    # together; documents agreeing on the finer fingerprint necessarily agree
    # on the coarser one, which is what makes a single group key sufficient.
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duplicate_group_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duplicate_match_rung: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Set when a person needs to look, which is not the same as being excluded.
    # A weak match is flagged and left admitted; a strong one is excluded and
    # still flagged, because an automatic exclusion nobody reviews is just a
    # quiet deletion.
    duplicate_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    metadata_: Mapped[dict] = mapped_column(
        "metadata", _jsonb_column(), nullable=False, default=dict, server_default="{}"
    )

    case = relationship("Case", foreign_keys=[case_id])
    evidence_file = relationship("EvidenceFile", foreign_keys=[evidence_file_id])
    ingestion_run = relationship(
        "FinancialIngestionRun", foreign_keys=[ingestion_run_id]
    )
    superseded_by = relationship(
        "FinancialSourceDocument", remote_side=[id], foreign_keys=[superseded_by_id]
    )


class FinancialAccount(Base, TimestampMixin):
    """An account as it appears across the case's financial documents.

    ``identity_key`` is a deterministic fingerprint computed by the service
    layer from whichever identifiers a document actually carried.  It exists
    because uniqueness over nullable columns is not uniqueness in Postgres,
    and because deciding that two differently-printed accounts are the same
    account is a judgement that must be made once, in code that can be tested,
    rather than implicitly in every query that joins on a masked number.

    Full identifiers are stored as printed.  Masking is a presentation
    concern, not a storage one: an investigation that cannot see the number it
    was given cannot check it.
    """

    __tablename__ = "financial_accounts"
    __table_args__ = (
        UniqueConstraint(
            "case_id", "identity_key", name="uq_financial_accounts_case_identity"
        ),
        Index("ix_financial_accounts_case", "case_id"),
        Index("ix_financial_accounts_normalised", "case_id", "identifier_normalised"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )

    identity_key: Mapped[str] = mapped_column(String(512), nullable=False)

    institution_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    identifier_as_printed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Digits only, for joining across documents that print the same account
    # with different punctuation or masking.
    identifier_normalised: Mapped[str | None] = mapped_column(String(128), nullable=True)

    account_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    holder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    # Structured identifiers, kept separate so their check digits can be
    # verified as fields rather than parsed back out of free text.
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    routing_number: Mapped[str | None] = mapped_column(String(9), nullable=True)

    first_seen_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_ingestion_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    metadata_: Mapped[dict] = mapped_column(
        "metadata", _jsonb_column(), nullable=False, default=dict, server_default="{}"
    )

    case = relationship("Case", foreign_keys=[case_id])
    first_seen_run = relationship(
        "FinancialIngestionRun", foreign_keys=[first_seen_run_id]
    )


class FinancialStatementPeriod(Base, TimestampMixin):
    """One account's coverage by one document, and the arithmetic over it.

    The balance identity is
    ``opening + sum(credits) - sum(debits) == closing``
    evaluated entirely in minor units.  Its result lives here rather than
    being recomputed on read, because the answer is evidence: it was true of a
    particular set of rows at a particular time, and a later recomputation
    over an adjudicated ledger is a different assertion.

    ``delta_minor`` is signed — computed closing minus printed closing — and is
    the input to delta localisation, which asks whether the gap equals one
    row's amount, twice a row's amount, or a round number.

    Four values here are each paired with a column saying where they came
    from, because in every case an absence and a measurement would otherwise
    be indistinguishable.  A missing balance is not a zero balance.  A period
    end derived from the last transaction on the page is not a period end
    printed on the statement, and only the printed one can support the claim
    that a neighbouring statement is missing.  An opening balance carried
    forward from the previous period names the period it came from, because
    the balance identity is then no longer an independent check of these rows
    — it is partly a restatement of the ones next door, and a reader is
    entitled to see that.

    The ``carried_from`` links carry no matching check constraint tying them
    to their source column.  One would be correct at write time and could then
    be falsified by a legitimate cascade: deleting the referenced period sets
    the link null, which would leave a surviving row failing a constraint and
    a case deletion unable to complete.  A constraint that blocks a delete is
    worse than one enforced where it can actually be maintained, so the rule
    lives in ``services.financial.periods`` and this docstring says so.
    """

    __tablename__ = "financial_statement_periods"
    __table_args__ = (
        CheckConstraint(
            f"reconciliation_status IN {_RECONCILIATION_STATUSES}",
            name="ck_financial_statement_periods_reconciliation_status",
        ),
        CheckConstraint(
            f"opening_balance_source IN {_BALANCE_SOURCES}",
            name="ck_financial_statement_periods_opening_source",
        ),
        CheckConstraint(
            f"closing_balance_source IN {_BALANCE_SOURCES}",
            name="ck_financial_statement_periods_closing_source",
        ),
        CheckConstraint(
            f"period_start_source IN {_PERIOD_BOUNDS_SOURCES}",
            name="ck_financial_statement_periods_start_source",
        ),
        CheckConstraint(
            f"period_end_source IN {_PERIOD_BOUNDS_SOURCES}",
            name="ck_financial_statement_periods_end_source",
        ),
        CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR period_start <= period_end",
            name="ck_financial_statement_periods_ordered",
        ),
        # A value and its source must agree about whether the value exists.
        # Without these a row may say a balance is absent while carrying one,
        # or say it was printed while carrying nothing, and either way the
        # source column stops being evidence of anything.  Comparing the two
        # booleans is portable and, unlike a truthiness test, admits a zero
        # balance as the real balance it is.
        CheckConstraint(
            "(opening_balance_source = 'absent') = (opening_balance_minor IS NULL)",
            name="ck_financial_statement_periods_opening_coherent",
        ),
        CheckConstraint(
            "(closing_balance_source = 'absent') = (closing_balance_minor IS NULL)",
            name="ck_financial_statement_periods_closing_coherent",
        ),
        CheckConstraint(
            "(period_start_source = 'absent') = (period_start IS NULL)",
            name="ck_financial_statement_periods_start_coherent",
        ),
        CheckConstraint(
            "(period_end_source = 'absent') = (period_end IS NULL)",
            name="ck_financial_statement_periods_end_coherent",
        ),
        UniqueConstraint(
            "source_document_id",
            "account_id",
            "period_start",
            "period_end",
            name="uq_financial_statement_periods_document_account_period",
        ),
        # The constraint above does not cover the case it most needs to.  Both
        # Postgres and SQLite treat nulls as distinct inside a unique
        # constraint, so a statement whose dates could not be read admits
        # unlimited duplicate periods for the same account on the same
        # document — precisely the document that is hardest to check by eye.
        # One document covers one account once, whether or not anyone could
        # read the dates, so the undated case gets an index of its own.
        Index(
            "uq_financial_statement_periods_document_account_undated",
            "source_document_id",
            "account_id",
            unique=True,
            postgresql_where=text(
                "period_start IS NULL AND period_end IS NULL"
            ),
            sqlite_where=text("period_start IS NULL AND period_end IS NULL"),
        ),
        Index("ix_financial_statement_periods_case", "case_id"),
        Index(
            "ix_financial_statement_periods_account_span",
            "account_id",
            "period_start",
            "period_end",
        ),
        Index(
            "ix_financial_statement_periods_status",
            "case_id",
            "reconciliation_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_start_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="absent", server_default="absent"
    )
    period_end_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="absent", server_default="absent"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    opening_balance_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    closing_balance_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    opening_balance_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="absent", server_default="absent"
    )
    closing_balance_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="absent", server_default="absent"
    )
    # Set only where the matching source is 'carried_forward'.  See the class
    # docstring for why this is a service-layer rule rather than a constraint.
    opening_carried_from_period_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_statement_periods.id", ondelete="SET NULL"),
        nullable=True,
    )
    closing_carried_from_period_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_statement_periods.id", ondelete="SET NULL"),
        nullable=True,
    )

    reconciliation_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="not_attempted",
        server_default="not_attempted",
    )
    computed_closing_minor: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    delta_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    credit_total_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    debit_total_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    transaction_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Output of delta localisation: the candidate explanations, each naming the
    # rows that would account for the gap.  Never a conclusion on its own.
    delta_explanation: Mapped[dict | None] = mapped_column(
        _jsonb_column(), nullable=True
    )

    case = relationship("Case", foreign_keys=[case_id])
    source_document = relationship(
        "FinancialSourceDocument", foreign_keys=[source_document_id]
    )
    account = relationship("FinancialAccount", foreign_keys=[account_id])
    ingestion_run = relationship(
        "FinancialIngestionRun", foreign_keys=[ingestion_run_id]
    )
    opening_carried_from = relationship(
        "FinancialStatementPeriod",
        remote_side=[id],
        foreign_keys=[opening_carried_from_period_id],
    )
    closing_carried_from = relationship(
        "FinancialStatementPeriod",
        remote_side=[id],
        foreign_keys=[closing_carried_from_period_id],
    )


class FinancialTransaction(Base, TimestampMixin):
    """A single ledger row: the atom the whole feature exists to get right.

    Four date columns are kept because statements genuinely carry up to four
    different dates for one movement and collapsing them loses the difference
    that matters — a transaction dated the 30th and posted the 2nd sits in
    whichever month the question is about.  All four are nullable because no
    single one is always printed, and a check constraint requires at least one.
    ``ordering_date`` is the date chosen for sequencing and
    ``ordering_date_source`` records which of the four it came from, so the
    choice is visible rather than buried in a query.

    ``content_hash`` fingerprints the normalised field set so that re-reading
    the same document twice produces the same row rather than a duplicate.
    """

    __tablename__ = "financial_transactions"
    __table_args__ = (
        CheckConstraint(
            "amount_minor >= 0", name="ck_financial_transactions_amount_non_negative"
        ),
        CheckConstraint(
            f"direction IN {_DIRECTIONS}",
            name="ck_financial_transactions_direction",
        ),
        CheckConstraint(
            f"proof_class IN {_PROOF_CLASSES}",
            name="ck_financial_transactions_proof_class",
        ),
        # p4 is corroboration only.  It never reaches this table; the
        # constraint is what makes that a guarantee rather than an intention.
        CheckConstraint(
            "proof_class <> 'p4'", name="ck_financial_transactions_no_p4"
        ),
        CheckConstraint(
            f"ledger_status IN {_LEDGER_STATUSES}",
            name="ck_financial_transactions_ledger_status",
        ),
        CheckConstraint(
            f"quarantine_reason IS NULL OR quarantine_reason IN "
            f"{_QUARANTINE_REASONS}",
            name="ck_financial_transactions_quarantine_reason",
        ),
        # Quarantine removes a row from every total.  Doing that without a
        # recorded basis is the failure mode the closed vocabulary exists to
        # prevent, so the two columns are held to agree in the database and
        # not only in services.financial.quarantine.
        CheckConstraint(
            "(quarantine_reason IS NOT NULL) = (ledger_status = 'quarantined')",
            name="ck_financial_transactions_quarantine_coherent",
        ),
        CheckConstraint(
            f"ordering_date_source IN {_DATE_SOURCES}",
            name="ck_financial_transactions_ordering_date_source",
        ),
        CheckConstraint(
            "transaction_date IS NOT NULL OR posted_date IS NOT NULL "
            "OR value_date IS NOT NULL OR effective_date IS NOT NULL",
            name="ck_financial_transactions_has_a_date",
        ),
        CheckConstraint(
            "extraction_layer BETWEEN 0 AND 4",
            name="ck_financial_transactions_extraction_layer",
        ),
        UniqueConstraint(
            "case_id", "ref_id", name="uq_financial_transactions_case_ref"
        ),
        UniqueConstraint(
            "source_document_id",
            "content_hash",
            name="uq_financial_transactions_document_content",
        ),
        Index(
            "ix_financial_transactions_period_order",
            "statement_period_id",
            "ordering_date",
            "row_index",
        ),
        Index(
            "ix_financial_transactions_account_date",
            "account_id",
            "ordering_date",
        ),
        Index(
            "ix_financial_transactions_case_status",
            "case_id",
            "ledger_status",
        ),
        Index("ix_financial_transactions_run", "ingestion_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Null for sources that carry no statement period at all, such as a raw
    # payment file.  Such rows cannot participate in a balance identity, and
    # that absence is exactly what the null records.
    statement_period_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_statement_periods.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Stable exhibit reference, cited in reports and regenerated identically.
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Position within the source document, so ordering is total and stable
    # even where several rows share a date.
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)

    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    direction: Mapped[str] = mapped_column(String(6), nullable=False)
    # The balance printed beside the row, where one is printed.  A second,
    # independent check on the arithmetic.
    running_balance_minor: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    posted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ordering_date: Mapped[date] = mapped_column(Date, nullable=False)
    ordering_date_source: Mapped[str] = mapped_column(String(16), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    counterparty_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    proof_class: Mapped[str] = mapped_column(String(2), nullable=False)
    extraction_layer: Mapped[int] = mapped_column(Integer, nullable=False)

    ledger_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="admitted", server_default="admitted"
    )
    quarantine_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Where on the page this came from: page number, normalised bounding box,
    # and the raw text the value was read from.  Formalised alongside the
    # click-through-to-source work; held as a document here so that the shape
    # can settle without a migration per field.
    provenance: Mapped[dict] = mapped_column(
        _jsonb_column(), nullable=False, default=dict, server_default="{}"
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", _jsonb_column(), nullable=False, default=dict, server_default="{}"
    )

    case = relationship("Case", foreign_keys=[case_id])
    account = relationship("FinancialAccount", foreign_keys=[account_id])
    source_document = relationship(
        "FinancialSourceDocument", foreign_keys=[source_document_id]
    )
    statement_period = relationship(
        "FinancialStatementPeriod", foreign_keys=[statement_period_id]
    )
    ingestion_run = relationship(
        "FinancialIngestionRun", foreign_keys=[ingestion_run_id]
    )
    superseded_by = relationship(
        "FinancialTransaction", remote_side=[id], foreign_keys=[superseded_by_id]
    )


class AdjudicationEvent(Base):
    """A decision about evidence, recorded as an event.

    Almost every row is a human decision, and the table is shaped for that: a
    mandatory reason, an actor copied in by name and address, a per-subject
    sequence.  The one machine writer is the reconciliation stage, which moves
    a document's proof class once the arithmetic it could not run at ingestion
    has run.  It is here rather than in a log of its own because the question
    "why is this document in this class" has one answer, and splitting the
    answer across two tables would mean a reader could see half of it and
    believe they had seen all of it.  Machine rows are separable by actor: see
    ``AdjudicationDecision.reclassify_document``.

    Rows are appended and never updated, which is why this model does not take
    ``TimestampMixin``: an ``updated_at`` column would invite exactly the
    mutation the table exists to rule out.

    ``subject_id`` carries no foreign key because the subject may be any of
    several tables.  The trade is deliberate: a decision must outlive the row it
    was about, and a cascade that deleted the record of a decision would
    destroy the audit trail at precisely the moment it was needed.  Referential
    integrity is checked in the service layer instead.

    That is also why this model lives in ``financial.py`` under an unqualified
    name.  The table was built polymorphic and first used by the financial
    stages, so it was called ``financial_adjudications`` until
    ``20260901_rename_adjudications`` dropped the prefix.  Which subjects it
    accepts is a fact about one ``CHECK`` constraint and the
    ``AdjudicationSubject`` vocabulary, not about the structure or about this
    module; the file it is declared in is history rather than scope.

    The class is ``AdjudicationEvent`` rather than ``Adjudication`` because
    ``Adjudication`` is taken, by
    :class:`services.financial.adjudication.Adjudication` -- a balance-failure
    verdict, which is the *payload* of one member of this table's vocabulary
    (``explain_balance_failure``) rather than a row of it.  Both are exported
    from their package roots, so sharing a name would leave a reader of
    ``Adjudication(...)`` unable to tell a ledger row from a verdict without
    checking the imports.  ``Event`` is the accurate half of the distinction:
    rows here are appended facts about what was done, whatever the subject.

    Actor name and email are copied in at the time of the decision for the same
    reason the run table copies them: a deleted user must not erase who
    decided what.

    ``subject_sequence`` orders the decisions about one subject, and exists
    because ``created_at`` cannot.  Postgres ``now()`` is transaction-start
    time, so every row written in one transaction shares it; SQLite's
    ``CURRENT_TIMESTAMP`` is granular to the second.  Ordering by timestamp and
    breaking ties on ``id`` would give a stable answer, but ``id`` is a random
    uuid4, so the answer would be arbitrary — which is worse than no order at
    all, because it looks like one.  A quarantine and the release that undid it
    are the exact pair a reader must be able to tell apart, and they are the
    pair most likely to be written together.

    The counter is assigned in the service layer rather than by a sequence, so
    that it is per subject and portable to the SQLite the tests build.  The
    unique constraint is what makes it worth having: a gap or a repeat in a
    subject's history is then a fact the database will show you, rather than an
    absence you would have to already suspect to look for.
    """

    __tablename__ = "adjudications"
    __table_args__ = (
        CheckConstraint(
            f"subject_type IN {_ADJUDICATION_SUBJECTS}",
            name="ck_adjudications_subject_type",
        ),
        CheckConstraint(
            f"decision IN {_ADJUDICATION_DECISIONS}",
            name="ck_adjudications_decision",
        ),
        CheckConstraint(
            _REASON_NOT_BLANK,
            name="ck_adjudications_reason_not_blank",
        ),
        CheckConstraint(
            "subject_sequence >= 1",
            name="ck_adjudications_sequence_positive",
        ),
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "subject_sequence",
            name="uq_adjudications_subject_sequence",
        ),
        Index(
            "ix_adjudications_subject", "subject_type", "subject_id"
        ),
        Index("ix_adjudications_case", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )

    subject_type: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # 1 for the first decision about a subject, and one more for each after.
    # Assigned in services.financial.decisions.record; see the class docstring
    # on why this is not a timestamp and not a sequence.
    subject_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    decision: Mapped[str] = mapped_column(String(48), nullable=False)
    # Free text and mandatory.  An adjudication without a stated reason is not
    # an adjudication; it is an unexplained edit.
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    before: Mapped[dict | None] = mapped_column(_jsonb_column(), nullable=True)
    after: Mapped[dict | None] = mapped_column(_jsonb_column(), nullable=True)

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False)

    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("financial_ingestion_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    case = relationship("Case", foreign_keys=[case_id])
    actor = relationship("User", foreign_keys=[actor_user_id])
    ingestion_run = relationship(
        "FinancialIngestionRun", foreign_keys=[ingestion_run_id]
    )
