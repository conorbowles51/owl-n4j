"""Tests for the per-case census of proof classes.

``proof_class`` computes a class and states what each class licenses.  Until
this module there was no caller for ``requires_adjudication`` anywhere in the
running system, which meant the one class whose route into the ledger is a
recorded human act was named by a function nothing asked.  So the claim
checked hardest here is that the p3 population is counted and reported as
requiring adjudication, and that it is counted from the rows rather than
assumed.

Four groups of claims, in rough order of what it would cost to get them
wrong.

*The case bounds the read.*  Documents and rows in another matter must not be
counted, and the same tables are read directly rather than through anything
that already scopes them, so the scoping has to be demonstrated rather than
inherited.

*The parts add up to the whole.*  ``documents`` and ``transactions`` are
summed from the per-class figures.  A census whose total disagrees with its
own breakdown is worse than no census, because both numbers look equally
authoritative.

*Every class is reported, present or absent.*  An omitted key and a zero say
different things and only one of them is true.

*The licences are the ones proof_class states.*  They are carried on the
record so that no reader re-derives them from a two-character string, which
means the record has to agree with the functions it copies, member by member.

Rows are inserted directly rather than through an ingestion run.  This is a
reader over two columns of two tables, and its contract is about rows in
those tables and not about the route they took; going through the pipeline
would make the fixture depend on parsing a document, which is not what is
under test.
"""

from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    DateSource,
    DocumentStatus,
    ExtractionLayer,
    GlobalRole,
    IngestionRunStatus,
    LedgerStatus,
    ProofClass,
    TransactionDirection,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import (
    FinancialAccount,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User
from services.financial.proof_class import (
    AUTO_ADMITTED_CLASSES,
    DEFAULT_TOTAL_CLASSES,
    admits_automatically,
    counts_toward_totals,
    may_produce_ledger_rows,
    requires_adjudication,
)
from services.financial.proof_standing import (
    ClassStanding,
    ProofStanding,
    ProofStandingError,
    _member,
    case_proof_standing,
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
]


class ProofStandingTestCase(unittest.TestCase):
    """A case with evidence in several classes, and a second matter beside it."""

    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )
        self.db = self.SessionLocal()

        self.user = User(
            id=uuid4(),
            email="investigator@example.test",
            name="Investigator",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid4(),
            title="Proof Standing Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid4(),
            title="A Different Matter",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case, self.other_case])
        self.db.commit()

        self.evidence_file = self.make_evidence_file()
        self.run = self.make_run()
        self.account = self.make_account()
        self.db.commit()

        self._row_index = 0

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine, tables=list(reversed(TABLES)))
        self.engine.dispose()

    # ---- fixture builders ------------------------------------------------

    def make_evidence_file(self, *, case=None, name=None):
        name = name or f"statement-{uuid4().hex[:8]}.pdf"
        evidence_file = EvidenceFile(
            id=uuid4(),
            case_id=(case or self.case).id,
            original_filename=name,
            stored_path=f"/evidence/{name}",
            sha256=uuid4().hex + uuid4().hex,
        )
        self.db.add(evidence_file)
        self.db.flush()
        return evidence_file

    def make_run(self, *, case=None):
        run = FinancialIngestionRun(
            id=uuid4(),
            case_id=(case or self.case).id,
            status=IngestionRunStatus.completed.value,
            code_version="financial@1.0.0",
            ruleset_version="rules@2026.08",
            started_by_user_id=self.user.id,
            started_by_email=self.user.email,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def make_account(self, *, case=None, digits="20445566"):
        account = FinancialAccount(
            id=uuid4(),
            case_id=(case or self.case).id,
            identity_key=f"gb-barclays-{digits}-{uuid4().hex[:6]}",
            institution_name="Barclays",
            identifier_as_printed="20-44-55 66",
            identifier_normalised=digits,
            currency="GBP",
        )
        self.db.add(account)
        self.db.flush()
        return account

    def make_document(
        self,
        proof_class=ProofClass.p2,
        *,
        case=None,
        run=None,
        evidence_file=None,
        status=DocumentStatus.admitted,
    ):
        # A fresh evidence file per document unless one is named.  The table
        # holds at most one document per file per run, which is the model
        # saying a run reads a given upload once; sharing the fixture's file
        # across several documents would be inventing rows the system cannot
        # produce.
        if evidence_file is None:
            evidence_file = self.make_evidence_file(case=case)
        document = FinancialSourceDocument(
            id=uuid4(),
            case_id=(case or self.case).id,
            evidence_file_id=evidence_file.id,
            ingestion_run_id=(run or self.run).id,
            sha256_at_ingestion=uuid4().hex + uuid4().hex,
            document_type="bank_statement",
            proof_class=proof_class.value,
            status=status.value,
            extraction_layer=ExtractionLayer.structural.value,
            parser_name="statement_pdf",
            parser_version="1.4.0",
        )
        self.db.add(document)
        self.db.flush()
        return document

    def make_transaction(
        self,
        proof_class=ProofClass.p2,
        *,
        case=None,
        run=None,
        account=None,
        document=None,
        ledger_status=LedgerStatus.admitted,
    ):
        self._row_index += 1
        transaction = FinancialTransaction(
            id=uuid4(),
            case_id=(case or self.case).id,
            account_id=(account or self.account).id,
            source_document_id=(document or self.document).id,
            ingestion_run_id=(run or self.run).id,
            ref_id=f"TXN-{uuid4().hex[:12]}",
            row_index=self._row_index,
            amount_minor=125_00,
            currency="GBP",
            direction=TransactionDirection.debit.value,
            transaction_date=date(2026, 3, 4),
            ordering_date=date(2026, 3, 4),
            ordering_date_source=DateSource.transaction.value,
            proof_class=proof_class.value,
            ledger_status=ledger_status.value,
            extraction_layer=ExtractionLayer.structural.value,
            content_hash=uuid4().hex,
        )
        self.db.add(transaction)
        self.db.flush()
        return transaction

    # ---- helpers ---------------------------------------------------------

    def standing_for(self, result: ProofStanding, member: ProofClass) -> ClassStanding:
        for standing in result.classes:
            if standing.proof_class == member.value:
                return standing
        self.fail(f"{member.value} is missing from the census entirely")


class EmptyCaseTests(ProofStandingTestCase):
    """A case with nothing in it still reports every class."""

    def test_every_class_is_present_at_zero(self):
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(
            [standing.proof_class for standing in result.classes],
            [member.value for member in ProofClass],
        )
        for standing in result.classes:
            with self.subTest(proof_class=standing.proof_class):
                self.assertEqual(standing.documents, 0)
                self.assertEqual(standing.transactions, 0)

    def test_totals_are_zero_and_stated(self):
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(result.documents, 0)
        self.assertEqual(result.transactions, 0)
        self.assertEqual(result.documents_requiring_adjudication, 0)
        self.assertEqual(result.transactions_requiring_adjudication, 0)
        self.assertEqual(result.case_id, str(self.case.id))


class CountingTests(ProofStandingTestCase):
    """The counts come from the rows, per class, and add up."""

    def setUp(self):
        super().setUp()
        # Two p2 documents, three p3, one p1, one p4.  The p4 document is the
        # one that can carry no rows.
        self.document = self.make_document(ProofClass.p2)
        self.make_document(ProofClass.p2)
        for _ in range(3):
            self.make_document(ProofClass.p3)
        self.make_document(ProofClass.p1)
        self.make_document(ProofClass.p4)

        # Five p2 rows, two p3 rows, nothing else.
        for _ in range(5):
            self.make_transaction(ProofClass.p2)
        for _ in range(2):
            self.make_transaction(ProofClass.p3)
        self.db.commit()

    def test_documents_are_counted_per_class(self):
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(self.standing_for(result, ProofClass.p0).documents, 0)
        self.assertEqual(self.standing_for(result, ProofClass.p1).documents, 1)
        self.assertEqual(self.standing_for(result, ProofClass.p2).documents, 2)
        self.assertEqual(self.standing_for(result, ProofClass.p3).documents, 3)
        self.assertEqual(self.standing_for(result, ProofClass.p4).documents, 1)

    def test_transactions_are_counted_per_class(self):
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(self.standing_for(result, ProofClass.p2).transactions, 5)
        self.assertEqual(self.standing_for(result, ProofClass.p3).transactions, 2)
        self.assertEqual(self.standing_for(result, ProofClass.p1).transactions, 0)

    def test_p4_carries_documents_but_never_rows(self):
        """The check constraint made visible rather than left implicit."""
        result = case_proof_standing(self.db, self.case.id)
        p4 = self.standing_for(result, ProofClass.p4)

        self.assertEqual(p4.documents, 1)
        self.assertEqual(p4.transactions, 0)
        self.assertFalse(p4.may_produce_ledger_rows)

    def test_the_parts_add_up_to_the_whole(self):
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(
            result.documents, sum(s.documents for s in result.classes)
        )
        self.assertEqual(
            result.transactions, sum(s.transactions for s in result.classes)
        )
        self.assertEqual(result.documents, 7)
        self.assertEqual(result.transactions, 7)

    def test_the_adjudication_population_is_the_p3_population(self):
        """The claim this module exists to make."""
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(result.documents_requiring_adjudication, 3)
        self.assertEqual(result.transactions_requiring_adjudication, 2)
        self.assertEqual(
            result.documents_requiring_adjudication,
            self.standing_for(result, ProofClass.p3).documents,
        )
        self.assertEqual(
            result.transactions_requiring_adjudication,
            self.standing_for(result, ProofClass.p3).transactions,
        )

    def test_disposition_does_not_change_the_class_count(self):
        """A superseded document is still the class its arithmetic earned.

        The census reports one axis and says so.  A quarantined row and a
        superseded document keep the class they carry, because the class is a
        property of the source and the outcome, not of what was later done
        with it.
        """
        before = case_proof_standing(self.db, self.case.id)
        self.make_document(ProofClass.p3, status=DocumentStatus.superseded)
        self.db.commit()
        after = case_proof_standing(self.db, self.case.id)

        self.assertEqual(
            after.documents_requiring_adjudication,
            before.documents_requiring_adjudication + 1,
        )


class CaseScopingTests(ProofStandingTestCase):
    """Another matter's evidence is not this matter's evidence."""

    def setUp(self):
        super().setUp()
        self.document = self.make_document(ProofClass.p3)
        self.make_transaction(ProofClass.p3)

        self.other_file = self.make_evidence_file(
            case=self.other_case, name="not-ours.pdf"
        )
        self.other_run = self.make_run(case=self.other_case)
        self.other_account = self.make_account(
            case=self.other_case, digits="99887766"
        )
        self.other_document = self.make_document(
            ProofClass.p3,
            case=self.other_case,
            run=self.other_run,
            evidence_file=self.other_file,
        )
        for _ in range(4):
            self.make_transaction(
                ProofClass.p3,
                case=self.other_case,
                run=self.other_run,
                account=self.other_account,
                document=self.other_document,
            )
        self.db.commit()

    def test_only_this_case_is_counted(self):
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(result.documents, 1)
        self.assertEqual(result.transactions, 1)
        self.assertEqual(result.documents_requiring_adjudication, 1)
        self.assertEqual(result.transactions_requiring_adjudication, 1)

    def test_the_other_case_is_counted_separately(self):
        result = case_proof_standing(self.db, self.other_case.id)

        self.assertEqual(result.documents, 1)
        self.assertEqual(result.transactions, 4)
        self.assertEqual(result.case_id, str(self.other_case.id))

    def test_a_case_with_no_evidence_reports_nothing_rather_than_everything(self):
        empty = Case(
            id=uuid4(),
            title="Opened This Morning",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add(empty)
        self.db.commit()

        result = case_proof_standing(self.db, empty.id)

        self.assertEqual(result.documents, 0)
        self.assertEqual(result.transactions, 0)

    def test_a_missing_case_is_refused(self):
        with self.assertRaises(ProofStandingError) as raised:
            case_proof_standing(self.db, None)

        self.assertIn("crosses matters", str(raised.exception))


class LicenceTests(ProofStandingTestCase):
    """What the record says a class permits is what proof_class says."""

    def test_each_licence_agrees_with_its_function(self):
        result = case_proof_standing(self.db, self.case.id)

        for member in ProofClass:
            with self.subTest(proof_class=member.value):
                standing = self.standing_for(result, member)
                self.assertEqual(
                    standing.admits_automatically, admits_automatically(member)
                )
                self.assertEqual(
                    standing.requires_adjudication, requires_adjudication(member)
                )
                self.assertEqual(
                    standing.may_produce_ledger_rows,
                    may_produce_ledger_rows(member),
                )
                self.assertEqual(
                    standing.counts_toward_totals,
                    counts_toward_totals(member, included=DEFAULT_TOTAL_CLASSES),
                )

    def test_exactly_one_class_requires_adjudication(self):
        """If this ever fails, the totals a case reports have changed meaning."""
        result = case_proof_standing(self.db, self.case.id)

        requiring = [s.proof_class for s in result.classes if s.requires_adjudication]
        self.assertEqual(requiring, [ProofClass.p3.value])

    def test_the_auto_admitted_classes_are_the_three_named(self):
        result = case_proof_standing(self.db, self.case.id)

        automatic = {
            s.proof_class for s in result.classes if s.admits_automatically
        }
        self.assertEqual(
            automatic, {member.value for member in AUTO_ADMITTED_CLASSES}
        )

    def test_no_class_both_admits_automatically_and_requires_adjudication(self):
        result = case_proof_standing(self.db, self.case.id)

        for standing in result.classes:
            with self.subTest(proof_class=standing.proof_class):
                self.assertFalse(
                    standing.admits_automatically and standing.requires_adjudication
                )


class CountedSetTests(ProofStandingTestCase):
    """The set a total covers is reported, not merely applied."""

    def test_the_default_set_is_reported(self):
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(
            set(result.counted_classes),
            {member.value for member in DEFAULT_TOTAL_CLASSES},
        )

    def test_the_counted_classes_are_in_the_enum_order(self):
        result = case_proof_standing(self.db, self.case.id)

        self.assertEqual(list(result.counted_classes), ["p0", "p1", "p2"])

    def test_a_widened_set_moves_the_flag_and_is_reported(self):
        result = case_proof_standing(
            self.db,
            self.case.id,
            included=frozenset({ProofClass.p0, ProofClass.p1, ProofClass.p2, ProofClass.p3}),
        )

        self.assertTrue(self.standing_for(result, ProofClass.p3).counts_toward_totals)
        self.assertIn("p3", result.counted_classes)

    def test_an_empty_set_is_answered_rather_than_defaulted(self):
        result = case_proof_standing(self.db, self.case.id, included=frozenset())

        self.assertEqual(result.counted_classes, ())
        for standing in result.classes:
            with self.subTest(proof_class=standing.proof_class):
                self.assertFalse(standing.counts_toward_totals)

    def test_a_set_of_strings_is_refused(self):
        with self.assertRaises(ProofStandingError) as raised:
            case_proof_standing(self.db, self.case.id, included={"p0", "p1"})

        self.assertIn("not a ProofClass", str(raised.exception))

    def test_a_list_is_refused(self):
        with self.assertRaises(ProofStandingError) as raised:
            case_proof_standing(
                self.db, self.case.id, included=[ProofClass.p0]
            )

        self.assertIn("set of ProofClass members", str(raised.exception))


class SerialisationTests(ProofStandingTestCase):
    """What crosses the wire carries both halves."""

    def setUp(self):
        super().setUp()
        self.document = self.make_document(ProofClass.p3)
        self.make_transaction(ProofClass.p3)
        self.db.commit()

    def test_as_dict_carries_the_counts_and_the_licences(self):
        payload = case_proof_standing(self.db, self.case.id).as_dict()

        self.assertEqual(payload["case_id"], str(self.case.id))
        self.assertEqual(payload["documents"], 1)
        self.assertEqual(payload["transactions"], 1)
        self.assertEqual(payload["documents_requiring_adjudication"], 1)
        self.assertEqual(payload["transactions_requiring_adjudication"], 1)
        self.assertEqual(payload["counted_classes"], ["p0", "p1", "p2"])

        p3 = next(
            entry for entry in payload["classes"] if entry["proof_class"] == "p3"
        )
        self.assertEqual(p3["documents"], 1)
        self.assertTrue(p3["requires_adjudication"])
        self.assertFalse(p3["admits_automatically"])
        self.assertTrue(p3["may_produce_ledger_rows"])
        self.assertFalse(p3["counts_toward_totals"])

    def test_every_class_appears_in_the_payload(self):
        payload = case_proof_standing(self.db, self.case.id).as_dict()

        self.assertEqual(
            [entry["proof_class"] for entry in payload["classes"]],
            [member.value for member in ProofClass],
        )

    def test_the_payload_holds_only_json_types(self):
        payload = case_proof_standing(self.db, self.case.id).as_dict()

        import json

        # Round-tripped rather than merely dumped, so a value that serialises
        # to something a reader cannot use is caught here rather than in a
        # browser.
        self.assertEqual(json.loads(json.dumps(payload)), payload)


class UnknownStoredClassTests(unittest.TestCase):
    """A class outside the vocabulary is refused rather than dropped.

    Tested against the conversion directly, without a database, because both
    tables constrain ``proof_class`` to the vocabulary and the constraint is
    enforced on write: there is no way to place such a row through the models
    and no reason to want one.  What is under test is the reader's behaviour
    if that guarantee ever stopped holding, which is a property of the
    conversion and not of the query around it.
    """

    def test_an_unrecognised_stored_class_raises_and_names_itself(self):
        with self.assertRaises(ProofStandingError) as raised:
            _member("p9", table="financial_source_documents")

        message = str(raised.exception)
        self.assertIn("p9", message)
        self.assertIn("financial_source_documents", message)

    def test_the_refusal_says_it_will_not_omit_the_row(self):
        """The reason a census cannot skip what it cannot classify.

        Omitting the row would return a document count lower than the case's
        documents with nothing saying why, which is exactly the silently wrong
        total this subsystem exists to prevent.
        """
        with self.assertRaises(ProofStandingError) as raised:
            _member("", table="financial_transactions")

        self.assertIn("silently", str(raised.exception))

    def test_a_real_class_converts(self):
        self.assertIs(
            _member("p3", table="financial_transactions"), ProofClass.p3
        )


if __name__ == "__main__":
    unittest.main()
