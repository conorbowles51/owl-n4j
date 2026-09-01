"""Tests for source documents: what the class is derived from, and when it moves.

The subject of this module is one column.  ``proof_class`` is what every total
filters on, so an error in it does not surface as a wrong document, it surfaces
as a wrong figure, computed from a population that quietly gained or lost a row.
The tests are therefore organised around the two ways that column can come to
hold something nobody chose:

*A caller supplying it.*  The writer takes a ``SourceShape`` and derives the
class, and there is no parameter to override that.  So the assertions here are
mostly that the draft refuses -- a shape that is a string, a layer that is a
bare int, a metadata key that would give a second and unvalidated way to say
what the document is.

*The class moving with nothing on the record.*  A document is admitted before
its arithmetic can run, so the class it is admitted at is provisional by
construction and something has to move it later.  The assertions there are that
the move is logged first, that the log names a machine rather than a person, and
that a move which is not a move writes nothing at all.

The direction of every judgement is the one ``proof_class.py`` states: admitting
a document one class too low costs an adjudication a person will resolve, while
admitting it one class too high puts an unchecked row inside a total.  So where
a test could assert either, it asserts the pessimistic reading -- most visibly
in :class:`AdmittedClassTests`, where a camt.053 whose format *guarantees*
control totals is still written at p3.

The database-backed tests use a file on disk rather than ``:memory:``, matching
``test_financial_accounts`` and ``test_financial_periods``: the run service opens
sessions of its own, and a test where the caller and the bookkeeping share one
connection cannot see what production sees.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    ExtractionLayer,
    GlobalRole,
    ProofClass,
    ReconciliationStatus,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import (
    FinancialAccount,
    AdjudicationEvent,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User
from services.financial.documents import (
    RECONCILIATION_ACTOR_EMAIL,
    SHAPE_METADATA_KEY,
    DocumentFieldError,
    ExtractionLayerMismatchError,
    SourceDocumentDraft,
    SourceDocumentError,
    UnknownSourceShapeError,
    combine_period_outcomes,
    document_reconciliation,
    read_source_shape,
    reclassify_after_reconciliation,
    reconciliation_actor,
    record_source_document,
)
from services.financial.money import UnknownCurrencyError
from services.financial.proof_class import SourceShape
from services.financial.runs import RunScopeError, open_ingestion_run

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
    AdjudicationEvent.__table__,
]

GBP = "GBP"
HASH_A = "a" * 64
HASH_B = "b" * 64


def draft(**overrides) -> SourceDocumentDraft:
    """A statement-document draft, which is the corpus's ordinary case."""
    overrides.setdefault("evidence_file_id", uuid.uuid4())
    overrides.setdefault("sha256_at_ingestion", HASH_A)
    overrides.setdefault("document_type", "bank_statement")
    overrides.setdefault("shape", SourceShape.statement_document)
    overrides.setdefault("extraction_layer", ExtractionLayer.structural)
    overrides.setdefault("parser_name", "statement_pdf")
    overrides.setdefault("parser_version", "1.4.0")
    return SourceDocumentDraft(**overrides)


# ---------------------------------------------------------------------------
# The class the writer would assign.  No database: these are about derivation.
# ---------------------------------------------------------------------------


class AdmittedClassTests(unittest.TestCase):
    """What a draft grades to before any arithmetic has been run."""

    def test_a_statement_is_admitted_unchecked_at_p3(self):
        self.assertEqual(draft().proof_class, ProofClass.p3)

    def test_a_mandatory_totals_format_is_also_admitted_at_p3(self):
        """The consequential one.

        A camt.053's format guarantees control totals, and it is still written
        at p3, because at admission the guarantee has not been collected.  If
        this ever returns p0 the document auto-admits on the strength of a
        check nobody ran.
        """
        camt = draft(
            shape=SourceShape.native_with_control_totals,
            extraction_layer=ExtractionLayer.native,
            document_type="camt.053",
        )
        self.assertEqual(camt.proof_class, ProofClass.p3)

    def test_a_totals_free_native_export_is_p1_immediately(self):
        """Nothing will ever check it, so admission is the whole decision."""
        ofx = draft(
            shape=SourceShape.native_without_control_totals,
            extraction_layer=ExtractionLayer.native,
            document_type="ofx",
        )
        self.assertEqual(ofx.proof_class, ProofClass.p1)

    def test_a_narrative_is_p4(self):
        chat = draft(
            shape=SourceShape.unstructured_narrative,
            document_type="chat_export",
        )
        self.assertEqual(chat.proof_class, ProofClass.p4)

    def test_no_draft_field_names_a_proof_class(self):
        """The absence is the design, so it is asserted rather than assumed."""
        self.assertNotIn(
            "proof_class", SourceDocumentDraft.__dataclass_fields__
        )


# ---------------------------------------------------------------------------
# What the draft refuses
# ---------------------------------------------------------------------------


class ShapeAndLayerTests(unittest.TestCase):
    def test_a_shape_spelled_as_a_string_is_refused(self):
        with self.assertRaises(DocumentFieldError):
            draft(shape="statement_document")

    def test_a_layer_spelled_as_a_bare_int_is_refused(self):
        """0 is a valid column value, so a wrong 0 is invisible once stored."""
        with self.assertRaises(ExtractionLayerMismatchError):
            draft(shape=SourceShape.statement_document, extraction_layer=0)

    def test_a_native_shape_must_have_been_read_natively(self):
        """The guard.  p1 auto-admits with no arithmetic anywhere behind it.

        Naming a native shape for a model's reading of a screenshot is how
        model output reaches the verified ledger with nothing downstream that
        would ever look at it again.
        """
        for layer in (
            ExtractionLayer.template,
            ExtractionLayer.structural,
            ExtractionLayer.grounded_model,
        ):
            for shape in (
                SourceShape.native_with_control_totals,
                SourceShape.native_without_control_totals,
            ):
                with self.subTest(shape=shape, layer=layer):
                    with self.assertRaises(ExtractionLayerMismatchError):
                        draft(shape=shape, extraction_layer=layer)

    def test_the_mismatch_is_an_error_not_a_quiet_downgrade(self):
        """A caller who said two contradictory things should find out."""
        with self.assertRaises(ExtractionLayerMismatchError) as caught:
            draft(
                shape=SourceShape.native_without_control_totals,
                extraction_layer=ExtractionLayer.grounded_model,
            )
        self.assertIn("Name the shape the reading actually supports", str(caught.exception))

    def test_a_statement_may_be_read_at_any_layer(self):
        """It still has to pass the arithmetic to leave p3, so a layer rule
        here would refuse real files and catch nothing the check does not."""
        for layer in ExtractionLayer:
            with self.subTest(layer=layer):
                self.assertEqual(
                    draft(
                        shape=SourceShape.statement_document,
                        extraction_layer=layer,
                    ).proof_class,
                    ProofClass.p3,
                )


class DraftFieldTests(unittest.TestCase):
    def test_a_hash_that_is_not_64_hex_characters_is_refused(self):
        for bad in ("", "abc", "A" * 63, "z" * 64, "0x" + "a" * 62):
            with self.subTest(bad=bad):
                with self.assertRaises(DocumentFieldError):
                    draft(sha256_at_ingestion=bad)

    def test_a_hash_is_normalised_to_lower_case(self):
        """Stored to be compared against the evidence file's own hash.  A
        difference of case would differ from a matching hash and read as
        tampering."""
        self.assertEqual(draft(sha256_at_ingestion="A" * 64).sha256_at_ingestion, HASH_A)

    def test_over_length_text_is_refused_rather_than_truncated(self):
        """A truncated parser version is a version that never existed."""
        with self.assertRaises(DocumentFieldError):
            draft(parser_version="1." * 20)
        with self.assertRaises(DocumentFieldError):
            draft(parser_name="p" * 65)
        with self.assertRaises(DocumentFieldError):
            draft(document_type="d" * 33)

    def test_required_text_may_not_be_blank(self):
        for blank in ("", "   ", None):
            with self.subTest(blank=blank):
                with self.assertRaises(DocumentFieldError):
                    draft(parser_name=blank)

    def test_a_blank_institution_becomes_absent(self):
        """Otherwise 'no institution recorded' has two spellings and a count
        of them gives two different answers."""
        self.assertIsNone(draft(institution_name="   ").institution_name)
        self.assertIsNone(draft(institution_name=None).institution_name)

    def test_page_count_of_zero_is_refused(self):
        """Absent says nobody counted; zero says someone counted none."""
        with self.assertRaises(DocumentFieldError):
            draft(page_count=0)
        with self.assertRaises(DocumentFieldError):
            draft(page_count=-1)
        self.assertIsNone(draft(page_count=None).page_count)
        self.assertEqual(draft(page_count=12).page_count, 12)

    def test_a_bool_is_not_a_page_count(self):
        with self.assertRaises(DocumentFieldError):
            draft(page_count=True)

    def test_currency_is_normalised_through_the_registry(self):
        self.assertEqual(draft(currency="gbp").currency, GBP)

    def test_an_unknown_currency_is_refused(self):
        """An unrecognised code has no exponent, and a guessed exponent puts
        the decimal point in the wrong place."""
        with self.assertRaises(UnknownCurrencyError):
            draft(currency="ZZZ")

    def test_metadata_may_not_carry_the_shape_key(self):
        """A second, unvalidated way to say what the document is."""
        with self.assertRaises(DocumentFieldError) as caught:
            draft(metadata={SHAPE_METADATA_KEY: "native_with_control_totals"})
        self.assertIn(SHAPE_METADATA_KEY, str(caught.exception))

    def test_metadata_is_copied_so_the_caller_cannot_mutate_it_later(self):
        supplied = {"bates": "OCG-000123"}
        made = draft(metadata=supplied)
        supplied["bates"] = "OCG-999999"
        self.assertEqual(made.metadata["bates"], "OCG-000123")


# ---------------------------------------------------------------------------
# The fold from many periods to one class
# ---------------------------------------------------------------------------


class CombinePeriodOutcomesTests(unittest.TestCase):
    def test_no_periods_is_not_attempted(self):
        """The case that matters.  ``all(...)`` over an empty list is True,
        which is exactly the input a promotion must not be built on."""
        self.assertIs(combine_period_outcomes([]), ReconciliationStatus.not_attempted)

    def test_one_unbalanced_period_makes_the_document_unbalanced(self):
        self.assertIs(
            combine_period_outcomes(
                [
                    ReconciliationStatus.balanced,
                    ReconciliationStatus.balanced,
                    ReconciliationStatus.unbalanced,
                ]
            ),
            ReconciliationStatus.unbalanced,
        )

    def test_every_period_balanced_and_nothing_less(self):
        self.assertIs(
            combine_period_outcomes(
                [ReconciliationStatus.balanced, ReconciliationStatus.balanced]
            ),
            ReconciliationStatus.balanced,
        )
        self.assertIs(
            combine_period_outcomes(
                [ReconciliationStatus.balanced, ReconciliationStatus.not_attempted]
            ),
            ReconciliationStatus.not_attempted,
        )

    def test_unavailable_outranks_not_attempted(self):
        self.assertIs(
            combine_period_outcomes(
                [ReconciliationStatus.unavailable, ReconciliationStatus.not_attempted]
            ),
            ReconciliationStatus.unavailable,
        )

    def test_a_bare_string_is_refused(self):
        with self.assertRaises(SourceDocumentError):
            combine_period_outcomes(["balanced"])


# ---------------------------------------------------------------------------
# The writer and the regrade
# ---------------------------------------------------------------------------


class DocumentPersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-documents-")
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
            title="Document Fixture",
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
        self.foreign_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.other_case.id,
            original_filename="not-our-matter.pdf",
            stored_path="/evidence/not-our-matter.pdf",
            sha256=HASH_B,
        )
        self.db.add_all(
            [
                self.user,
                self.case,
                self.other_case,
                self.evidence_file,
                self.foreign_file,
            ]
        )
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def second_run(self, case_id=None):
        # Committed first: SQLAlchemy expires objects on commit, and against
        # file-backed SQLite a stale read transaction on this connection blocks
        # the run service's independent session.  Production reaches a second
        # run the same way -- the first run's work is already committed.
        self.db.commit()
        return open_ingestion_run(
            case_id=case_id or self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )

    def statement(self, **overrides):
        overrides.setdefault("evidence_file_id", self.evidence_file.id)
        return draft(**overrides)

    def admit(self, **overrides):
        return record_source_document(self.db, self.run, self.statement(**overrides))

    def add_period(self, document, status, account=None):
        """One period, on a fresh account unless the caller names one.

        ``uq_financial_statement_periods_document_account_undated`` holds a
        document to one period per account when the dates could not be read,
        because "one document covers one account once" is true whether or not
        anyone could read the dates.  So a document with several periods is a
        combined statement spanning several accounts, and that is the shape a
        worst-case fold has to be tested against.
        """
        period = FinancialStatementPeriod(
            id=uuid.uuid4(),
            case_id=self.case.id,
            source_document_id=document.id,
            account_id=(account or self.account()).id,
            ingestion_run_id=self.run.run_id,
            currency=GBP,
            reconciliation_status=status.value,
        )
        self.db.add(period)
        self.db.flush()
        return period

    def account(self, identifier=None):
        """A distinct account per call, so periods do not collide.

        Built by hand rather than stamped: an account is matter-level and
        outlives any one run, so it carries ``first_seen_run_id`` and has no
        ``ingestion_run_id`` for ``run.stamp`` to set.
        """
        self._accounts = getattr(self, "_accounts", 0) + 1
        digits = identifier or f"2044556{self._accounts}"
        account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=self.case.id,
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


class RecordSourceDocumentTests(DocumentPersistenceTestCase):
    def test_writes_the_document_with_its_case_and_run(self):
        document = self.admit()
        self.db.commit()

        self.assertEqual(document.case_id, self.case.id)
        self.assertEqual(document.ingestion_run_id, self.run.run_id)
        self.assertEqual(document.evidence_file_id, self.evidence_file.id)

    def test_the_stored_class_is_derived_not_supplied(self):
        self.assertEqual(self.admit().proof_class, ProofClass.p3.value)

    def test_the_shape_is_recorded_so_the_regrade_can_read_it(self):
        """A class cannot be inverted to a shape -- p3 is reached from three of
        the four -- so a document written without this can be graded by nobody.
        """
        document = self.admit()
        self.db.commit()
        self.assertEqual(
            document.metadata_[SHAPE_METADATA_KEY],
            SourceShape.statement_document.value,
        )
        self.assertIs(read_source_shape(document), SourceShape.statement_document)

    def test_caller_metadata_is_kept_alongside_the_shape(self):
        document = self.admit(metadata={"bates": "OCG-000123"})
        self.db.commit()
        self.assertEqual(document.metadata_["bates"], "OCG-000123")
        self.assertIn(SHAPE_METADATA_KEY, document.metadata_)

    def test_a_document_is_admitted_never_quarantined(self):
        """Quarantine is a decision about a document that has been read, so it
        needs the document to exist, and it records who took it."""
        document = self.admit()
        self.assertEqual(document.status, "admitted")
        self.assertIsNone(document.quarantine_reason)

    def test_a_missing_evidence_file_is_refused(self):
        with self.assertRaises(RunScopeError):
            record_source_document(
                self.db, self.run, draft(evidence_file_id=uuid.uuid4())
            )

    def test_another_matters_file_is_refused(self):
        """The foreign key guarantees the row exists, not that it concerns this
        investigation."""
        with self.assertRaises(RunScopeError) as caught:
            self.admit(evidence_file_id=self.foreign_file.id)
        self.assertIn(str(self.other_case.id), str(caught.exception))

    def test_one_row_per_file_per_run(self):
        self.admit()
        self.db.flush()
        with self.assertRaises(IntegrityError):
            self.admit()
            self.db.flush()
        self.db.rollback()

    def test_re_ingesting_under_a_new_run_is_a_new_row(self):
        """The second reading may have used a different parser, and overwriting
        the first would destroy the record that it ever said something else."""
        first = self.admit()
        first_id = first.id
        run_two = self.second_run()
        second = record_source_document(
            self.db, run_two, self.statement(parser_version="2.0.0")
        )
        self.db.commit()

        self.assertNotEqual(first_id, second.id)
        self.assertEqual(second.parser_version, "2.0.0")


class ReadSourceShapeTests(DocumentPersistenceTestCase):
    def test_a_document_with_no_recorded_shape_is_refused(self):
        document = self.admit()
        document.metadata_ = {}
        self.db.flush()
        with self.assertRaises(UnknownSourceShapeError):
            read_source_shape(document)

    def test_a_shape_that_is_not_a_member_is_refused(self):
        document = self.admit()
        document.metadata_ = {SHAPE_METADATA_KEY: "native_ish"}
        self.db.flush()
        with self.assertRaises(UnknownSourceShapeError):
            read_source_shape(document)


class DocumentReconciliationTests(DocumentPersistenceTestCase):
    def test_a_document_with_no_periods_has_not_been_checked(self):
        document = self.admit()
        self.assertIs(
            document_reconciliation(self.db, document),
            ReconciliationStatus.not_attempted,
        )

    def test_the_periods_are_folded_worst_case(self):
        document = self.admit()
        self.add_period(document, ReconciliationStatus.balanced)
        self.add_period(document, ReconciliationStatus.unbalanced)
        self.assertIs(
            document_reconciliation(self.db, document),
            ReconciliationStatus.unbalanced,
        )

    def test_all_balanced_reads_as_balanced(self):
        document = self.admit()
        self.add_period(document, ReconciliationStatus.balanced)
        self.add_period(document, ReconciliationStatus.balanced)
        self.assertIs(
            document_reconciliation(self.db, document),
            ReconciliationStatus.balanced,
        )

    def test_only_this_documents_periods_are_read(self):
        document = self.admit()
        self.add_period(document, ReconciliationStatus.balanced)

        other_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename="february-statement.pdf",
            stored_path="/evidence/february-statement.pdf",
            sha256=HASH_B,
        )
        self.db.add(other_file)
        self.db.flush()
        other = self.admit(
            evidence_file_id=other_file.id, sha256_at_ingestion=HASH_B
        )
        self.add_period(other, ReconciliationStatus.unbalanced)

        self.assertIs(
            document_reconciliation(self.db, document),
            ReconciliationStatus.balanced,
        )


class ReclassifyTests(DocumentPersistenceTestCase):
    def adjudications(self):
        return list(
            self.db.scalars(
                select(AdjudicationEvent).order_by(
                    AdjudicationEvent.subject_sequence
                )
            ).all()
        )

    def test_a_balanced_statement_is_promoted_to_p2(self):
        document = self.admit()
        self.db.flush()

        logged = reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced, run=self.run
        )
        self.db.commit()

        self.assertIsNotNone(logged)
        self.assertEqual(document.proof_class, ProofClass.p2.value)

    def test_the_promotion_is_logged_as_the_seventh_decision(self):
        document = self.admit()
        self.db.flush()
        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced
        )
        self.db.commit()

        rows = self.adjudications()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].decision, AdjudicationDecision.reclassify_document.value)
        self.assertEqual(
            rows[0].subject_type, AdjudicationSubject.source_document.value
        )
        self.assertEqual(rows[0].subject_id, document.id)

    def test_the_log_names_a_machine_that_no_person_can_be(self):
        """'How many documents did your analysts reclassify' is answered by
        excluding this address, and the answer is only sound if nobody can hold
        it.  ``.invalid`` is reserved by RFC 2606 and never resolves."""
        document = self.admit()
        self.db.flush()
        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced
        )
        self.db.commit()

        row = self.adjudications()[0]
        self.assertEqual(row.actor_email, RECONCILIATION_ACTOR_EMAIL)
        self.assertTrue(row.actor_email.endswith(".invalid"))
        self.assertIsNone(reconciliation_actor().user_id)

    def test_the_event_carries_the_class_before_and_after(self):
        """This is why there is no ``unreclassify_document``: a later run that
        moves the document back writes another one of these, and the pair reads
        correctly in sequence."""
        document = self.admit()
        self.db.flush()
        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced
        )
        self.db.commit()

        row = self.adjudications()[0]
        self.assertEqual(row.before, {"proof_class": ProofClass.p3.value})
        self.assertEqual(row.after, {"proof_class": ProofClass.p2.value})

    def test_a_balanced_camt053_reaches_p0(self):
        document = self.admit(
            shape=SourceShape.native_with_control_totals,
            extraction_layer=ExtractionLayer.native,
            document_type="camt.053",
        )
        self.db.flush()
        self.assertEqual(document.proof_class, ProofClass.p3.value)

        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced
        )
        self.db.commit()
        self.assertEqual(document.proof_class, ProofClass.p0.value)

    def test_a_failed_statement_stays_at_p3_and_writes_nothing(self):
        """An event claiming a change that did not happen is worse than no
        event, because a reader counting reclassifications would count it."""
        document = self.admit()
        self.db.flush()

        self.assertIsNone(
            reclassify_after_reconciliation(
                self.db, document, ReconciliationStatus.unbalanced
            )
        )
        self.db.commit()
        self.assertEqual(document.proof_class, ProofClass.p3.value)
        self.assertEqual(self.adjudications(), [])

    def test_an_unchecked_document_is_not_promoted(self):
        document = self.admit()
        self.db.flush()
        self.assertIsNone(
            reclassify_after_reconciliation(
                self.db, document, ReconciliationStatus.not_attempted
            )
        )
        self.assertEqual(document.proof_class, ProofClass.p3.value)

    def test_a_demotion_is_recorded_too(self):
        """A rerun finding a previously balanced document unbalanced is the
        move most worth having on the record."""
        document = self.admit()
        self.db.flush()
        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced
        )
        self.db.flush()
        self.assertEqual(document.proof_class, ProofClass.p2.value)

        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.unbalanced
        )
        self.db.commit()

        self.assertEqual(document.proof_class, ProofClass.p3.value)
        rows = self.adjudications()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1].before, {"proof_class": ProofClass.p2.value})
        self.assertEqual(rows[1].after, {"proof_class": ProofClass.p3.value})
        self.assertEqual([r.subject_sequence for r in rows], [1, 2])

    def test_a_totals_free_export_is_demoted_when_its_rows_do_not_close(self):
        """p1 is auto-admitted, so the one outcome that can contradict it is
        the one that must be able to take it back out."""
        document = self.admit(
            shape=SourceShape.native_without_control_totals,
            extraction_layer=ExtractionLayer.native,
            document_type="ofx",
        )
        self.db.flush()
        self.assertEqual(document.proof_class, ProofClass.p1.value)

        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.unbalanced
        )
        self.db.commit()
        self.assertEqual(document.proof_class, ProofClass.p3.value)

    def test_a_narrative_is_never_regraded(self):
        """An outcome passed alongside a narrative describes some other
        artefact and must not be allowed to promote a claim."""
        document = self.admit(
            shape=SourceShape.unstructured_narrative,
            document_type="chat_export",
        )
        self.db.flush()
        for status in ReconciliationStatus:
            with self.subTest(status=status):
                self.assertIsNone(
                    reclassify_after_reconciliation(self.db, document, status)
                )
        self.assertEqual(document.proof_class, ProofClass.p4.value)
        self.assertEqual(self.adjudications(), [])

    def test_a_document_with_no_recorded_shape_cannot_be_regraded(self):
        document = self.admit()
        document.metadata_ = {}
        self.db.flush()
        with self.assertRaises(UnknownSourceShapeError):
            reclassify_after_reconciliation(
                self.db, document, ReconciliationStatus.balanced
            )

    def test_a_bare_string_outcome_is_refused(self):
        """'balanced' and 'balance' would otherwise be two answers, one of
        which silently fails to promote."""
        document = self.admit()
        self.db.flush()
        with self.assertRaises(SourceDocumentError):
            reclassify_after_reconciliation(self.db, document, "balanced")

    def test_a_run_from_another_matter_may_not_regrade_this_document(self):
        document = self.admit()
        foreign_run = self.second_run(case_id=self.other_case.id)
        with self.assertRaises(RunScopeError):
            reclassify_after_reconciliation(
                self.db,
                document,
                ReconciliationStatus.balanced,
                run=foreign_run,
            )

    def test_the_regrade_carries_the_run_that_made_it(self):
        document = self.admit()
        self.db.flush()
        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced, run=self.run
        )
        self.db.commit()
        self.assertEqual(self.adjudications()[0].ingestion_run_id, self.run.run_id)

    def test_the_reason_states_the_outcome_and_the_move(self):
        """The column is mandatory because an unexplained edit is not an
        adjudication, and that applies to the machine's rows too."""
        document = self.admit()
        self.db.flush()
        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced
        )
        self.db.commit()

        reason = self.adjudications()[0].reason
        self.assertIn("balanced", reason)
        self.assertIn(SourceShape.statement_document.value, reason)
        self.assertIn("p3 -> p2", reason)


class ReservationTests(DocumentPersistenceTestCase):
    """A file that passes its arithmetic and still must not auto-admit.

    The reserving cases are the ones where grading on the arithmetic is exactly
    inverted.  A camt.053 marked ``DUPL`` is a *re-sent* message: it repeats
    totals that already agreed, so it balances perfectly, and admitting it
    counts the same money twice.  A NACHA batch of prenotifications is a run of
    zero-dollar account tests: it satisfies every control total vacuously,
    because nothing had to add up, and admitting it enters rehearsal data as
    payments.  In both, the better the agreement the more certainly the
    document admits itself, and the thing it admits is wrong.

    So these tests are not about arithmetic failing.  Every document below
    reports ``balanced``.
    """

    # Borrowed rather than inherited: subclassing ReclassifyTests would re-run
    # all of its cases here under a second name.
    adjudications = ReclassifyTests.adjudications

    CAMT = dict(
        shape=SourceShape.native_with_control_totals,
        extraction_layer=ExtractionLayer.native,
        document_type="camt.053",
    )
    OFX = dict(
        shape=SourceShape.native_without_control_totals,
        extraction_layer=ExtractionLayer.native,
        document_type="ofx",
    )
    DUPL = ("camt.053 carries CopyDuplicateIndicator DUPL",)

    def test_a_reserved_camt053_does_not_reach_p0(self):
        """The defect this parameter exists for."""
        document = self.admit(**self.CAMT)
        self.db.flush()

        reclassify_after_reconciliation(
            self.db,
            document,
            ReconciliationStatus.balanced,
            reservations=self.DUPL,
        )
        self.db.commit()
        self.assertEqual(document.proof_class, ProofClass.p3.value)

    def test_the_same_file_unreserved_still_reaches_p0(self):
        """The withholding has to be the reservation doing it, not the
        parameter's presence breaking the promotion for everyone."""
        document = self.admit(**self.CAMT)
        self.db.flush()

        reclassify_after_reconciliation(
            self.db, document, ReconciliationStatus.balanced, reservations=()
        )
        self.db.commit()
        self.assertEqual(document.proof_class, ProofClass.p0.value)

    def test_withholding_a_promotion_that_never_happened_writes_nothing(self):
        """A reserved native file was admitted at p3 and stays there, so there
        is no change to record.  An event saying so would be a reader's evidence
        that something moved."""
        document = self.admit(**self.CAMT)
        self.db.flush()

        self.assertIsNone(
            reclassify_after_reconciliation(
                self.db,
                document,
                ReconciliationStatus.balanced,
                reservations=self.DUPL,
            )
        )
        self.db.commit()
        self.assertEqual(self.adjudications(), [])

    def test_a_reserved_totals_free_export_is_taken_back_out(self):
        """p1 is auto-admitted on format validation alone, so unlike the
        native-totals case there is a real demotion here: the document was
        already in the ledger and the reservation removes it."""
        document = self.admit(**self.OFX)
        self.db.flush()
        self.assertEqual(document.proof_class, ProofClass.p1.value)

        logged = reclassify_after_reconciliation(
            self.db,
            document,
            ReconciliationStatus.balanced,
            reservations=("rehearsal file",),
        )
        self.db.commit()

        self.assertIsNotNone(logged)
        self.assertEqual(document.proof_class, ProofClass.p3.value)

    def test_a_reserved_statement_document_does_not_reach_p2(self):
        """p2 auto-admits too.  Keying the rule on p0 would have let this one
        through."""
        document = self.admit()
        self.db.flush()

        reclassify_after_reconciliation(
            self.db,
            document,
            ReconciliationStatus.balanced,
            reservations=("scan is stamped COPY",),
        )
        self.db.commit()
        self.assertEqual(document.proof_class, ProofClass.p3.value)

    def test_the_reason_names_the_class_withheld_and_why(self):
        """A reviewer looking at a document that balanced and did not admit
        needs the reason on the record, not in a parser."""
        document = self.admit(**self.OFX)
        self.db.flush()
        reclassify_after_reconciliation(
            self.db,
            document,
            ReconciliationStatus.balanced,
            reservations=("prenotification batch", "no funds moved"),
        )
        self.db.commit()

        reason = self.adjudications()[0].reason
        self.assertIn("p1 withheld", reason)
        self.assertIn("balanced", reason)
        self.assertIn("2 admissibility reservation(s)", reason)
        self.assertIn("prenotification batch", reason)
        self.assertIn("no funds moved", reason)

    def test_a_reservation_does_not_demote_a_failed_document(self):
        """p3 already requires the human act the reservation is asking for."""
        document = self.admit(**self.CAMT)
        self.db.flush()

        self.assertIsNone(
            reclassify_after_reconciliation(
                self.db,
                document,
                ReconciliationStatus.unbalanced,
                reservations=self.DUPL,
            )
        )
        self.assertEqual(document.proof_class, ProofClass.p3.value)

    def test_a_reservation_does_not_regrade_a_narrative(self):
        """p4 is not an auto-admitting class and is never regraded at all."""
        document = self.admit(
            shape=SourceShape.unstructured_narrative, document_type="chat_export"
        )
        self.db.flush()

        self.assertIsNone(
            reclassify_after_reconciliation(
                self.db,
                document,
                ReconciliationStatus.balanced,
                reservations=self.DUPL,
            )
        )
        self.assertEqual(document.proof_class, ProofClass.p4.value)

    def test_a_bare_string_reservation_is_refused(self):
        """A string is a sequence of characters, so one reservation passed
        unwrapped would become dozens of one-letter reasons -- and would still
        be truthy, so the withholding would appear to work while the logged
        reason was nonsense."""
        document = self.admit(**self.CAMT)
        self.db.flush()
        with self.assertRaises(SourceDocumentError):
            reclassify_after_reconciliation(
                self.db,
                document,
                ReconciliationStatus.balanced,
                reservations="camt.053 carries DUPL",
            )

    def test_a_reservation_that_is_not_a_string_is_refused(self):
        document = self.admit(**self.CAMT)
        self.db.flush()
        for bad in (7, None, ["nested"]):
            with self.subTest(reservation=bad):
                with self.assertRaises(SourceDocumentError):
                    reclassify_after_reconciliation(
                        self.db,
                        document,
                        ReconciliationStatus.balanced,
                        reservations=(bad,),
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
