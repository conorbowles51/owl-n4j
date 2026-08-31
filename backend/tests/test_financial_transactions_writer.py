"""Tests for the ledger row writer: the last boundary before money is a total.

Three things can go wrong here, and the module is organised around them.

*The sign is read off a column rather than declared.*  Two opposite conventions
exist in the wild and nothing inside one row tells them apart, so every
assertion about :func:`normalise_sign` is really an assertion that the writer
refuses to guess -- including the two that look pedantic, zero under a signed
convention and a stated direction that contradicts the sign.  Both are places
where a plausible default would silently reverse the direction of money.

*Two genuinely distinct rows collide.*  A document can honestly contain the
same reading twice, and the occurrence index that tells them apart is counted
across the document.  :class:`OccurrenceTests` is the reason this writer takes
a document and not a row, and it is written against the real unique constraint
rather than against the hashing function, because the constraint is what would
actually reject the row in production.

*A row's class stops matching its document's.*  ``DEFAULT_TOTAL_CLASSES`` is
``{p0, p1, p2}``, so a row left at p3 after its document was promoted to p2 is
a row that leaves every total.  :class:`ProofClassPropagationTests` covers the
promotion, the count that gets recorded with it, and the row that must *not*
move because a person moved it first.

The database-backed tests use a file on disk rather than ``:memory:``, matching
``test_financial_documents``: the run service opens sessions of its own, and a
test where the caller and the bookkeeping share one connection cannot see what
production sees.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    DateSource,
    ExtractionLayer,
    GlobalRole,
    ProofClass,
    ReconciliationStatus,
    TransactionDirection,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import (
    FinancialAccount,
    FinancialAdjudication,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User
from services.financial.documents import (
    SourceDocumentDraft,
    reclassify_after_reconciliation,
    record_source_document,
)
from services.financial.proof_class import DEFAULT_TOTAL_CLASSES, SourceShape
from services.financial.references import RowReading, content_hash
from services.financial.runs import RunScopeError, open_ingestion_run
from services.financial.transactions import (
    ORDERING_PRECEDENCE,
    NonLedgerClassError,
    OrderingDateError,
    SignConvention,
    SignConventionError,
    TransactionDraft,
    TransactionFieldError,
    choose_ordering_date,
    normalise_sign,
    record_transactions,
)

TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    FinancialIngestionRun.__table__,
    FinancialSourceDocument.__table__,
    FinancialAccount.__table__,
    FinancialStatementPeriod.__table__,
    FinancialTransaction.__table__,
    FinancialAdjudication.__table__,
]

GBP = "GBP"
HASH_A = "a" * 64
HASH_B = "b" * 64

JANUARY = date(2024, 1, 15)
FEBRUARY = date(2024, 2, 15)


def reading(**overrides) -> RowReading:
    """An ordinary debit, dated the one way most sources date a row."""
    overrides.setdefault("currency", GBP)
    overrides.setdefault("amount_minor", 12_50)
    overrides.setdefault("direction", TransactionDirection.debit)
    overrides.setdefault("posted_date", JANUARY)
    return RowReading(**overrides)


# ---------------------------------------------------------------------------
# Sign.  No database: this is about what the writer refuses to infer.
# ---------------------------------------------------------------------------


class NormaliseSignTests(unittest.TestCase):
    def test_a_direction_indicator_passes_the_magnitude_through(self):
        self.assertEqual(
            normalise_sign(
                1500,
                SignConvention.direction_indicator,
                stated=TransactionDirection.debit,
            ),
            (1500, TransactionDirection.debit),
        )

    def test_a_direction_indicator_without_a_direction_is_refused(self):
        """That convention *is* the claim that the source said which way."""
        with self.assertRaises(SignConventionError):
            normalise_sign(1500, SignConvention.direction_indicator)

    def test_a_negative_under_direction_indicator_is_refused(self):
        """A signed amount here means the convention was named wrongly.

        Taking the absolute value would be the friendly thing to do and would
        make a customer-view export load cleanly under the wrong declaration.
        """
        with self.assertRaises(SignConventionError):
            normalise_sign(
                -1500,
                SignConvention.direction_indicator,
                stated=TransactionDirection.debit,
            )

    def test_the_same_column_means_opposite_things_under_the_two_conventions(self):
        """The whole reason the caller has to declare one.

        One negative number, two readings, and nothing inside the row to
        choose between them.
        """
        customer = normalise_sign(-1500, SignConvention.debit_negative)
        bookkeeper = normalise_sign(-1500, SignConvention.debit_positive)

        self.assertEqual(customer, (1500, TransactionDirection.debit))
        self.assertEqual(bookkeeper, (1500, TransactionDirection.credit))

    def test_a_magnitude_is_returned_not_the_signed_amount(self):
        """ck_financial_transactions_amount_non_negative would reject it."""
        amount, _ = normalise_sign(-1500, SignConvention.debit_negative)
        self.assertEqual(amount, 1500)

    def test_a_stated_direction_agreeing_with_the_sign_is_accepted(self):
        self.assertEqual(
            normalise_sign(
                -1500,
                SignConvention.debit_negative,
                stated=TransactionDirection.debit,
            ),
            (1500, TransactionDirection.debit),
        )

    def test_a_stated_direction_contradicting_the_sign_is_refused(self):
        """The consequential one.

        The source has said two things about one movement.  Preferring either
        buries a disagreement about direction inside a total, and direction is
        the difference between money arriving and money leaving.
        """
        with self.assertRaises(SignConventionError):
            normalise_sign(
                -1500,
                SignConvention.debit_negative,
                stated=TransactionDirection.credit,
            )

    def test_zero_under_a_signed_convention_is_refused(self):
        """A real amount -- a reversed fee -- with no sign to read.

        Both signed conventions, because zero is unsigned under either and a
        default here would invent a direction for every notional entry.
        """
        for convention in (
            SignConvention.debit_negative,
            SignConvention.debit_positive,
        ):
            with self.subTest(convention=convention):
                with self.assertRaises(SignConventionError):
                    normalise_sign(0, convention)

    def test_zero_is_accepted_when_the_direction_is_stated(self):
        self.assertEqual(
            normalise_sign(
                0,
                SignConvention.direction_indicator,
                stated=TransactionDirection.credit,
            ),
            (0, TransactionDirection.credit),
        )

    def test_a_convention_spelled_as_a_string_is_refused(self):
        with self.assertRaises(SignConventionError):
            normalise_sign(-1500, "debit_negative")

    def test_a_float_amount_is_refused(self):
        """15.00 is not 1500, and a float cannot be hashed exactly."""
        with self.assertRaises(SignConventionError):
            normalise_sign(-1500.0, SignConvention.debit_negative)

    def test_a_bool_amount_is_refused(self):
        """True is an int in Python and would store as a penny."""
        with self.assertRaises(SignConventionError):
            normalise_sign(True, SignConvention.debit_negative)


# ---------------------------------------------------------------------------
# Ordering date
# ---------------------------------------------------------------------------


class ChooseOrderingDateTests(unittest.TestCase):
    def test_posted_leads_the_precedence(self):
        """The running balance on a statement advances in posting order."""
        chosen, source = choose_ordering_date(
            reading(posted_date=JANUARY, transaction_date=FEBRUARY)
        )
        self.assertEqual(chosen, JANUARY)
        self.assertIs(source, DateSource.posted)

    def test_the_precedence_is_walked_in_order(self):
        """Each date wins against every date below it, checked pairwise.

        Pairwise rather than one reading carrying all four, because a single
        reading only ever proves the first entry wins.
        """
        for index, (source, attribute) in enumerate(ORDERING_PRECEDENCE):
            for _, lower in ORDERING_PRECEDENCE[index + 1:]:
                with self.subTest(higher=attribute, lower=lower):
                    chosen, picked = choose_ordering_date(
                        RowReading(
                            currency=GBP,
                            amount_minor=100,
                            direction=TransactionDirection.debit,
                            **{attribute: JANUARY, lower: FEBRUARY},
                        )
                    )
                    self.assertEqual(chosen, JANUARY)
                    self.assertIs(picked, source)

    def test_a_reading_with_no_date_at_all_is_refused(self):
        """ck_financial_transactions_has_a_date would reject it anyway.

        Refusing here names the reading; letting it through names a column.
        """
        with self.assertRaises(OrderingDateError):
            choose_ordering_date(
                RowReading(
                    currency=GBP,
                    amount_minor=100,
                    direction=TransactionDirection.debit,
                )
            )

    def test_a_timestamp_is_refused_rather_than_truncated(self):
        """The column is a DATE, so the time would vanish without a word."""
        with self.assertRaises(OrderingDateError):
            choose_ordering_date(
                reading(posted_date=datetime(2024, 1, 15, 9, 30))
            )


# ---------------------------------------------------------------------------
# What the draft refuses
# ---------------------------------------------------------------------------


class TransactionDraftTests(unittest.TestCase):
    def draft(self, **overrides) -> TransactionDraft:
        overrides.setdefault("reading", reading())
        overrides.setdefault("row_index", 0)
        overrides.setdefault("account_id", uuid.uuid4())
        return TransactionDraft(**overrides)

    def test_no_draft_field_names_a_proof_class_or_a_reference(self):
        """The absence is the design, so it is asserted rather than assumed."""
        fields = TransactionDraft.__dataclass_fields__
        for derived in ("proof_class", "ref_id", "content_hash", "case_id"):
            with self.subTest(field=derived):
                self.assertNotIn(derived, fields)

    def test_a_loose_mapping_is_not_a_reading(self):
        """The reading is what gets hashed; a mapping hashes its own keys."""
        with self.assertRaises(TransactionFieldError):
            self.draft(reading={"amount_minor": 100})

    def test_a_negative_row_index_is_refused(self):
        with self.assertRaises(TransactionFieldError):
            self.draft(row_index=-1)

    def test_a_bool_row_index_is_refused(self):
        with self.assertRaises(TransactionFieldError):
            self.draft(row_index=True)

    def test_an_account_id_that_is_not_a_uuid_is_refused(self):
        with self.assertRaises(TransactionFieldError):
            self.draft(account_id=str(uuid.uuid4()))

    def test_an_ordering_date_without_its_source_is_refused(self):
        """A date with no named source cannot be audited."""
        with self.assertRaises(OrderingDateError):
            self.draft(ordering_date=JANUARY)

    def test_an_ordering_source_without_its_date_is_refused(self):
        """A source with no date names a choice nobody made."""
        with self.assertRaises(OrderingDateError):
            self.draft(ordering_date_source=DateSource.posted)

    def test_the_pair_is_accepted_when_it_matches_the_reading(self):
        draft = self.draft(
            ordering_date=JANUARY, ordering_date_source=DateSource.posted
        )
        self.assertEqual(draft.ordering_date, JANUARY)

    def test_a_source_naming_a_date_the_reading_does_not_state_is_refused(self):
        """The column exists to make the choice visible.

        A row ordered by ``value`` when no value date was read has a
        provenance that points at nothing.
        """
        with self.assertRaises(OrderingDateError):
            self.draft(
                reading=reading(posted_date=JANUARY, value_date=None),
                ordering_date=JANUARY,
                ordering_date_source=DateSource.value,
            )

    def test_an_ordering_date_that_is_none_of_the_readings_dates_is_refused(self):
        """The ordering date is one of the four dates, not a fifth."""
        with self.assertRaises(OrderingDateError):
            self.draft(
                reading=reading(posted_date=JANUARY),
                ordering_date=FEBRUARY,
                ordering_date_source=DateSource.posted,
            )

    def test_an_extraction_layer_spelled_as_a_bare_int_is_refused(self):
        """0 is a valid column value, so a wrong 0 is invisible once stored."""
        with self.assertRaises(TransactionFieldError):
            self.draft(extraction_layer=0)

    def test_the_mappings_are_copied_so_a_later_mutation_cannot_reach_in(self):
        supplied = {"page": 2}
        draft = self.draft(provenance=supplied)
        supplied["page"] = 99
        self.assertEqual(draft.provenance, {"page": 2})


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


class TransactionPersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-transactions-")
        self.engine = create_engine(
            f"sqlite+pysqlite:///{Path(self._directory) / 'ledger.db'}",
            future=True,
        )

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )
        self.db = self.SessionLocal()

        self.user = User(
            id=uuid.uuid4(),
            email="investigator@example.test",
            name="Investigator",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid.uuid4(),
            title="Transaction Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid.uuid4(),
            title="A Different Matter",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.evidence_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename="january-statement.pdf",
            stored_path="/evidence/january-statement.pdf",
            sha256=HASH_A,
        )
        self.db.add_all(
            [self.user, self.case, self.other_case, self.evidence_file]
        )
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        self.document = self.admit()
        self.acct = self.account()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def evidence(self, sha256):
        """A distinct evidence file per document.

        ``uq_financial_source_documents_run_file`` holds one run to one
        reading of one file, so a second document inside this run needs a
        second file rather than a second row against the first.
        """
        self._files = getattr(self, "_files", 0) + 1
        record = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename=f"statement-{self._files}.pdf",
            stored_path=f"/evidence/statement-{self._files}.pdf",
            sha256=sha256,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def admit(self, **overrides):
        sha = overrides.setdefault("sha256_at_ingestion", HASH_A)
        if "evidence_file_id" not in overrides:
            overrides["evidence_file_id"] = (
                self.evidence_file.id
                if sha == HASH_A
                else self.evidence(sha).id
            )
        overrides.setdefault("document_type", "bank_statement")
        overrides.setdefault("shape", SourceShape.statement_document)
        overrides.setdefault("extraction_layer", ExtractionLayer.structural)
        overrides.setdefault("parser_name", "statement_pdf")
        overrides.setdefault("parser_version", "1.4.0")
        return record_source_document(
            self.db, self.run, SourceDocumentDraft(**overrides)
        )

    def account(self, case_id=None):
        """A distinct account per call, so identity keys do not collide."""
        self._accounts = getattr(self, "_accounts", 0) + 1
        digits = f"2044556{self._accounts}"
        account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=case_id or self.case.id,
            first_seen_run_id=self.run.run_id,
            identity_key=f"gb-barclays-{digits}",
            institution_name="Barclays",
            identifier_as_printed=f"20-44-55 6{self._accounts}",
            identifier_normalised=digits,
            currency=GBP,
        )
        self.db.add(account)
        self.db.flush()
        return account

    def period(self, document=None, account=None):
        period = FinancialStatementPeriod(
            id=uuid.uuid4(),
            case_id=self.case.id,
            source_document_id=(document or self.document).id,
            account_id=(account or self.acct).id,
            ingestion_run_id=self.run.run_id,
            currency=GBP,
            reconciliation_status=ReconciliationStatus.not_attempted.value,
        )
        self.db.add(period)
        self.db.flush()
        return period

    def draft(self, **overrides) -> TransactionDraft:
        overrides.setdefault("reading", reading())
        overrides.setdefault("row_index", 0)
        overrides.setdefault("account_id", self.acct.id)
        return TransactionDraft(**overrides)

    def write(self, drafts, document=None):
        return record_transactions(
            self.db, self.run, document or self.document, drafts
        )


class RecordTransactionsTests(TransactionPersistenceTestCase):
    def test_writes_the_row_with_its_case_and_run(self):
        (row,) = self.write([self.draft()])
        self.db.commit()

        self.assertEqual(row.case_id, self.case.id)
        self.assertEqual(row.ingestion_run_id, self.run.run_id)
        self.assertEqual(row.source_document_id, self.document.id)
        self.assertEqual(row.account_id, self.acct.id)

    def test_the_reading_is_stored_field_for_field(self):
        (row,) = self.write(
            [
                self.draft(
                    reading=reading(
                        amount_minor=98_76,
                        direction=TransactionDirection.credit,
                        description="TFR FROM SAVINGS",
                        running_balance_minor=100_00,
                    )
                )
            ]
        )
        self.db.commit()

        self.assertEqual(row.amount_minor, 98_76)
        self.assertEqual(row.direction, TransactionDirection.credit.value)
        self.assertEqual(row.description, "TFR FROM SAVINGS")
        self.assertEqual(row.running_balance_minor, 100_00)
        self.assertEqual(row.currency, GBP)

    def test_the_class_is_the_documents_and_is_not_a_parameter(self):
        (row,) = self.write([self.draft()])
        self.assertEqual(row.proof_class, self.document.proof_class)
        self.assertEqual(row.proof_class, ProofClass.p3.value)

    def test_the_reference_is_derived_from_the_documents_digest(self):
        """So that re-ingesting the same file reproduces the same reference.

        A caller-supplied reference is one that stops reproducing.
        """
        (row,) = self.write([self.draft()])
        self.assertIsNotNone(row.ref_id)
        self.assertEqual(row.content_hash, content_hash(reading()))

    def test_a_row_is_admitted_not_quarantined(self):
        (row,) = self.write([self.draft()])
        self.assertEqual(row.ledger_status, "admitted")
        self.assertIsNone(row.quarantine_reason)

    def test_the_ordering_date_is_chosen_and_named(self):
        (row,) = self.write([self.draft()])
        self.assertEqual(row.ordering_date, JANUARY)
        self.assertEqual(row.ordering_date_source, DateSource.posted.value)

    def test_a_formats_own_ordering_choice_is_not_overruled(self):
        """camt.053 defines that booking governs; precedence must not argue."""
        (row,) = self.write(
            [
                self.draft(
                    reading=reading(posted_date=JANUARY, value_date=FEBRUARY),
                    ordering_date=FEBRUARY,
                    ordering_date_source=DateSource.value,
                )
            ]
        )
        self.assertEqual(row.ordering_date, FEBRUARY)
        self.assertEqual(row.ordering_date_source, DateSource.value.value)

    def test_an_empty_document_writes_nothing_and_returns_nothing(self):
        """A period with no movements is a real thing.

        Refusing it would make the writer disagree with the arithmetic, which
        reconciles an empty period against an unchanged balance quite happily.
        """
        self.assertEqual(self.write([]), [])
        self.db.commit()
        self.assertEqual(
            self.db.scalar(
                select(FinancialTransaction).limit(1)
            ),
            None,
        )

    def test_the_row_inherits_the_documents_extraction_layer(self):
        (row,) = self.write([self.draft()])
        self.assertEqual(row.extraction_layer, ExtractionLayer.structural.value)

    def test_a_row_may_be_less_deterministic_than_its_document(self):
        """One figure recovered by a model inside a structural read is true."""
        (row,) = self.write(
            [self.draft(extraction_layer=ExtractionLayer.grounded_model)]
        )
        self.assertEqual(
            row.extraction_layer, ExtractionLayer.grounded_model.value
        )

    def test_a_row_may_not_be_more_deterministic_than_its_document(self):
        """It would claim a guarantee the file never offered."""
        with self.assertRaises(TransactionFieldError):
            self.write([self.draft(extraction_layer=ExtractionLayer.native)])

    def test_two_drafts_at_one_position_are_refused(self):
        with self.assertRaises(TransactionFieldError):
            self.write(
                [
                    self.draft(row_index=0),
                    self.draft(
                        row_index=0, reading=reading(amount_minor=99_99)
                    ),
                ]
            )

    def test_a_bare_mapping_in_place_of_a_draft_is_refused(self):
        with self.assertRaises(TransactionFieldError):
            self.write([{"row_index": 0}])

    def test_a_string_is_not_a_sequence_of_drafts(self):
        with self.assertRaises(TransactionFieldError):
            self.write("rows")


class ScopeTests(TransactionPersistenceTestCase):
    """The guards the foreign keys cannot express.

    Every one of these is a row that the database would accept and file under
    the wrong matter, which ``runs`` calls evidence pointed at the wrong
    person.
    """

    def test_an_account_from_another_case_is_refused(self):
        foreign = self.account(case_id=self.other_case.id)
        with self.assertRaises(RunScopeError):
            self.write([self.draft(account_id=foreign.id)])

    def test_an_account_that_does_not_exist_is_refused(self):
        with self.assertRaises(RunScopeError):
            self.write([self.draft(account_id=uuid.uuid4())])

    def test_a_period_belonging_to_another_document_is_refused(self):
        """It would be counted into that document's opening-to-closing sum.

        The identity would then fail on a page nobody printed it on.
        """
        other_document = self.admit(sha256_at_ingestion=HASH_B)
        foreign_period = self.period(document=other_document)
        with self.assertRaises(RunScopeError):
            self.write([self.draft(statement_period_id=foreign_period.id)])

    def test_a_period_covering_another_account_is_refused(self):
        other_account = self.account()
        period = self.period(account=other_account)
        with self.assertRaises(RunScopeError):
            self.write([self.draft(statement_period_id=period.id)])

    def test_a_period_that_does_not_exist_is_refused(self):
        with self.assertRaises(RunScopeError):
            self.write([self.draft(statement_period_id=uuid.uuid4())])

    def test_a_matching_period_is_accepted(self):
        period = self.period()
        (row,) = self.write([self.draft(statement_period_id=period.id)])
        self.assertEqual(row.statement_period_id, period.id)

    def test_a_p4_document_may_not_produce_rows_at_all(self):
        """A corroborating document supports readings and states none."""
        narrative = self.admit(
            sha256_at_ingestion=HASH_B,
            shape=SourceShape.unstructured_narrative,
            document_type="chat_export",
        )
        self.assertEqual(narrative.proof_class, ProofClass.p4.value)
        with self.assertRaises(NonLedgerClassError):
            self.write([self.draft()], document=narrative)


class OccurrenceTests(TransactionPersistenceTestCase):
    """Why the unit of this writer is the document and not the row."""

    def test_one_document_may_honestly_contain_the_same_reading_twice(self):
        """Two identical cash withdrawals on one day are two withdrawals.

        Asserted against the constraint by committing, not merely against the
        hashes, because the constraint is what rejects the row in production.
        """
        rows = self.write(
            [
                self.draft(row_index=0),
                self.draft(row_index=1),
            ]
        )
        self.db.commit()

        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0].content_hash, rows[1].content_hash)
        self.assertNotEqual(rows[0].ref_id, rows[1].ref_id)
        stored = self.db.scalars(
            select(FinancialTransaction).where(
                FinancialTransaction.source_document_id == self.document.id
            )
        ).all()
        self.assertEqual(len(stored), 2)

    def test_splitting_one_document_across_two_calls_collides(self):
        """The failure the document-at-a-time rule exists to prevent.

        Each call counts occurrences only over the rows it was given, so the
        second identical row takes occurrence zero a second time and the
        unique constraint rejects a row that belongs in the ledger.  This is
        asserted so that anyone tempted to make the writer row-at-a-time finds
        out here rather than on a client's statement.
        """
        self.write([self.draft(row_index=0)])
        self.db.flush()
        with self.assertRaises(IntegrityError) as caught:
            self.write([self.draft(row_index=1)])
        # Named, so that this cannot quietly start passing because some other
        # constraint fired first and the collision stopped being reachable.
        self.assertIn("content_hash", str(caught.exception.orig))
        self.db.rollback()


class ProofClassPropagationTests(TransactionPersistenceTestCase):
    """The p3 staleness bug: a balanced statement whose money disappears.

    A statement is admitted at p3.  Its rows cannot exist before it does and
    the arithmetic cannot run before its rows do, so the rows are necessarily
    written at p3 too.  When reconciliation closes and the document is promoted
    to p2, rows left behind at p3 fall outside ``DEFAULT_TOTAL_CLASSES`` --
    the arithmetic passed and every figure computed from it lost the rows.
    """

    def promote(self):
        return reclassify_after_reconciliation(
            self.db, self.document, ReconciliationStatus.balanced
        )

    def test_p3_is_outside_the_default_total_population(self):
        """The premise of everything below, asserted rather than assumed."""
        self.assertNotIn(ProofClass.p3, DEFAULT_TOTAL_CLASSES)
        self.assertIn(ProofClass.p2, DEFAULT_TOTAL_CLASSES)

    def test_the_rows_move_with_their_document(self):
        rows = self.write([self.draft(row_index=0), self.draft(row_index=1)])
        self.db.flush()
        self.assertEqual(
            {row.proof_class for row in rows}, {ProofClass.p3.value}
        )

        self.promote()
        self.db.commit()

        self.assertEqual(self.document.proof_class, ProofClass.p2.value)
        for row in rows:
            self.db.refresh(row)
            self.assertEqual(row.proof_class, ProofClass.p2.value)

    def test_the_moved_count_is_recorded_on_the_adjudication(self):
        """A number the table can be held to, written before the update."""
        self.write([self.draft(row_index=0), self.draft(row_index=1)])
        self.db.flush()

        adjudication = self.promote()
        self.db.commit()

        self.assertIn("2 ledger row", adjudication.reason)

    def test_a_row_adjudicated_to_its_own_class_is_left_alone(self):
        """An automatic pass must not erase a human decision.

        The filter moves only rows still holding the document's previous
        class, which is what makes this true rather than a special case.
        """
        moved, kept = self.write(
            [self.draft(row_index=0), self.draft(row_index=1)]
        )
        kept.proof_class = ProofClass.p1.value
        self.db.flush()

        self.promote()
        self.db.commit()

        self.db.refresh(moved)
        self.db.refresh(kept)
        self.assertEqual(moved.proof_class, ProofClass.p2.value)
        self.assertEqual(kept.proof_class, ProofClass.p1.value)

    def test_a_document_with_no_rows_still_regrades(self):
        adjudication = self.promote()
        self.db.commit()
        self.assertEqual(self.document.proof_class, ProofClass.p2.value)
        self.assertIn("0 ledger row", adjudication.reason)

    def test_a_failed_reconciliation_leaves_the_rows_where_they_are(self):
        """p3 to p3 is not a move, so nothing is written and nothing logged."""
        (row,) = self.write([self.draft()])
        self.db.flush()

        self.assertIsNone(
            reclassify_after_reconciliation(
                self.db, self.document, ReconciliationStatus.unbalanced
            )
        )
        self.db.commit()

        self.db.refresh(row)
        self.assertEqual(row.proof_class, ProofClass.p3.value)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
